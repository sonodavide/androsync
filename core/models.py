"""
Data Models Module
Core dataclasses used throughout the application.
"""

from dataclasses import dataclass, field


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
