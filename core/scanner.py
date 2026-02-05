"""
Media Scanner Module
Scans Android device for media folders and calculates statistics.
"""

from dataclasses import dataclass, field
from typing import Optional
from .adb import shell_command, list_files, ADBError


# Media file extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.raw', '.cr2', '.nef', '.arw'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v'}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

# Directories to skip during recursive scan
SKIP_DIRECTORIES = {
    'Android/data',  # App data, usually not user media
    'Android/obb',   # Game data
    '.thumbnails',
    '.cache',
    'cache',
    '.trash',
    'lost+found',
}


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


def should_skip_directory(path: str) -> bool:
    """Check if a directory should be skipped during scan."""
    for skip in SKIP_DIRECTORIES:
        if skip in path:
            return True
    return False


def get_storage_roots(device_serial: Optional[str] = None) -> list[str]:
    """
    Get all storage root paths on the device.
    
    Returns:
        List of unique storage root paths.
    """
    roots = set()
    
    # Primary internal storage - /sdcard is usually a symlink
    try:
        # Resolve /sdcard symlink to get real path
        output = shell_command('readlink -f /sdcard', device_serial)
        real_path = output.strip()
        if real_path:
            roots.add(real_path)
    except ADBError:
        pass
    
    # Fallback to known paths
    roots.add('/storage/emulated/0')
    
    # Find external SD cards and other storage in /storage/
    try:
        output = shell_command('ls -1 /storage/ 2>/dev/null', device_serial)
        for line in output.strip().split('\n'):
            line = line.strip()
            if line and line not in ['emulated', 'self']:
                potential_path = f'/storage/{line}'
                # Check if it's a valid storage
                try:
                    check = shell_command(f'[ -d "{potential_path}" ] && echo "ok"', device_serial)
                    if 'ok' in check:
                        roots.add(potential_path)
                except ADBError:
                    pass
    except ADBError:
        pass
    
    return list(roots)


def scan_directory_recursive(
    path: str,
    device_serial: Optional[str] = None,
    max_depth: int = 10,
    current_depth: int = 0,
    progress_callback: Optional[callable] = None
) -> dict[str, dict]:
    """
    Scan a directory recursively and collect media file information.
    
    Returns:
        Dict mapping folder paths to their media statistics.
    """
    if current_depth > max_depth:
        return {}
    
    if should_skip_directory(path):
        return {}
    
    folder_stats = {}
    
    try:
        files = list_files(path, device_serial)
    except ADBError:
        return {}
    
    current_folder = {
        'photos': 0,
        'videos': 0,
        'size': 0,
        'files': []
    }
    
    for file_info in files:
        if file_info['is_dir']:
            # Recurse into subdirectory
            subpath = file_info['path']
            if not should_skip_directory(subpath):
                if progress_callback:
                    progress_callback(subpath, 0, 0)
                sub_stats = scan_directory_recursive(
                    subpath, device_serial, max_depth, current_depth + 1, progress_callback
                )
                folder_stats.update(sub_stats)
        else:
            is_media, media_type = is_media_file(file_info['name'])
            if is_media:
                if media_type == 'photo':
                    current_folder['photos'] += 1
                else:
                    current_folder['videos'] += 1
                current_folder['size'] += file_info['size']
                current_folder['files'].append(file_info)
    
    # Only add folder if it contains media
    if current_folder['photos'] > 0 or current_folder['videos'] > 0:
        folder_stats[path] = current_folder
    
    return folder_stats


