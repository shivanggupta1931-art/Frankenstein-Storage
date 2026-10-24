"""StorageProvider abstract base class."""

from abc import ABC, abstractmethod
from typing import Any


class StorageProvider(ABC):
    @abstractmethod
    def get_usage(self) -> dict[str, Any]:
        """Returns storage usage: {'total': int, 'used': int, 'free': int, 'source': str}."""
        pass

    @abstractmethod
    def put_chunk(self, chunk_id: str, data: bytes) -> None:
        """Stores chunk data atomically."""
        pass

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> bytes:
        """Retrieves raw chunk data."""
        pass

    @abstractmethod
    def delete_chunk(self, chunk_id: str) -> bool:
        """Deletes a chunk by ID. Returns True if deleted, False if not found."""
        pass

    @abstractmethod
    def check_availability(self) -> bool:
        """Checks if provider is reachable and operational."""
        pass

    def get_device_info(self) -> dict[str, Any]:
        """Returns device and volume metadata for de-duplication."""
        return {
            "device_id": None,
            "st_dev": None,
            "mount_point": None,
            "volume_name": None,
        }
