"""
File Scanner Module
Scans Android device for files by category and calculates statistics.
Uses fast find command instead of recursive ls for better performance.
"""

from dataclasses import dataclass, field
from typing import Optional
from .adb import shell_command, find_media_files, ADBError


# File categories with their extensions
FILE_CATEGORIES = {
    'media': {
        'name': 'Media',
        'extensions': {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.raw', '.cr2', '.nef', '.arw',
                       '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v'}
    },
    'documents': {
        'name': 'Documenti',
        'extensions': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.odt', '.ods', '.odp', 
                       '.rtf', '.csv', '.md', '.json', '.xml', '.html', '.htm'}
    },
    'apk': {
        'name': 'APK',
        'extensions': {'.apk', '.xapk', '.apkm'}
    },
    'other': {
        'name': 'Altro',
        'extensions': set()  # Special: matches everything not in other categories
    }
}

# Legacy compatibility
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.raw', '.cr2', '.nef', '.arw'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v'}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

# All known extensions (for "other" category exclusion)
ALL_KNOWN_EXTENSIONS = set()
for cat in FILE_CATEGORIES.values():
    ALL_KNOWN_EXTENSIONS |= cat['extensions']


def get_extensions_for_categories(categories: list[str]) -> set[str]:
    """Get combined extensions for selected categories."""
    extensions = set()
    include_other = False
    
    for cat in categories:
        if cat == 'other':
            include_other = True
        elif cat in FILE_CATEGORIES:
            extensions |= FILE_CATEGORIES[cat]['extensions']
    
    return extensions, include_other


