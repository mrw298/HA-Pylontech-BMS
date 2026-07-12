"""Data models for Pylontech BMS integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import BatteryVariant, ConnectionType


@dataclass
class BatteryData:
    """Unified battery data model across protocols."""

    # Pack-level measurements
    pack_voltage: float
    pack_current: float
    soc: int  # State of charge percentage

    # Capacity
    remaining_capacity: float  # Ah
    total_capacity: float  # Ah

    # Power (calculated or provided)
    power: float | None = None  # W

    # Temperatures
    temperatures: dict[str, float] = field(default_factory=dict)  # {name: temp_c}
    avg_temperature: float | None = None

    # Cell-level data
    cell_voltages: list[float] = field(default_factory=list)  # V
    cell_temps: list[float] = field(default_factory=list)  # C

    # Battery state
    base_state: str | None = None
    volt_state: str | None = None
    curr_state: str | None = None
    temp_state: str | None = None

    # Cell states
    cell_volt_state: str | None = None
    cell_temp_state: str | None = None

    # Unit states (for multi-BMU systems)
    unit_volt_state: str | None = None
    unit_temp_state: str | None = None

    # Charge metrics
    charge_ah: float | None = None  # Ah
    charge_ah_perc: int | None = None  # %
    charge_wh: float | None = None  # Wh
    charge_wh_perc: int | None = None  # %

    # Voltage extremes
    cell_volt_low: float | None = None  # V
    cell_volt_high: float | None = None  # V
    unit_volt_low: float | None = None  # V
    unit_volt_high: float | None = None  # V

    # Temperature extremes
    cell_temp_low: float | None = None  # C
    cell_temp_high: float | None = None  # C
    unit_temp_low: float | None = None  # C
    unit_temp_high: float | None = None  # C

    # DC voltage (for console protocol)
    dc_voltage: float | None = None  # V
    bat_voltage: float | None = None  # V

    # Status groups (binary protocol) - strings showing active flags or "Normal"
    status_groups: dict[str, str] = field(default_factory=dict)

    # Cycle count (binary protocol)
    cycle_count: int | None = None

    # Error code (console protocol)
    error_code: str | None = None

    # Cells actively balancing (console bat command)
    cells_balancing: int | None = None


@dataclass
class DeviceInfo:
    """Device information model."""

    manufacturer: str
    model: str
    barcode: str
    firmware_version: str
    connection_type: ConnectionType
    variant: BatteryVariant

    # Optional fields
    device_name: str | None = None
    hardware_version: str | None = None
    device_address: int | None = None
    pack_count: int | None = None
    cell_count: int | None = None
    max_charge_current: float | None = None  # A
    max_discharge_current: float | None = None  # A

    # BMU (Battery Management Unit) information
    bmu_modules: list[str] = field(default_factory=list)
    bmu_pcbas: list[str] = field(default_factory=list)

    def to_hass_device_info(self) -> dict[str, Any]:
        """Convert to Home Assistant device info format."""
        return {
            "identifiers": {(f"pylontech_{self.barcode}",)},
            "name": f"Pylontech {self.barcode}",
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": self.firmware_version,
            "hw_version": self.hardware_version,
        }


@dataclass
class BMUData:
    """Battery Management Unit (individual module) data."""

    index: int
    volt: float  # V
    curr: float  # A
    temp: float  # C

    # Cell extremes
    cell_temp_low: float  # C
    cell_temp_high: float  # C
    cell_volt_low: float  # V
    cell_volt_high: float  # V

    # States
    base_state: str
    volt_state: str
    temp_state: str

    # Charge metrics
    charge_ah_perc: int  # %
    charge_ah: float  # Ah
    charge_wh_perc: int  # %
    charge_wh: float  # Wh
