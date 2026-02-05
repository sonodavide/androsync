"""
ADB Wrapper Module
Handles all communication with Android devices via ADB.
"""

import subprocess
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Device:
    """Represents a connected Android device."""
    serial: str
    model: str
    status: str


class ADBError(Exception):
    """Exception raised for ADB-related errors."""
    pass


def check_adb_available() -> bool:
    """Check if ADB is installed and available in PATH."""
    try:
        result = subprocess.run(
            ["adb", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_connected_devices() -> list[Device]:
    """
    Get list of connected Android devices.
    
    Returns:
        List of Device objects for each connected device.
    
    Raises:
        ADBError: If ADB command fails.
    """
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise ADBError(f"ADB command failed: {result.stderr}")
        
        devices = []
        lines = result.stdout.strip().split('\n')[1:]  # Skip header line
        
        for line in lines:
            if not line.strip():
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                status = parts[1]
                
                # Extract model from device info
                model = "Unknown"
                model_match = re.search(r'model:(\S+)', line)
                if model_match:
                    model = model_match.group(1).replace('_', ' ')
                
                devices.append(Device(serial=serial, model=model, status=status))
        
        return devices
    
    except subprocess.TimeoutExpired:
        raise ADBError("ADB command timed out")
    except FileNotFoundError:
        raise ADBError("ADB not found. Please install Android SDK Platform Tools.")


def get_single_device() -> Optional[Device]:
    """
    Get the single connected device, or None if not exactly one device.
    
    Returns:
        Device object if exactly one device is connected, None otherwise.
    """
    devices = get_connected_devices()
    authorized = [d for d in devices if d.status == "device"]
    
    if len(authorized) == 1:
        return authorized[0]
    return None


def shell_command(command: str, device_serial: Optional[str] = None) -> str:
    """
    Execute a shell command on the Android device.
    
    Args:
        command: Shell command to execute.
        device_serial: Optional device serial (required if multiple devices).
    
    Returns:
        Command output as string.
    
    Raises:
        ADBError: If command fails.
    """
    cmd = ["adb"]
    if device_serial:
        cmd.extend(["-s", device_serial])
    cmd.extend(["shell", command])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout for long operations
        )
        
        if result.returncode != 0:
            raise ADBError(f"Shell command failed: {result.stderr}")
        
        return result.stdout
    
    except subprocess.TimeoutExpired:
        raise ADBError(f"Command timed out: {command}")


def pull_file(remote_path: str, local_path: str, device_serial: Optional[str] = None) -> bool:
    """
    Pull a file from the Android device to local filesystem.
    
    Args:
        remote_path: Path on the Android device.
        local_path: Local destination path.
        device_serial: Optional device serial.
    
    Returns:
        True if successful, False otherwise.
    
    Raises:
        ADBError: If pull fails.
    """
    cmd = ["adb"]
    if device_serial:
        cmd.extend(["-s", device_serial])
    cmd.extend(["pull", remote_path, local_path])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout for large files
        )
        
        return result.returncode == 0
    
    except subprocess.TimeoutExpired:
        raise ADBError(f"Pull timed out for: {remote_path}")


def list_files(path: str, device_serial: Optional[str] = None) -> list[dict]:
    """
    List files in a directory on the Android device with details.
    
    Args:
        path: Directory path on the device.
        device_serial: Optional device serial.
    
    Returns:
        List of dicts with keys: name, size, mtime, is_dir
    """
    # Use ls -la for detailed listing
    output = shell_command(f'ls -la "{path}" 2>/dev/null', device_serial)
    
    files = []
    for line in output.strip().split('\n'):
        if not line or line.startswith('total'):
            continue
        
        # Parse ls -la output
        # Format: drwxrwx--- 2 root sdcard_rw 4096 2024-01-15 10:30 dirname
        parts = line.split()
        if len(parts) < 7:
            continue
        
        permissions = parts[0]
        is_dir = permissions.startswith('d')
        
        try:
            size = int(parts[4])
        except (ValueError, IndexError):
            size = 0
        
        # Date and time are in parts[5] and parts[6]
        try:
            mtime = f"{parts[5]} {parts[6]}"
        except IndexError:
            mtime = ""
        
        # Name is everything after the time (handles spaces in names)
        name_parts = parts[7:]
        if not name_parts:
            continue
        name = ' '.join(name_parts)
        
        # Skip . and ..
        if name in ['.', '..']:
            continue
        
        files.append({
            'name': name,
            'size': size,
            'mtime': mtime,
            'is_dir': is_dir,
            'path': f"{path.rstrip('/')}/{name}"
        })
    
    return files


def get_file_stat(path: str, device_serial: Optional[str] = None) -> Optional[dict]:
    """
    Get file statistics for a single file.
    
    Args:
        path: File path on the device.
        device_serial: Optional device serial.
    
    Returns:
        Dict with size and mtime, or None if file doesn't exist.
    """
    try:
        output = shell_command(f'stat -c "%s %Y" "{path}" 2>/dev/null', device_serial)
        parts = output.strip().split()
        if len(parts) >= 2:
            return {
                'size': int(parts[0]),
                'mtime': int(parts[1])
            }
    except (ADBError, ValueError):
        pass
    return None
