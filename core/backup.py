"""
Backup Manager Module
Orchestrates the backup process with incremental sync support.
"""

import os
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

from .adb import pull_file, ADBError, get_single_device
from .scanner import MediaFolder, get_all_media_files, is_media_file
from .manifest import Manifest


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
    skipped_files: int  # Already synced
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
    needs_sync: bool  # False if already synced


class BackupManager:
    """
    Manages backup operations with incremental sync support.
    
    Features:
    - Incremental backup (only downloads new/modified files)
    - Progress tracking with callbacks
    - Interrupt and resume support via manifest
    - Maintains folder structure from device
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
        self.manifest = Manifest(destination)
        self._cancelled = False
        
        # Set device info in manifest
        device = get_single_device()
        if device:
            self.manifest.set_device_info(device.serial, device.model)
    
    def analyze_folder(self, folder: MediaFolder) -> tuple[list[FileToSync], list[FileToSync]]:
        """
        Analyze a folder to determine what needs to be synced.
        
        Args:
            folder: MediaFolder to analyze.
        
        Returns:
            Tuple of (files_to_sync, already_synced)
        """
        all_files = get_all_media_files(folder, self.device_serial)
        
        to_sync = []
        already_synced = []
        
        for file_info in all_files:
            remote_path = file_info['path']
            
            # Calculate local path maintaining folder structure
            # Keep storage type distinction to avoid conflicts
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
                    relative_path = relative_path[1:]  # Remove leading /
            
            local_path = os.path.join(self.destination, relative_path)
            
            file_to_sync = FileToSync(
                remote_path=remote_path,
                local_path=local_path,
                size=file_info['size'],
                mtime=file_info['mtime'],
                needs_sync=True
            )
            
            # Check if already synced
            if self.manifest.is_synced(remote_path, file_info['size'], file_info['mtime']):
                file_to_sync.needs_sync = False
                already_synced.append(file_to_sync)
            else:
                to_sync.append(file_to_sync)
        
        return to_sync, already_synced
    
    def analyze_folders(self, folders: list[MediaFolder]) -> tuple[list[FileToSync], list[FileToSync]]:
        """
        Analyze multiple folders.
        
        Returns:
            Tuple of (all_files_to_sync, all_already_synced)
        """
        all_to_sync = []
        all_synced = []
        
        for folder in folders:
            to_sync, synced = self.analyze_folder(folder)
            all_to_sync.extend(to_sync)
            all_synced.extend(synced)
        
        return all_to_sync, all_synced
    
    def start_backup(
        self,
        folders: list[MediaFolder],
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
        to_sync, already_synced = self.analyze_folders(folders)
        
        total_files = len(to_sync) + len(already_synced)
        total_bytes = sum(f.size for f in to_sync) + sum(f.size for f in already_synced)
        skipped_bytes = sum(f.size for f in already_synced)
        
        progress = BackupProgress(
            total_files=total_files,
            completed_files=0,
            skipped_files=len(already_synced),
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
                    # Add to manifest
                    self.manifest.add_entry(
                        file_to_sync.remote_path,
                        file_to_sync.local_path,
                        file_to_sync.size,
                        file_to_sync.mtime
                    )
                    progress.completed_files += 1
                    progress.completed_bytes += file_to_sync.size
                    
                    # Save manifest periodically (every 10 files)
                    if progress.completed_files % 10 == 0:
                        self.manifest.save()
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
        
        # Final save
        if not self._cancelled:
            self.manifest.update_last_sync()
            progress.status = BackupStatus.COMPLETED
        
        self.manifest.save()
        progress.current_file = ""
        
        if progress_callback:
            progress_callback(progress)
        
        return progress
    
    def cancel(self):
        """Cancel the ongoing backup operation."""
        self._cancelled = True
    
    def get_sync_stats(self) -> dict:
        """Get statistics about current sync state."""
        return self.manifest.get_stats()
