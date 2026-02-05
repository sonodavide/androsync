"""
Backup Manager Module
Orchestrates the backup process with rsync-like incremental sync.
No manifest needed - compares directly with local files.
"""

import os
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

from .adb import pull_file, pull_files_tar, ADBError, get_single_device
from .scanner import MediaFolder, get_all_media_files


class BackupStatus(Enum):
    """Status of the backup operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class BackupProgress:
    """Progress information for backup operation."""
    total_files: int
    completed_files: int
    skipped_files: int  # Already exist locally
    failed_files: int
    current_file: str
    total_bytes: int
    completed_bytes: int
    skipped_bytes: int
    status: BackupStatus
    error_message: Optional[str] = None
    
    @property
    def pending_files(self) -> int:
        return self.total_files - self.completed_files - self.skipped_files - self.failed_files
    
    @property
    def progress_percent(self) -> float:
        if self.total_files == 0:
            return 100.0
        return ((self.completed_files + self.skipped_files) / self.total_files) * 100


@dataclass 
class FileToSync:
    """Represents a file that needs to be synced."""
    remote_path: str
    local_path: str
    size: int
    mtime: str
    needs_sync: bool  # False if already exists locally with same size


class BackupManager:
    """
    Manages backup operations with rsync-like incremental sync.
    
    Features:
    - Rsync-like comparison: checks local files directly
    - Multithread local file checking for speed
    - No manifest needed
    - Progress tracking with callbacks
    """
    
    def __init__(self, destination: str, device_serial: Optional[str] = None):
        """
        Initialize backup manager.
        
        Args:
            destination: Local directory to save backups.
            device_serial: Optional device serial for multi-device support.
        """
        self.destination = destination
        self.device_serial = device_serial
        self._cancelled = False
        
        # Ensure destination exists
        os.makedirs(destination, exist_ok=True)
    
    def _get_local_path(self, remote_path: str) -> str:
        """Calculate local path from remote path, maintaining folder structure."""
        relative_path = remote_path
        if relative_path.startswith('/sdcard/'):
            relative_path = 'internal/' + relative_path[8:]
        elif relative_path.startswith('/storage/emulated/0/'):
            relative_path = 'internal/' + relative_path[20:]
        elif relative_path.startswith('/storage/'):
            # SD card or other storage: /storage/XXXX-XXXX/... -> sdcard_XXXX-XXXX/...
            parts = relative_path[9:].split('/', 1)
            if len(parts) == 2:
                storage_name = parts[0]
                rest = parts[1]
                relative_path = f'sdcard_{storage_name}/{rest}'
            else:
                relative_path = relative_path[1:]
        
        return os.path.join(self.destination, relative_path)
    
    def _check_local_file(self, local_path: str, expected_size: int) -> bool:
        """Check if local file exists and has matching size."""
        try:
            stat = os.stat(local_path)
            return stat.st_size == expected_size
        except OSError:
            return False
    
    def _check_files_multithread(
        self, 
        files: list[tuple[str, int]]  # List of (local_path, expected_size)
    ) -> set[str]:
        """
        Check multiple local files in parallel using threadpool.
        
        Returns:
            Set of local paths that exist and have matching size.
        """
        existing = set()
        
        if not files:
            return existing
        
        # Use thread pool for parallel file stat
        # Threads are ideal for I/O bound operations like file stat
        with ThreadPoolExecutor(max_workers=16) as executor:
            future_to_path = {
                executor.submit(self._check_local_file, path, size): path
                for path, size in files
            }
            
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    if future.result():
                        existing.add(path)
                except Exception:
                    pass
        
        return existing
    
    def analyze_folder(self, folder: MediaFolder, categories: list[str] = None) -> tuple[list[FileToSync], list[FileToSync]]:
        """
        Analyze a folder to determine what needs to be synced.
        Rsync-like: compares directly with local files.
        
        Args:
            folder: MediaFolder to analyze.
        
        Returns:
            Tuple of (files_to_sync, already_exist)
        """
        all_files = get_all_media_files(folder, categories, self.device_serial)
        
        # Build list of files with their local paths
        files_with_paths = []
        for file_info in all_files:
            remote_path = file_info['path']
            local_path = self._get_local_path(remote_path)
            files_with_paths.append((file_info, local_path))
        
        # Check all files locally using multithread
        files_to_check = [
            (local_path, file_info['size'])
            for file_info, local_path in files_with_paths
        ]
        
        existing_paths = self._check_files_multithread(files_to_check)
        
        # Categorize files
        to_sync = []
        already_exist = []
        
        for file_info, local_path in files_with_paths:
            file_to_sync = FileToSync(
                remote_path=file_info['path'],
                local_path=local_path,
                size=file_info['size'],
                mtime=file_info['mtime'],
                needs_sync=local_path not in existing_paths
            )
            
            if file_to_sync.needs_sync:
                to_sync.append(file_to_sync)
            else:
                already_exist.append(file_to_sync)
        
        return to_sync, already_exist
    
    def analyze_folders(self, folders: list[MediaFolder], categories: list[str] = None) -> tuple[list[FileToSync], list[FileToSync]]:
        """
        Analyze multiple folders.
        
        Returns:
            Tuple of (all_files_to_sync, all_already_exist)
        """
        all_to_sync = []
        all_exist = []
        
        for folder in folders:
            to_sync, exist = self.analyze_folder(folder, categories)
            all_to_sync.extend(to_sync)
            all_exist.extend(exist)
        
        return all_to_sync, all_exist
    
    def start_backup(
        self,
        folders: list[MediaFolder],
        categories: list[str] = None,
        progress_callback: Optional[Callable[[BackupProgress], None]] = None
    ) -> BackupProgress:
        """
        Start backup operation for selected folders.
        
        Args:
            folders: List of MediaFolder objects to backup.
            progress_callback: Optional callback called with BackupProgress updates.
        
        Returns:
            Final BackupProgress with results.
        """
        self._cancelled = False
        
        # Analyze what needs to be synced
        to_sync, already_exist = self.analyze_folders(folders, categories)
        
        total_files = len(to_sync) + len(already_exist)
        total_bytes = sum(f.size for f in to_sync) + sum(f.size for f in already_exist)
        skipped_bytes = sum(f.size for f in already_exist)
        
        progress = BackupProgress(
            total_files=total_files,
            completed_files=0,
            skipped_files=len(already_exist),
            failed_files=0,
            current_file="",
            total_bytes=total_bytes,
            completed_bytes=0,
            skipped_bytes=skipped_bytes,
            status=BackupStatus.IN_PROGRESS
        )
        
        if progress_callback:
            progress_callback(progress)
        
        # Process files that need syncing
        for file_to_sync in to_sync:
            if self._cancelled:
                progress.status = BackupStatus.CANCELLED
                break
            
            progress.current_file = os.path.basename(file_to_sync.remote_path)
            
            if progress_callback:
                progress_callback(progress)
            
            try:
                # Create directory structure
                os.makedirs(os.path.dirname(file_to_sync.local_path), exist_ok=True)
                
                # Pull file from device
                success = pull_file(
                    file_to_sync.remote_path,
                    file_to_sync.local_path,
                    self.device_serial
                )
                
                if success:
                    progress.completed_files += 1
                    progress.completed_bytes += file_to_sync.size
                else:
                    progress.failed_files += 1
                    
            except ADBError as e:
                progress.failed_files += 1
                progress.error_message = str(e)
            except OSError as e:
                progress.failed_files += 1
                progress.error_message = f"File system error: {e}"
            
            if progress_callback:
                progress_callback(progress)
        
        # Final status
        if not self._cancelled:
            progress.status = BackupStatus.COMPLETED
        
        progress.current_file = ""
        
        if progress_callback:
            progress_callback(progress)
        
        return progress
    
    def cancel(self):
        """Cancel the ongoing backup operation."""
        self._cancelled = True
    
    def get_sync_stats(self) -> dict:
        """Get statistics about backup destination."""
        total_files = 0
        total_size = 0
        
        for root, dirs, files in os.walk(self.destination):
            for f in files:
                total_files += 1
                try:
                    total_size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        
        return {
            'total_files': total_files,
            'total_size': total_size,
            'destination': self.destination
        }
