"""
Media Scanner Module
Scans Android device for media folders and calculates statistics.
"""

from dataclasses import dataclass, field
from typing import Optional
from .adb import shell_command, list_files, ADBError


# Common media directories on Android
MEDIA_DIRECTORIES = [
    # Internal storage
    "/sdcard/DCIM",
    "/sdcard/Pictures", 
    "/sdcard/Movies",
    "/sdcard/Download",
    "/sdcard/WhatsApp/Media",
    "/sdcard/Telegram",
    "/sdcard/Screenshots",
    "/sdcard/Android/media",
    "/sdcard/Music",
    "/sdcard/Video",
    "/sdcard/Photo",
    "/sdcard/Camera",
    # Alternative internal storage paths
    "/storage/emulated/0/DCIM",
    "/storage/emulated/0/Pictures",
    "/storage/emulated/0/Movies",
    "/storage/emulated/0/Download",
    "/storage/emulated/0/Android/media",
]

# SD Card paths to check (will be dynamically discovered)
SD_CARD_PATTERNS = [
    "/storage/sdcard1",
    "/storage/extSdCard",
    "/storage/external_sd",
    "/mnt/extSdCard",
    "/mnt/sdcard/external_sd",
]

# Media file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.raw', '.cr2', '.nef', '.arw'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v'}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass
class MediaFolder:
    """Represents a folder containing media files."""
    path: str
    name: str
    photo_count: int = 0
    video_count: int = 0
    total_size: int = 0  # in bytes
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


def scan_folder(path: str, device_serial: Optional[str] = None, recursive: bool = True) -> Optional[MediaFolder]:
    """
    Scan a single folder for media files.
    
    Args:
        path: Folder path on the device.
        device_serial: Optional device serial.
        recursive: Whether to scan subfolders.
    
    Returns:
        MediaFolder object with statistics, or None if folder doesn't exist.
    """
    try:
        files = list_files(path, device_serial)
    except ADBError:
        return None
    
    if not files:
        # Check if directory exists
        try:
            output = shell_command(f'[ -d "{path}" ] && echo "exists"', device_serial)
            if 'exists' not in output:
                return None
        except ADBError:
            return None
    
    folder = MediaFolder(
        path=path,
        name=path.rsplit('/', 1)[-1] or path
    )
    
    for file_info in files:
        if file_info['is_dir']:
            if recursive:
                subfolder = scan_folder(file_info['path'], device_serial, recursive=True)
                if subfolder and subfolder.total_count > 0:
                    folder.subfolders.append(subfolder)
                    folder.photo_count += subfolder.photo_count
                    folder.video_count += subfolder.video_count
                    folder.total_size += subfolder.total_size
        else:
            is_media, media_type = is_media_file(file_info['name'])
            if is_media:
                if media_type == 'photo':
                    folder.photo_count += 1
                else:
                    folder.video_count += 1
                folder.total_size += file_info['size']
    
    return folder


def discover_sd_cards(device_serial: Optional[str] = None) -> list[str]:
    """
    Discover SD card mount points on the device.
    
    Returns:
        List of SD card paths that exist on the device.
    """
    sd_paths = []
    
    # Check known SD card patterns
    for pattern in SD_CARD_PATTERNS:
        try:
            output = shell_command(f'[ -d "{pattern}" ] && echo "exists"', device_serial)
            if 'exists' in output:
                sd_paths.append(pattern)
        except ADBError:
            pass
    
    # Also try to find SD cards in /storage/
    try:
        output = shell_command('ls -1 /storage/ 2>/dev/null', device_serial)
        for line in output.strip().split('\n'):
            line = line.strip()
            if line and line not in ['emulated', 'self']:
                potential_path = f'/storage/{line}'
                if potential_path not in sd_paths:
                    sd_paths.append(potential_path)
    except ADBError:
        pass
    
    return sd_paths


def scan_media_folders(
    device_serial: Optional[str] = None,
    additional_paths: Optional[list[str]] = None,
    progress_callback: Optional[callable] = None
) -> ScanResult:
    """
    Scan all common media folders on the device.
    
    Args:
        device_serial: Optional device serial.
        additional_paths: Additional paths to scan beyond defaults.
        progress_callback: Optional callback(folder_path, index, total) for progress.
    
    Returns:
        ScanResult with all found media folders and totals.
    """
    paths_to_scan = MEDIA_DIRECTORIES.copy()
    if additional_paths:
        paths_to_scan.extend(additional_paths)
    
    # Discover and add SD card paths
    sd_cards = discover_sd_cards(device_serial)
    for sd_path in sd_cards:
        # Add common media folders on SD card
        for subdir in ['DCIM', 'Pictures', 'Movies', 'Download', 'Camera', 'Video', 'Photo']:
            full_path = f"{sd_path}/{subdir}"
            if full_path not in paths_to_scan:
                paths_to_scan.append(full_path)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for path in paths_to_scan:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    paths_to_scan = unique_paths
    
    folders = []
    total_photos = 0
    total_videos = 0
    total_size = 0
    
    for i, path in enumerate(paths_to_scan):
        if progress_callback:
            progress_callback(path, i, len(paths_to_scan))
        
        folder = scan_folder(path, device_serial, recursive=True)
        if folder and folder.total_count > 0:
            folders.append(folder)
            total_photos += folder.photo_count
            total_videos += folder.video_count
            total_size += folder.total_size
    
    return ScanResult(
        folders=folders,
        total_photos=total_photos,
        total_videos=total_videos,
        total_size=total_size
    )


def get_all_media_files(folder: MediaFolder, device_serial: Optional[str] = None) -> list[dict]:
    """
    Get all media files from a folder recursively.
    
    Args:
        folder: MediaFolder to get files from.
        device_serial: Optional device serial.
    
    Returns:
        List of file info dicts with path, size, mtime.
    """
    all_files = []
    
    def collect_files(path: str):
        try:
            files = list_files(path, device_serial)
            for file_info in files:
                if file_info['is_dir']:
                    collect_files(file_info['path'])
                else:
                    is_media, _ = is_media_file(file_info['name'])
                    if is_media:
                        all_files.append(file_info)
        except ADBError:
            pass
    
    collect_files(folder.path)
    return all_files
