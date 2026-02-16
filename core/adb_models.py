"""
ADB Data Models Module
Data classes for ADB-related types.
"""

from dataclasses import dataclass


@dataclass
class Device:
    """Represents a connected Android device."""
    serial: str
    model: str
    status: str


class ADBError(Exception):
    """Exception raised for ADB-related errors."""
    pass


class DeviceDisconnectedError(ADBError):
    """Exception raised when the device is disconnected during an operation."""
    pass
