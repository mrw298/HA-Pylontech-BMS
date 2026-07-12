"""Update coordinator for Pylontech BMS."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo as HADeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .models import BatteryData, DeviceInfo
from .protocol import ProtocolBase

_LOGGER = logging.getLogger(__name__)


class PylontechUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gather data for the energy device."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        protocol: ProtocolBase,
        device_info: DeviceInfo,
        device_name: str = "Battery",
        pack_infos: dict[int, DeviceInfo] | None = None,
    ) -> None:
        """Initialize update coordinator.

        Args:
            hass: Home Assistant instance
            entry: Config entry
            protocol: Protocol instance (console or binary)
            device_info: Device information from protocol
            device_name: Custom base name for devices (default: "Battery")
            pack_infos: Per-pack device information keyed by pack ID (1-based)
        """
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=SCAN_INTERVAL,
            update_method=self._async_update_data,
        )
        self.protocol = protocol
        self.device_info_model = device_info
        self.pack_infos = pack_infos or {}
        self.pack_count = device_info.pack_count or 1
        self.device_name = device_name

        # Integration identity: prefer a real per-pack barcode over the
        # top-level info's barcode (which may be "Unknown" on some firmware).
        first = self.pack_infos.get(1)
        self.serial_nr = (
            first.barcode
            if first is not None and first.barcode and first.barcode != "Unknown"
            else device_info.barcode
        )

        # Create device info for each pack from that pack's own metadata.
        self.pack_device_infos = tuple(
            _pack_device(self._pack_info(pack_id), pack_id, device_name)
            for pack_id in range(1, self.pack_count + 1)
        )
        # Store available sensors per pack: {pack_id: {sensor_name: type}}
        self.available_sensors_per_pack: dict[int, dict[str, type]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the BMS.

        Returns:
            Dictionary with pack data: {pack_1: {...}, pack_2: {...}, ...}
        """
        try:
            await self.protocol.connect()
            result = {}

            # Query each pack separately
            for pack_id in range(1, self.pack_count + 1):
                try:
                    battery_data = await self.protocol.get_battery_data(pack_id=pack_id)
                    pack_data = self._flatten_battery_data(battery_data)
                    # Store data under pack-specific key
                    result[f"pack_{pack_id}"] = pack_data
                except Exception as err:
                    _LOGGER.warning("Failed to fetch data for pack %d: %s", pack_id, err)
                    # Continue with other packs even if one fails

            return result
        except Exception as ex:
            raise UpdateFailed(ex) from ex
        finally:
            await self.protocol.disconnect()

    def _flatten_battery_data(self, data: BatteryData) -> dict[str, Any]:
        """Flatten BatteryData model to dictionary format.

        Args:
            data: BatteryData from protocol

        Returns:
            Dictionary with sensor keys and values
        """
        result = {}

        # Pack-level measurements
        if data.pack_voltage is not None:
            result["pack_voltage"] = data.pack_voltage
        if data.pack_current is not None:
            result["pack_current"] = data.pack_current
        if data.soc is not None:
            result["soc"] = data.soc
        if data.power is not None:
            result["power"] = data.power

        # Capacity
        if data.remaining_capacity is not None:
            result["remaining_capacity"] = data.remaining_capacity
        if data.total_capacity is not None:
            result["total_capacity"] = data.total_capacity

        # Temperatures
        if data.avg_temperature is not None:
            result["avg_temperature"] = data.avg_temperature
        # Console protocol temperatures (not used in binary protocol)
        # Binary protocol uses cell_temps list below with proper naming
        for temp_name, temp_value in data.temperatures.items():
            result[f"temp_{temp_name}"] = temp_value

        # States (console protocol)
        if data.base_state is not None:
            result["base_state"] = data.base_state
        if data.volt_state is not None:
            result["volt_state"] = data.volt_state
        if data.curr_state is not None:
            result["curr_state"] = data.curr_state
        if data.temp_state is not None:
            result["temp_state"] = data.temp_state
        if data.cell_volt_state is not None:
            result["cell_volt_state"] = data.cell_volt_state
        if data.cell_temp_state is not None:
            result["cell_temp_state"] = data.cell_temp_state
        if data.unit_volt_state is not None:
            result["unit_volt_state"] = data.unit_volt_state
        if data.unit_temp_state is not None:
            result["unit_temp_state"] = data.unit_temp_state

        # Charge metrics
        if data.charge_ah is not None:
            result["charge_ah"] = data.charge_ah
        if data.charge_ah_perc is not None:
            result["charge_ah_perc"] = data.charge_ah_perc
        if data.charge_wh is not None:
            result["charge_wh"] = data.charge_wh
        if data.charge_wh_perc is not None:
            result["charge_wh_perc"] = data.charge_wh_perc

        # Voltage extremes
        if data.cell_volt_low is not None:
            result["cell_volt_low"] = data.cell_volt_low
        if data.cell_volt_high is not None:
            result["cell_volt_high"] = data.cell_volt_high
        if data.cell_volt_delta is not None:
            result["cell_volt_delta"] = data.cell_volt_delta
        if data.unit_volt_low is not None:
            result["unit_volt_low"] = data.unit_volt_low
        if data.unit_volt_high is not None:
            result["unit_volt_high"] = data.unit_volt_high

        # Temperature extremes
        if data.cell_temp_low is not None:
            result["cell_temp_low"] = data.cell_temp_low
        if data.cell_temp_high is not None:
            result["cell_temp_high"] = data.cell_temp_high
        if data.unit_temp_low is not None:
            result["unit_temp_low"] = data.unit_temp_low
        if data.unit_temp_high is not None:
            result["unit_temp_high"] = data.unit_temp_high

        # DC voltage
        if data.dc_voltage is not None:
            result["dc_voltage"] = data.dc_voltage
        if data.bat_voltage is not None:
            result["bat_voltage"] = data.bat_voltage

        # Error code
        if data.error_code is not None:
            result["error_code"] = data.error_code

        # Cycle count (binary protocol)
        if data.cycle_count is not None:
            result["cycle_count"] = data.cycle_count

        # Protection/fault event summary (console stat command)
        if data.protection_events is not None:
            result["protection_events"] = data.protection_events

        # Cells balancing (console bat command)
        if data.cells_balancing is not None:
            result["cells_balancing"] = data.cells_balancing

        # Cell voltages (binary protocol)
        for idx, voltage in enumerate(data.cell_voltages):
            result[f"cell_voltage_{idx}"] = voltage

        # Cell temperatures (binary protocol)
        # Temperature sensors represent: 0=Cells1-4, 1=Cells5-8, 2=Cells9-12, 3=Cells13-16, 4=MOS, 5=ENV
        temp_names = ["temp_cells_1_4", "temp_cells_5_8", "temp_cells_9_12", "temp_cells_13_16", "temp_mos", "temp_env"]
        for idx, temp in enumerate(data.cell_temps):
            if idx < len(temp_names):
                result[temp_names[idx]] = temp
            else:
                result[f"temp_sensor_{idx}"] = temp  # Fallback for unexpected sensors

        # Status groups (binary protocol) - grouped status sensors
        for status_name, status_value in data.status_groups.items():
            result[status_name] = status_value

        return result

    async def detect_sensors(self) -> None:
        """Retrieve all supported sensor names from BMS.

        This populates available_sensors_per_pack by querying each pack
        individually to detect what sensors are actually available.
        """
        try:
            await self.protocol.connect()

            # Query each pack to detect available sensors
            for pack_id in range(1, self.pack_count + 1):
                try:
                    battery_data = await self.protocol.get_battery_data(pack_id=pack_id)
                    result = self._flatten_battery_data(battery_data)

                    # Store available sensors with their value types for this pack
                    pack_sensors = {}
                    for sensor_name, sensor_value in result.items():
                        pack_sensors[sensor_name] = type(sensor_value)

                    self.available_sensors_per_pack[pack_id] = pack_sensors
                except Exception as err:
                    _LOGGER.warning("Failed to detect sensors for pack %d: %s", pack_id, err)
                    # Store empty dict for this pack so we can continue
                    self.available_sensors_per_pack[pack_id] = {}

        finally:
            await self.protocol.disconnect()

    def sensor_value(self, sensor: str, pack_id: int) -> Any:
        """Answer current value of the sensor for a specific pack.

        Args:
            sensor: Sensor name
            pack_id: Pack ID (1-based)

        Returns:
            Current sensor value or None
        """
        pack_key = f"pack_{pack_id}"
        if pack_key not in self.data:
            return None
        return self.data[pack_key].get(sensor)

    def _pack_info(self, pack_id: int) -> DeviceInfo:
        """Return a pack's own DeviceInfo, falling back to the top-level info."""
        return self.pack_infos.get(pack_id, self.device_info_model)

    def pack_serial(self, pack_id: int) -> str:
        """Return the stable per-pack serial (real barcode where available)."""
        return _pack_serial(self._pack_info(pack_id), pack_id)


