"""
Media Scanner Module
Scans Android device for media folders and calculates statistics.
Uses fast find command instead of recursive ls for better performance.
"""

from dataclasses import dataclass, field
from typing import Optional
from .adb import shell_command, find_media_files, ADBError


# Media file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.raw', '.cr2', '.nef', '.arw'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v'}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

# Directories to skip during scan
SKIP_DIRECTORIES = [
    'Android/data',
    'Android/obb',
    '.thumbnails',
    '.cache',
    'cache',
    '.trash',
    'lost+found',
]

# Directories to expand to show individual subfolders
EXPAND_DIRECTORIES = {
    'Android/media',
}


@dataclass
class MediaFolder:
    """Represents a folder containing media files."""
    path: str
    name: str
    photo_count: int = 0
    video_count: int = 0
    total_size: int = 0
    storage_type: str = ""
    storage_root: str = ""
    subfolders: list['MediaFolder'] = field(default_factory=list)
    
    @property
    def total_count(self) -> int:
        return self.photo_count + self.video_count
    
    @property
    def size_mb(self) -> float:
        return self.total_size / (1024 * 1024)
    
    @property
    def size_gb(self) -> float:
        return self.total_size / (1024 * 1024 * 1024)
    
    def size_human(self) -> str:
        """Return human-readable size."""
        if self.total_size >= 1024 * 1024 * 1024:
            return f"{self.size_gb:.2f} GB"
        elif self.total_size >= 1024 * 1024:
            return f"{self.size_mb:.2f} MB"
        elif self.total_size >= 1024:
            return f"{self.total_size / 1024:.2f} KB"
        else:
            return f"{self.total_size} B"


@dataclass
class ScanResult:
    """Result of a media scan operation."""
    folders: list[MediaFolder]
    total_photos: int = 0
    total_videos: int = 0
    total_size: int = 0
    
    @property
    def total_media(self) -> int:
        return self.total_photos + self.total_videos
    
    def size_human(self) -> str:
        """Return human-readable total size."""
        if self.total_size >= 1024 * 1024 * 1024:
            return f"{self.total_size / (1024**3):.2f} GB"
        elif self.total_size >= 1024 * 1024:
            return f"{self.total_size / (1024**2):.2f} MB"
        else:
            return f"{self.total_size / 1024:.2f} KB"


def is_media_file(filename: str) -> tuple[bool, str]:
    """
    Check if a file is a media file.
    
    Returns:
        Tuple of (is_media, type) where type is 'photo', 'video', or ''
    """
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    ext = f'.{ext}'
    
    if ext in IMAGE_EXTENSIONS:
        return True, 'photo'
    elif ext in VIDEO_EXTENSIONS:
        return True, 'video'
    return False, ''


def get_storage_roots(device_serial: Optional[str] = None) -> dict[str, str]:
    """
    Get all storage root paths on the device.
    
    Returns:
        Dict mapping storage path to storage type name.
    """
    roots = {}
    
    # Primary internal storage
    try:
        output = shell_command('readlink -f /sdcard', device_serial)
        real_path = output.strip()
        if real_path:
            roots[real_path] = "Interno"
    except ADBError:
        pass
    
    # Fallback for internal
    if '/storage/emulated/0' not in roots:
        roots['/storage/emulated/0'] = "Interno"
    
    # Find external SD cards in /storage/
    try:
        output = shell_command('ls -1 /storage/ 2>/dev/null', device_serial)
        for line in output.strip().split('\n'):
            line = line.strip()
            if line and line not in ['emulated', 'self']:
                potential_path = f'/storage/{line}'
                try:
                    check = shell_command(f'[ -d "{potential_path}" ] && echo "ok"', device_serial)
                    if 'ok' in check:
                        roots[potential_path] = f"SD Card ({line})"
                except ADBError:
                    pass
    except ADBError:
        pass
    
    return roots


def should_expand_directory(relative_path: str) -> bool:
    """Check if a directory should be expanded to show subfolders."""
    for expand in EXPAND_DIRECTORIES:
        if relative_path == expand or relative_path.startswith(expand + '/'):
            return True
    return False