def aggregate_to_top_level(
    folder_stats: dict[str, dict],
    storage_root: str,
    min_depth: int = 1
) -> list[MediaFolder]:
    """
    Aggregate folder statistics to top-level media folders.
    
    This groups media by their top-level parent folder under the storage root.
    For example, all files under /sdcard/DCIM/* get grouped into a single 'DCIM' folder.
    
    Args:
        folder_stats: Dict from scan_directory_recursive
        storage_root: The storage root path (e.g., /storage/emulated/0)
        min_depth: Minimum depth from root to consider as a "top-level" folder
    
    Returns:
        List of MediaFolder objects representing top-level folders.
    """
    # Group by top-level folder
    top_level_groups: dict[str, list[str]] = {}
    
    for folder_path in folder_stats.keys():
        # Get path relative to storage root
        if folder_path.startswith(storage_root):
            relative = folder_path[len(storage_root):].lstrip('/')
        else:
            relative = folder_path
        
        parts = relative.split('/')
        if len(parts) >= min_depth:
            # Use first directory as top-level
            top_level = parts[0]
            top_level_path = f"{storage_root}/{top_level}"
        else:
            top_level_path = folder_path
        
        if top_level_path not in top_level_groups:
            top_level_groups[top_level_path] = []
        top_level_groups[top_level_path].append(folder_path)
    
    # Create MediaFolder for each top-level group
    folders = []
    for top_path, child_paths in top_level_groups.items():
        name = top_path.rsplit('/', 1)[-1] or top_path
        
        total_photos = 0
        total_videos = 0
        total_size = 0
        
        for child_path in child_paths:
            stats = folder_stats[child_path]
            total_photos += stats['photos']
            total_videos += stats['videos']
            total_size += stats['size']
        
        folder = MediaFolder(
            path=top_path,
            name=name,
            photo_count=total_photos,
            video_count=total_videos,
            total_size=total_size
        )
        folders.append(folder)
    
    # Sort by total count descending
    folders.sort(key=lambda f: f.total_count, reverse=True)
    
    return folders


def scan_media_folders(
    device_serial: Optional[str] = None,
    additional_paths: Optional[list[str]] = None,
    progress_callback: Optional[callable] = None
) -> ScanResult:
    """
    Scan all storage for media folders on the device.
    
    Args:
        device_serial: Optional device serial.
        additional_paths: Additional paths to scan beyond auto-discovered storage.
        progress_callback: Optional callback(folder_path, index, total) for progress.
    
    Returns:
        ScanResult with all found media folders and totals.
    """
    # Get all storage roots
    storage_roots = get_storage_roots(device_serial)
    if additional_paths:
        storage_roots.extend(additional_paths)
    
    # Remove duplicates
    storage_roots = list(set(storage_roots))
    
    all_folder_stats: dict[str, dict] = {}
    
    for root in storage_roots:
        if progress_callback:
            progress_callback(root, 0, len(storage_roots))
        
        stats = scan_directory_recursive(
            root, device_serial, progress_callback=progress_callback
        )
        all_folder_stats.update(stats)
    
    # Aggregate to top-level folders per storage root
    all_folders: list[MediaFolder] = []
    
    for root in storage_roots:
        # Filter stats for this root
        root_stats = {k: v for k, v in all_folder_stats.items() if k.startswith(root)}
        if root_stats:
            folders = aggregate_to_top_level(root_stats, root)
            all_folders.extend(folders)
    
    # Merge folders with same name from different storage roots
    merged: dict[str, MediaFolder] = {}
    for folder in all_folders:
        if folder.name in merged:
            # Merge into existing
            existing = merged[folder.name]
            existing.photo_count += folder.photo_count
            existing.video_count += folder.video_count
            existing.total_size += folder.total_size
        else:
            merged[folder.name] = folder
    
    folders = list(merged.values())
    folders.sort(key=lambda f: f.total_count, reverse=True)
    
    # Calculate totals
    total_photos = sum(f.photo_count for f in folders)
    total_videos = sum(f.video_count for f in folders)
    total_size = sum(f.total_size for f in folders)
    
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
                    if not should_skip_directory(file_info['path']):
                        collect_files(file_info['path'])
                else:
                    is_media, _ = is_media_file(file_info['name'])
                    if is_media:
                        all_files.append(file_info)
        except ADBError:
            pass
    
    collect_files(folder.path)
    return all_files
