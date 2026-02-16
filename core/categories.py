"""
File Categories Module
Defines file type categories, extensions, and classification helpers.
"""

import os


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


def get_extensions_for_categories(categories: list[str]) -> tuple[set[str], bool]:
    """Get combined extensions for selected categories.
    
    Returns:
        Tuple of (extensions_set, include_other_flag)
    """
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
    if '.' not in filename:
        # File without extension - only matches 'other' category
        ext = ''
    else:
        parts = filename.rsplit('.', 1)
        if len(parts) == 2:
            ext = '.' + parts[1].lower()
        else:
            ext = ''
    
    extensions, include_other = get_extensions_for_categories(categories)
    
    if ext and ext in extensions:
        return True
    if include_other and (not ext or ext not in ALL_KNOWN_EXTENSIONS):
        return True
    return False


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
