"""
GUI Worker Threads Module
Background workers for scan, backup, and analyze operations.
"""

import time
from typing import Optional

from PySide6.QtCore import QThread, Signal

from core.adb import ADBError
from core.scanner import scan_media_folders, MediaFolder, ScanResult
from core.backup import BackupManager, BackupProgress


class ScanWorker(QThread):
    """Worker thread for scanning device."""
    finished = Signal(object)  # ScanResult or None
    progress = Signal(str)  # Current folder being scanned
    error = Signal(str)
    
    def __init__(self, storage_paths: dict[str, str], categories: list[str], include_hidden: bool = False, include_system: bool = False, device_serial: Optional[str] = None):
        """
        Args:
            storage_paths: Dict mapping path -> display name to scan
            categories: List of categories to scan
            include_hidden: Whether to include hidden files
            include_system: Whether to include system directories (cache, Android/data, etc.)
            device_serial: Optional device serial to use
        """
        super().__init__()
        self.storage_paths = storage_paths
        self.categories = categories
        self.include_hidden = include_hidden
        self.include_system = include_system
        self.device_serial = device_serial
    
    def run(self):
        try:
            def on_progress(path: str, index: int, total: int):
                self.progress.emit(f"Scansione: {path}")
            
            result = scan_media_folders(
                storage_paths=self.storage_paths,
                categories=self.categories,
                include_hidden=self.include_hidden,
                include_system=self.include_system,
                device_serial=self.device_serial,
                progress_callback=on_progress
            )
            self.finished.emit(result)
        except ADBError as e:
            self.error.emit(str(e))
            self.finished.emit(None)


class BackupWorker(QThread):
    """Worker thread for backup operation."""
    progress = Signal(object)  # BackupProgress
    finished = Signal(object, float)  # Final BackupProgress, elapsed_time
    
    def __init__(self, folders: list[MediaFolder], categories: list[str], destination: str, include_hidden: bool = False, include_system: bool = False, device_serial: Optional[str] = None):
        super().__init__()
        self.folders = folders
        self.categories = categories
        self.destination = destination
        self.include_hidden = include_hidden
        self.include_system = include_system
        self.device_serial = device_serial
        self.manager: Optional[BackupManager] = None
        self.start_time: float = 0
    
    def run(self):
        self.start_time = time.time()
        self.manager = BackupManager(self.destination, self.device_serial)
        
        def on_progress(bp: BackupProgress):
            self.progress.emit(bp)
        
        result = self.manager.start_backup(
            self.folders, 
            categories=self.categories,
            include_hidden=self.include_hidden,
            include_system=self.include_system,
            progress_callback=on_progress
        )
        elapsed = time.time() - self.start_time
        self.finished.emit(result, elapsed)
    
    def cancel(self):
        if self.manager:
            self.manager.cancel()


class AnalyzeWorker(QThread):
    """Worker thread for analyzing files before backup."""
    finished = Signal(list, list)  # to_sync, already_synced
    error = Signal(str)
    
    def __init__(self, folders: list[MediaFolder], categories: list[str], destination: str, include_hidden: bool = False, include_system: bool = False, device_serial: Optional[str] = None):
        super().__init__()
        self.folders = folders
        self.categories = categories
        self.destination = destination
        self.include_hidden = include_hidden
        self.include_system = include_system
        self.device_serial = device_serial
    
    def run(self):
        try:
            manager = BackupManager(self.destination, self.device_serial)
            to_sync, already_synced = manager.analyze_folders(self.folders, self.categories, self.include_hidden, self.include_system)
            self.finished.emit(to_sync, already_synced)
        except Exception as e:
            self.error.emit(str(e))