def get_file_subcategory(filename: str) -> str:
    """Determine the display subcategory of a file."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    
    # Photo
    if ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.raw', '.cr2', '.nef', '.arw'}:
        return 'Foto'
    # Video
    elif ext in {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v'}:
        return 'Video'
    # PDF
    elif ext == '.pdf':
        return 'PDF'
    # Word
    elif ext in {'.doc', '.docx', '.odt'}:
        return 'Word'
    # Excel
    elif ext in {'.xls', '.xlsx', '.ods'}:
        return 'Excel'
    # PowerPoint
    elif ext in {'.ppt', '.pptx', '.odp'}:
        return 'PowerPoint'
    # Text
    elif ext in {'.txt', '.md', '.log', '.rtf'}:
        return 'Testo'
    # APK
    elif ext in {'.apk', '.xapk', '.apkm'}:
        return 'APK'
    # Code/Data
    elif ext in {'.json', '.xml', '.html', '.htm', '.csv'}:
        return 'Dati'
    else:
        return 'Altro'


def is_file_in_categories(filename: str, categories: list[str]) -> bool:
    """Check if a file matches any of the selected categories."""
    ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    extensions, include_other = get_extensions_for_categories(categories)
    
    if ext in extensions:
        return True
    if include_other and ext not in ALL_KNOWN_EXTENSIONS:
        return True
    return False


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
    file_count: int = 0
    photo_count: int = 0
    video_count: int = 0
    total_size: int = 0
    storage_type: str = ""
    storage_root: str = ""
    subfolders: list['MediaFolder'] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    
    @property
    def total_count(self) -> int:
        return self.file_count
    
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
    total_files: int = 0
    total_size: int = 0
    file_stats: dict[str, int] = field(default_factory=dict)  # subcategory -> count
    
    @property
    def total_media(self) -> int:
        return self.total_files
    
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
    Avoids duplicates by resolving symlinks and checking real paths.
    
    Returns:
        Dict mapping storage path to storage type name.
    """
    roots = {}
    seen_real_paths = set()
    
    # Primary internal storage - resolve the real path
    internal_path = '/storage/emulated/0'
    try:
        output = shell_command('readlink -f /sdcard', device_serial)
        real_path = output.strip()
        if real_path:
            internal_path = real_path
    except ADBError:
        pass
    
    roots[internal_path] = "Interno"
    seen_real_paths.add(internal_path)
    
    # Find external SD cards in /storage/
    try:
        output = shell_command('ls -1 /storage/ 2>/dev/null', device_serial)
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line or line in ['emulated', 'self']:
                continue
            
            potential_path = f'/storage/{line}'
            
            # Resolve to real path to avoid symlinks
            try:
                real_output = shell_command(f'readlink -f "{potential_path}" 2>/dev/null', device_serial)
                real_path = real_output.strip()
                if not real_path:
                    real_path = potential_path
            except ADBError:
                real_path = potential_path
            
            # Skip if we've already seen this real path
            if real_path in seen_real_paths:
                continue
            
            # Check if it's a valid directory
            try:
                check = shell_command(f'[ -d "{potential_path}" ] && echo "ok"', device_serial)
                if 'ok' in check:
                    # Use the real path, name it by the visible name
                    roots[potential_path] = f"SD Card ({line})"
                    seen_real_paths.add(real_path)
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
                'files': 0,
                'photos': 0,
                'videos': 0,
                'size': 0,
                'file_list': []
            }
        
        # Track total files
        folder_stats[top_level_path]['files'] += 1
        folder_stats[top_level_path]['size'] += file_info['size']
        folder_stats[top_level_path]['file_list'].append(file_info)
        
        # Categorize file for stats
        is_media, media_type = is_media_file(file_info['name'])
        if is_media:
            if media_type == 'photo':
                folder_stats[top_level_path]['photos'] += 1
            else:
                folder_stats[top_level_path]['videos'] += 1
    
    # Create MediaFolder objects
    folders = []
    for path, stats in folder_stats.items():
        folder = MediaFolder(
            path=path,
            name=stats['name'],
            file_count=stats['files'],
            photo_count=stats['photos'],
            video_count=stats['videos'],
            total_size=stats['size'],
            storage_type=storage_type,
            storage_root=storage_root,
            files=stats['file_list']
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
    categories: list[str] = None,
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
        categories: List of categories to scan (default: ['media']).
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
    all_files_scanned = []  # Track all files for stats
    
    # Determine extensions to scan
    categories = categories or ['media']
    extensions, include_other = get_extensions_for_categories(categories)
    
    # If "other" is included, we need to scan everything
    scan_extensions = {'*'} if include_other else extensions
    
    for idx, (root, storage_type) in enumerate(storage_roots.items()):
        if progress_callback:
            progress_callback(f"Scansione {storage_type}...", idx, total_roots)
        
        # Use fast find command
        files = find_media_files(
            storage_root=root,
            extensions=scan_extensions,
            device_serial=device_serial,
            exclude_patterns=SKIP_DIRECTORIES
        )
        
        # Filter files if needed (especially for "Other" category logic)
        if files:
            filtered_files = [
                f for f in files 
                if is_file_in_categories(f['name'], categories)
            ]
            files = filtered_files
            all_files_scanned.extend(files)  # Track for stats
        
        if progress_callback:
            progress_callback(f"Analisi {len(files)} file da {storage_type}...", idx, total_roots)
        
        if files:
            folders = aggregate_files_to_folders(files, root, storage_type)
            all_folders.extend(folders)
    
    # Sort by total count descending
    all_folders.sort(key=lambda f: f.total_count, reverse=True)
    
    # Calculate totals and file type statistics
    total_photos = sum(f.photo_count for f in all_folders)
    total_videos = sum(f.video_count for f in all_folders)
    total_files = sum(f.file_count for f in all_folders)
    total_size = sum(f.total_size for f in all_folders)
    
    # Calculate file type breakdown from all scanned files
    file_stats = {}
    for file_info in all_files_scanned:
        subcat = get_file_subcategory(file_info['name'])
        file_stats[subcat] = file_stats.get(subcat, 0) + 1
    
    return ScanResult(
        folders=all_folders,
        total_photos=total_photos,
        total_videos=total_videos,
        total_files=total_files,
        total_size=total_size,
        file_stats=file_stats
    )


def get_all_media_files(
    folder: MediaFolder, 
    categories: list[str] = None,
    device_serial: Optional[str] = None
) -> list[dict]:
    """
    Get all media files from a folder using fast find command.
    
    Args:
        folder: MediaFolder to get files from.
        categories: List of categories to find.
        device_serial: Optional device serial.
    
    Returns:
        List of file info dicts with path, size, mtime.
    """
    categories = categories or ['media']
    extensions, include_other = get_extensions_for_categories(categories)
    scan_extensions = {'*'} if include_other else extensions
    
    files = find_media_files(
        storage_root=folder.path,
        extensions=scan_extensions,
        device_serial=device_serial,
        exclude_patterns=SKIP_DIRECTORIES
    )
    
    # Filter files strictly
    return [
        f for f in files 
        if is_file_in_categories(f['name'], categories)
    ]
