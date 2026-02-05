"""
Manifest Module
Tracks synchronized files to enable incremental backups.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime


MANIFEST_FILENAME = ".backup_manifest.json"


@dataclass
class FileEntry:
    """Represents a synchronized file entry in the manifest."""
    remote_path: str
    local_path: str
    size: int
    mtime: str  # Modification time as string from device
    synced_at: str  # ISO timestamp when file was synced
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileEntry':
        return cls(**data)


class Manifest:
    """
    Manages the backup manifest file that tracks synchronized files.
    
    The manifest is stored as a JSON file in the backup destination directory.
    It enables incremental backups by tracking which files have already been synced.
    """
    
    def __init__(self, backup_dir: str):
        """
        Initialize manifest for a backup directory.
        
        Args:
            backup_dir: Path to the backup destination directory.
        """
        self.backup_dir = backup_dir
        self.manifest_path = os.path.join(backup_dir, MANIFEST_FILENAME)
        self.entries: dict[str, FileEntry] = {}  # remote_path -> FileEntry
        self.metadata: dict = {
            'version': 1,
            'created_at': None,
            'last_sync': None,
            'device_serial': None,
            'device_model': None
        }
        
        self._load()
    
    def _load(self):
        """Load manifest from disk if it exists."""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.metadata = data.get('metadata', self.metadata)
                entries_data = data.get('entries', {})
                
                for remote_path, entry_data in entries_data.items():
                    self.entries[remote_path] = FileEntry.from_dict(entry_data)
                    
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # Corrupted manifest, start fresh
                print(f"Warning: Could not load manifest, starting fresh: {e}")
                self.entries = {}
    
    def save(self):
        """Save manifest to disk."""
        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)
        
        data = {
            'metadata': self.metadata,
            'entries': {path: entry.to_dict() for path, entry in self.entries.items()}
        }
        
        # Write to temp file first, then rename for atomicity
        temp_path = self.manifest_path + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        os.replace(temp_path, self.manifest_path)
    
    def set_device_info(self, serial: str, model: str):
        """Set device information in manifest metadata."""
        self.metadata['device_serial'] = serial
        self.metadata['device_model'] = model
        if not self.metadata['created_at']:
            self.metadata['created_at'] = datetime.now().isoformat()
    
    def update_last_sync(self):
        """Update last sync timestamp."""
        self.metadata['last_sync'] = datetime.now().isoformat()
    
    def is_synced(self, remote_path: str, size: int, mtime: str) -> bool:
        """
        Check if a file is already synced with matching size and mtime.
        
        Args:
            remote_path: Path on the device.
            size: File size in bytes.
            mtime: Modification time string.
        
        Returns:
            True if file is already synced and unchanged.
        """
        if remote_path not in self.entries:
            return False
        
        entry = self.entries[remote_path]
        
        # Check if size matches
        if entry.size != size:
            return False
        
        # Check if mtime matches (comparing strings)
        if entry.mtime != mtime:
            return False
        
        # Also verify local file still exists
        if not os.path.exists(entry.local_path):
            return False
        
        return True
    
    def add_entry(self, remote_path: str, local_path: str, size: int, mtime: str):
        """
        Add or update an entry in the manifest.
        
        Args:
            remote_path: Path on the device.
            local_path: Path where file was saved locally.
            size: File size in bytes.
            mtime: Modification time string.
        """
        self.entries[remote_path] = FileEntry(
            remote_path=remote_path,
            local_path=local_path,
            size=size,
            mtime=mtime,
            synced_at=datetime.now().isoformat()
        )
    
    def remove_entry(self, remote_path: str):
        """Remove an entry from the manifest."""
        if remote_path in self.entries:
            del self.entries[remote_path]
    
    def get_synced_count(self) -> int:
        """Get count of synced files."""
        return len(self.entries)
    
    def get_synced_size(self) -> int:
        """Get total size of synced files."""
        return sum(entry.size for entry in self.entries.values())
    
    def get_stats(self) -> dict:
        """Get manifest statistics."""
        return {
            'total_files': len(self.entries),
            'total_size': self.get_synced_size(),
            'created_at': self.metadata.get('created_at'),
            'last_sync': self.metadata.get('last_sync'),
            'device_serial': self.metadata.get('device_serial'),
            'device_model': self.metadata.get('device_model')
        }
    
    def clear(self):
        """Clear all entries from manifest."""
        self.entries = {}