def _pack_serial(info: DeviceInfo, pack_id: int) -> str:
    """Return a stable, per-pack-unique identifier key.

    Always includes the pack index so distinct packs never collide, even when
    they report the same barcode (e.g. a binary-protocol stack that falls back
    to the shared top-level info, or a console pack whose per-pack info fetch
    failed). Incorporates the real barcode when known.
    """
    base = info.barcode if info.barcode and info.barcode != "Unknown" else "Unknown"
    return f"{base}_pack{pack_id}"


def _pack_device(info: DeviceInfo, pack_id: int, device_name: str = "Battery") -> HADeviceInfo:
    """Create Home Assistant device info for one battery pack.

    Args:
        info: That pack's own DeviceInfo.
        pack_id: Pack ID (1-based).
        device_name: Custom base name for the device (default: "Battery")

    Returns:
        Home Assistant DeviceInfo for the pack.
    """
    pack_key = _pack_serial(info, pack_id)
    display_serial = (
        info.barcode if info.barcode and info.barcode != "Unknown" else pack_key
    )
    return HADeviceInfo(
        identifiers={(DOMAIN, pack_key)},
        name=f"{info.manufacturer} {device_name} Pack {pack_id}",
        model=info.model,
        manufacturer=info.manufacturer,
        sw_version=info.firmware_version,
        hw_version=info.hardware_version,
        serial_number=display_serial,
    )
