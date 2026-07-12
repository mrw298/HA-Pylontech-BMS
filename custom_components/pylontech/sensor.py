"""Pylontech (high voltage) BMS sensors."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, KEY_COORDINATOR
from .coordinator import PylontechUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


# Sensor mapping: sensor_key -> (name, device_class, unit, state_class)
SENSOR_MAPPINGS: dict[str, tuple[str, SensorDeviceClass | None, str | None, SensorStateClass | None]] = {
    # Pack-level measurements
    "pack_voltage": ("Pack Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "pack_current": ("Pack Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, SensorStateClass.MEASUREMENT),
    "soc": ("State of Charge", SensorDeviceClass.BATTERY, PERCENTAGE, SensorStateClass.MEASUREMENT),
    "power": ("Power", SensorDeviceClass.POWER, UnitOfPower.WATT, SensorStateClass.MEASUREMENT),

    # Capacity (Ah is charge, not energy, so don't use ENERGY_STORAGE device class)
    "remaining_capacity": ("Remaining Capacity", None, "Ah", SensorStateClass.MEASUREMENT),
    "total_capacity": ("Total Capacity", None, "Ah", SensorStateClass.MEASUREMENT),

    # Temperatures
    "avg_temperature": ("Average Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_average": ("Temperature Average", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_pack": ("Pack Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_cell_low": ("Lowest Cell Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_cell_high": ("Highest Cell Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_unit_low": ("Lowest Unit Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_unit_high": ("Highest Unit Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),

    # Temperature sensors (binary protocol - grouped by cell ranges)
    "temp_cells_1_4": ("Temperature Cells 1-4", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_cells_5_8": ("Temperature Cells 5-8", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_cells_9_12": ("Temperature Cells 9-12", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_cells_13_16": ("Temperature Cells 13-16", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_mos": ("MOSFET Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "temp_env": ("Environment Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),

    # Voltage extremes
    "cell_volt_low": ("Lowest Cell Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "cell_volt_high": ("Highest Cell Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "unit_volt_low": ("Lowest Unit Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "unit_volt_high": ("Highest Unit Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),

    # Temperature extremes
    "cell_temp_low": ("Lowest Cell Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "cell_temp_high": ("Highest Cell Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "unit_temp_low": ("Lowest Unit Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "unit_temp_high": ("Highest Unit Temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),

    # DC voltage (console protocol)
    "dc_voltage": ("DC Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "bat_voltage": ("Battery Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),

    # Charge metrics (console protocol)
    "charge_ah": ("Charge (Ah)", None, "Ah", SensorStateClass.MEASUREMENT),
    "charge_ah_perc": ("Charge Percentage (Ah)", None, PERCENTAGE, SensorStateClass.MEASUREMENT),
    "charge_wh": ("Charge (Wh)", SensorDeviceClass.ENERGY, UnitOfEnergy.WATT_HOUR, SensorStateClass.MEASUREMENT),
    "charge_wh_perc": ("Charge Percentage (Wh)", None, PERCENTAGE, SensorStateClass.MEASUREMENT),

    # States (console protocol)
    "base_state": ("Base State", None, None, None),
    "volt_state": ("Voltage State", None, None, None),
    "curr_state": ("Current State", None, None, None),
    "temp_state": ("Temperature State", None, None, None),
    "cell_volt_state": ("Cell Voltage State", None, None, None),
    "cell_temp_state": ("Cell Temperature State", None, None, None),
    "unit_volt_state": ("Unit Voltage State", None, None, None),
    "unit_temp_state": ("Unit Temperature State", None, None, None),
    "error_code": ("Error Code", None, None, None),

    # Cycle count (binary protocol)
    "cycle_count": ("Cycle Count", None, "cycles", SensorStateClass.TOTAL_INCREASING),

    # Cells balancing (console bat command)
    "cells_balancing": ("Cells Balancing", None, "cells", SensorStateClass.MEASUREMENT),

    # Status groups (binary protocol) - show active flags or "Normal"
    "protect_status": ("Protection Status", None, None, None),
    "system_status": ("System Status", None, None, None),
    "fault_status": ("Fault Status", None, None, None),
    "alarm_status": ("Alarm Status", None, None, None),
}


def _get_sensor_name(sensor_key: str) -> str:
    """Get human-readable sensor name from sensor key.

    Args:
        sensor_key: Sensor identifier

    Returns:
        Human-readable name
    """
    # Check predefined mappings first
    if sensor_key in SENSOR_MAPPINGS:
        return SENSOR_MAPPINGS[sensor_key][0]

    # Handle dynamic sensors (cell voltages, temp sensors)
    if sensor_key.startswith("cell_voltage_"):
        idx = sensor_key.split("_")[-1]
        return f"Cell {idx} Voltage"

    if sensor_key.startswith("temp_sensor_"):
        idx = sensor_key.split("_")[-1]
        return f"Temperature Sensor {idx}"

    # Fallback: convert snake_case to Title Case
    return sensor_key.replace("_", " ").title()


def _get_sensor_description(sensor_key: str, sensor_value_type: type) -> SensorEntityDescription:
    """Get sensor entity description from sensor key and value type.

    Args:
        sensor_key: Sensor identifier
        sensor_value_type: Type of sensor value (int, float, str, bool)

    Returns:
        SensorEntityDescription configured for this sensor
    """
    # Check predefined mappings
    if sensor_key in SENSOR_MAPPINGS:
        name, device_class, unit, state_class = SENSOR_MAPPINGS[sensor_key]
        # Set 3 decimal precision for all voltage sensors
        precision = 3 if device_class == SensorDeviceClass.VOLTAGE else None
        return SensorEntityDescription(
            key=sensor_key,
            name=name,
            device_class=device_class,
            native_unit_of_measurement=unit,
            state_class=state_class,
            suggested_display_precision=precision,
        )

    # Handle dynamic cell voltages
    if sensor_key.startswith("cell_voltage_"):
        return SensorEntityDescription(
            key=sensor_key,
            name=_get_sensor_name(sensor_key),
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=3,
        )

    # Handle dynamic temperature sensors (fallback for unexpected sensors)
    if sensor_key.startswith("temp_sensor_"):
        return SensorEntityDescription(
            key=sensor_key,
            name=_get_sensor_name(sensor_key),
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
        )

    # Fallback based on value type
    if sensor_value_type in (int, float):
        return SensorEntityDescription(
            key=sensor_key,
            name=_get_sensor_name(sensor_key),
            state_class=SensorStateClass.MEASUREMENT,
        )
    else:
        return SensorEntityDescription(
            key=sensor_key,
            name=_get_sensor_name(sensor_key),
        )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor entities from a config entry."""
    coordinator: PylontechUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        KEY_COORDINATOR
    ]

    entities: list[PylontechSensorEntity] = []

    # Create sensors for each pack based on what's actually available in that pack
    for pack_id in range(1, coordinator.pack_count + 1):
        # Get sensors available for this specific pack
        pack_sensors = coordinator.available_sensors_per_pack.get(pack_id, {})

        if not pack_sensors:
            _LOGGER.warning("No sensors detected for pack %d, skipping entity creation", pack_id)
            continue

        for sensor_key, sensor_value_type in pack_sensors.items():
            # Create sensor entity for this pack
            description = _get_sensor_description(sensor_key, sensor_value_type)
            entities.append(
                PylontechSensorEntity(
                    coordinator=coordinator,
                    description=description,
                    sensor_key=sensor_key,
                    pack_id=pack_id,
                )
            )

    _LOGGER.info("Created %d sensor entities across %d packs", len(entities), coordinator.pack_count)
    async_add_entities(entities)