def aggregate_files_to_folders(
    files: list[dict],
    storage_root: str,
    storage_type: str
) -> list[MediaFolder]:
    """
    Aggregate a flat list of files into folder statistics.
    
    Args:
        files: List of file dicts from find_media_files
        storage_root: The storage root path
        storage_type: Human-readable storage type name
    
    Returns:
        List of MediaFolder objects
    """
    # Group files by top-level folder
    folder_stats: dict[str, dict] = {}
    
    for file_info in files:
        path = file_info['path']
        
        # Get path relative to storage root
        if path.startswith(storage_root):
            relative = path[len(storage_root):].lstrip('/')
        else:
            relative = path
        
        parts = relative.split('/')
        
        # Determine the grouping folder
        if len(parts) >= 3 and should_expand_directory('/'.join(parts[:2])):
            # For Android/media, use 3 levels (Android/media/com.app)
            top_level = '/'.join(parts[:3])
        elif len(parts) >= 1:
            # Use first directory
            top_level = parts[0]
        else:
            top_level = relative
        
        top_level_path = f"{storage_root}/{top_level}"
        
        if top_level_path not in folder_stats:
            folder_stats[top_level_path] = {
                'name': top_level,
                'photos': 0,
                'videos': 0,
                'size': 0
            }
        
        # Categorize file
        is_media, media_type = is_media_file(file_info['name'])
        if is_media:
            if media_type == 'photo':
                folder_stats[top_level_path]['photos'] += 1
            else:
                folder_stats[top_level_path]['videos'] += 1
            folder_stats[top_level_path]['size'] += file_info['size']
    
    # Create MediaFolder objects
    folders = []
    for path, stats in folder_stats.items():
        folder = MediaFolder(
            path=path,
            name=stats['name'],
            photo_count=stats['photos'],
            video_count=stats['videos'],
            total_size=stats['size'],
            storage_type=storage_type,
            storage_root=storage_root
        )
        folders.append(folder)
    
    # Sort by total count descending
    folders.sort(key=lambda f: f.total_count, reverse=True)
    
    return folders


def scan_media_folders(
    device_serial: Optional[str] = None,
    scan_internal: bool = True,
    scan_sdcard: bool = True,
    storage_paths: Optional[dict[str, str]] = None,
    additional_paths: Optional[list[str]] = None,
    progress_callback: Optional[callable] = None
) -> ScanResult:
    """
    Scan selected storage for media folders on the device.
    Uses fast find command for much better performance.
    
    Args:
        device_serial: Optional device serial.
        scan_internal: Whether to scan internal storage (ignored if storage_paths provided).
        scan_sdcard: Whether to scan SD card(s) (ignored if storage_paths provided).
        storage_paths: Dict mapping path -> name for specific paths to scan.
        additional_paths: Additional paths to scan beyond auto-discovered storage.
        progress_callback: Optional callback(message, index, total) for progress.
    
    Returns:
        ScanResult with all found media folders and totals.
    """
    if storage_paths:
        # Use provided paths directly
        storage_roots = storage_paths.copy()
    else:
        # Get all storage roots with their types
        all_roots = get_storage_roots(device_serial)
        
        # Filter based on selection
        storage_roots = {}
        for path, storage_type in all_roots.items():
            if storage_type == "Interno" and scan_internal:
                storage_roots[path] = storage_type
            elif storage_type.startswith("SD Card") and scan_sdcard:
                storage_roots[path] = storage_type
    
    if additional_paths:
        for path in additional_paths:
            if path not in storage_roots:
                storage_roots[path] = "Altro"
    
    all_folders: list[MediaFolder] = []
    total_roots = len(storage_roots)
    
    for idx, (root, storage_type) in enumerate(storage_roots.items()):
        if progress_callback:
            progress_callback(f"Scansione {storage_type}...", idx, total_roots)
        
        # Use fast find command
        files = find_media_files(
            storage_root=root,
            extensions=MEDIA_EXTENSIONS,
            device_serial=device_serial,
            exclude_patterns=SKIP_DIRECTORIES
        )
        
        if progress_callback:
            progress_callback(f"Analisi {len(files)} file da {storage_type}...", idx, total_roots)
        
        if files:
            folders = aggregate_files_to_folders(files, root, storage_type)
            all_folders.extend(folders)
    
    # Sort by total count descending
    all_folders.sort(key=lambda f: f.total_count, reverse=True)
    
    # Calculate totals
    total_photos = sum(f.photo_count for f in all_folders)
    total_videos = sum(f.video_count for f in all_folders)
    total_size = sum(f.total_size for f in all_folders)
    
    return ScanResult(
        folders=all_folders,
        total_photos=total_photos,
        total_videos=total_videos,
        total_size=total_size
    )


def get_all_media_files(folder: MediaFolder, device_serial: Optional[str] = None) -> list[dict]:
    """
    Get all media files from a folder using fast find command.
    
    Args:
        folder: MediaFolder to get files from.
        device_serial: Optional device serial.
    
    Returns:
        List of file info dicts with path, size, mtime.
    """
    return find_media_files(
        storage_root=folder.path,
        extensions=MEDIA_EXTENSIONS,
        device_serial=device_serial,
        exclude_patterns=SKIP_DIRECTORIES
    )
