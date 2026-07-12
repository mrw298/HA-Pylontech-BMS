"""Abstract base protocol interface for Pylontech BMS communication."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import BatteryData, DeviceInfo


class ProtocolBase(ABC):
    """Abstract base class for BMS communication protocols."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to BMS.

        Raises:
            ConnectionError: If connection cannot be established.
            TimeoutError: If connection times out.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Close BMS connection.

        Should be safe to call even if not connected.
        """

    @abstractmethod
    async def get_device_info(self, pack_id: int | None = None) -> DeviceInfo:
        """Retrieve device information.

        Args:
            pack_id: Optional pack ID (1-based) to fetch per-pack info for.
                Protocols that do not support per-pack info may ignore it.

        Returns:
            DeviceInfo: Device metadata including manufacturer, model, version, etc.

        Raises:
            ConnectionError: If not connected or communication fails.
            ValueError: If response data is invalid.
        """

    @abstractmethod
    async def get_battery_data(self) -> BatteryData:
        """Fetch current battery telemetry.

        Returns:
            BatteryData: Complete battery state including voltage, current, SOC, temps, etc.

        Raises:
            ConnectionError: If not connected or communication fails.
            ValueError: If response data is invalid.
        """

    async def __aenter__(self) -> ProtocolBase:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<{self.__class__.__name__}>"
