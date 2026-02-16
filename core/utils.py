"""
Shared Utilities Module
Common utility functions used across the application.
"""


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"