class PylontechSensorEntity(
    CoordinatorEntity[PylontechUpdateCoordinator], SensorEntity
):
    """Representation of a Pylontech BMS sensor."""

    def __init__(
        self,
        coordinator: PylontechUpdateCoordinator,
        description: SensorEntityDescription,
        sensor_key: str,
        pack_id: int,
    ) -> None:
        """Initialize the sensor entity.

        Args:
            coordinator: Update coordinator
            description: Sensor entity description
            sensor_key: Sensor identifier in coordinator data
            pack_id: Pack ID (1-based)
        """
        super().__init__(coordinator)
        self.entity_description = description
        self._sensor_key = sensor_key
        self._pack_id = pack_id

        # Set unique ID including pack ID
        # Added v2 suffix to force recreation of entities with correct naming
        self._attr_unique_id = f"{sensor_key}-pack{pack_id}-{coordinator.serial_nr}-v2"

        # Set device info for this pack to group entities under pack devices
        pack_idx = pack_id - 1  # Convert to 0-based index
        if pack_idx < len(coordinator.pack_device_infos):
            self._attr_device_info = coordinator.pack_device_infos[pack_idx]
        else:
            _LOGGER.error("Pack index %d out of range", pack_idx)

        # Set suggested_object_id to control entity_id generation
        # This is the proper way to set entity_id in Home Assistant
        # Remove special characters that Home Assistant doesn't allow in entity IDs
        device_name_clean = coordinator.device_name.lower().replace(" ", "_").replace("-", "_")
        sensor_name_clean = description.name.lower().replace(" ", "_").replace(":", "").replace("-", "_")
        # Remove any double underscores
        sensor_name_clean = "_".join(filter(None, sensor_name_clean.split("_")))

        self._attr_suggested_object_id = f"{device_name_clean}_pack_{pack_id}_{sensor_name_clean}"
        self._attr_has_entity_name = True  # Use device name in friendly name

    @property
    def native_value(self):
        """Return the value reported by the sensor."""
        return self.coordinator.sensor_value(self._sensor_key, self._pack_id)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        pack_key = f"pack_{self._pack_id}"
        return (
            self.coordinator.last_update_success
            and pack_key in self.coordinator.data
            and self._sensor_key in self.coordinator.data[pack_key]
        )
