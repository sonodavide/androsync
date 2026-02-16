"""
File Scanner Module
Scans Android device for files by category and calculates statistics.
Uses fast find command instead of recursive ls for better performance.
"""

from typing import Optional

from .adb import shell_command, find_media_files, ADBError
from .models import MediaFolder, ScanResult
from .categories import (
    FILE_CATEGORIES, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, MEDIA_EXTENSIONS,
    ALL_KNOWN_EXTENSIONS, SKIP_DIRECTORIES, SKIP_HIDDEN_DIRECTORIES, EXPAND_DIRECTORIES,
    get_extensions_for_categories, get_file_subcategory, is_file_in_categories, is_media_file
)


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


def is_hidden_path(path: str) -> bool:
    """
    Check if path is hidden (file or any parent directory starts with '.').
    
    Args:
        path: File or directory path to check.
    
    Returns:
        True if the path or any component starts with '.' (excluding '.' and '..').
    """
    parts = path.split('/')
    for part in parts:
        if part.startswith('.') and part not in ('.', '..'):
            return True
    return False


def should_expand_directory(relative_path: str) -> bool:
    """Check if a directory should be expanded to show subfolders."""
    for expand in EXPAND_DIRECTORIES:
        if relative_path == expand or relative_path.startswith(expand + '/'):
            return True
    return False


def aggregate_files_to_folders(
    files: list[dict],
    storage_root: str,
    storage_type: str,
    include_hidden: bool = False
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
    # Filter hidden files if needed
    if not include_hidden:
        files = [f for f in files if not is_hidden_path(f['path'])]
    
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
    include_hidden: bool = False,
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
        include_hidden: Whether to include hidden files/directories (starting with '.').
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
        
        # Build exclude list: always skip system dirs, conditionally skip hidden dirs
        exclude = list(SKIP_DIRECTORIES)
        if not include_hidden:
            exclude.extend(SKIP_HIDDEN_DIRECTORIES)
        
        # Use fast find command
        files = find_media_files(
            storage_root=root,
            extensions=scan_extensions,
            device_serial=device_serial,
            exclude_patterns=exclude
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
            folders = aggregate_files_to_folders(files, root, storage_type, include_hidden)
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
    device_serial: Optional[str] = None,
    include_hidden: bool = False
) -> list[dict]:
    """
    Get all media files from a folder using fast find command.
    
    Args:
        folder: MediaFolder to get files from.
        categories: List of categories to find.
        device_serial: Optional device serial.
        include_hidden: Whether to include hidden files/directories.
    
    Returns:
        List of file info dicts with path, size, mtime.
    """
    categories = categories or ['media']
    extensions, include_other = get_extensions_for_categories(categories)
    scan_extensions = {'*'} if include_other else extensions
    
    # Build exclude list based on include_hidden
    exclude = list(SKIP_DIRECTORIES)
    if not include_hidden:
        exclude.extend(SKIP_HIDDEN_DIRECTORIES)
    
    files = find_media_files(
        storage_root=folder.path,
        extensions=scan_extensions,
        device_serial=device_serial,
        exclude_patterns=exclude
    )
    
    # Filter files strictly
    filtered = [
        f for f in files 
        if is_file_in_categories(f['name'], categories)
    ]
    
    # Filter hidden if needed
    if not include_hidden:
        filtered = [f for f in filtered if not is_hidden_path(f['path'])]
    
    return filtered
