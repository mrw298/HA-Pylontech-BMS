"""TCP Console Protocol implementation for Pylontech BMS.

This module implements the text-based console protocol over TCP.
Commands: pwr, unit, bat, info
Response format: ASCII text with 'pylon>' prompt
"""

from __future__ import annotations

import asyncio
from asyncio import StreamReader, StreamWriter
import logging
from typing import Any

from .base import ProtocolBase
from ..const import BatteryVariant, ConnectionType
from ..models import BatteryData, BMUData, DeviceInfo

# Import all sensor and command classes from parent pylontech module
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pylontech import (
    BatCommand,
    InfoCommand,
    PwrCommand,
    PwrDetailCommand,
    PwrTableCommand,
    UnitCommand,
    Sensor,
    is_flat_pwr,
)

_LOGGER = logging.getLogger(__name__)


class TCPConsoleProtocol(ProtocolBase):
    """Pylontech BMS TCP console protocol implementation.

    Uses text-based commands over TCP connection (default port 1234).
    Commands: pwr, unit, bat, info
    """

    _END_PROMPTS = ("Command completed successfully", "$$")

    def __init__(self, host: str, port: int) -> None:
        """Initialize the TCP console protocol.

        Args:
            host: BMS hostname or IP address
            port: TCP port (typically 1234)
        """
        self.host = host
        self.port = port
        self.reader: StreamReader | None = None
        self.writer: StreamWriter | None = None
        # Cached flat `pwr` response for the current connection (cleared on
        # connect/disconnect) so pack_count and every per-pack fetch reuse it.
        self._pwr_lines: tuple[str, ...] | None = None

    async def connect(self) -> None:
        """Establish TCP connection to BMS console."""
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), 5
        )
        self._pwr_lines = None
        _LOGGER.debug("Connected to %s:%s", self.host, self.port)

    async def disconnect(self) -> None:
        """Close TCP connection."""
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            self.reader = None
            self.writer = None
            self._pwr_lines = None
            _LOGGER.debug("Disconnected from %s:%s", self.host, self.port)

    async def _exec_cmd(self, cmd: str) -> tuple[str]:
        """Send command to BMS and parse response.

        Args:
            cmd: Command string to send

        Returns:
            Tuple of response lines

        Raises:
            ValueError: If response format is invalid
        """
        # Device requires CR+LF; CR alone is not accepted over ser2net bridges.
        self.writer.write((cmd + "\r\n").encode("ascii"))
        await asyncio.wait_for(self.writer.drain(), 2)
        lines = []
        linebytes = bytearray()
        while linebytes != b"pylon>":
            # Read in smaller chunks (Linux compatibility)
            data = await asyncio.wait_for(self.reader.read(120), 2)
            for i in data:
                # Handle mixed LF and CR+LF line endings
                if i not in (13, 10):
                    linebytes.append(i)
                elif len(linebytes) > 0:
                    # Tolerate occasional serial line noise: a stray non-ASCII
                    # byte becomes a replacement char and the malformed line is
                    # skipped downstream rather than failing the whole read.
                    line = linebytes.decode("ascii", errors="replace")
                    if line not in self._END_PROMPTS:
                        lines.append(line)
                    linebytes = bytearray()
        if lines.pop(0) != cmd:
            raise ValueError("Command echo mismatch")
        if lines.pop(0) != "@":
            raise ValueError("Missing @ separator")
        return tuple(lines)

    async def bat(self) -> BatCommand:
        """Invoke 'bat' console command."""
        return BatCommand(await self._exec_cmd("bat"))

    async def info(self) -> InfoCommand:
        """Invoke 'info' console command."""
        return InfoCommand(await self._exec_cmd("info"))

    async def pwr(self) -> PwrCommand:
        """Invoke 'pwr' console command."""
        return PwrCommand(await self._exec_cmd("pwr"))

    async def unit(self) -> UnitCommand:
        """Invoke 'unit' console command."""
        return UnitCommand(await self._exec_cmd("unit"))

    async def _pwr_table_lines(self) -> tuple[str, ...]:
        """Fetch the flat `pwr` response once per connection and cache it."""
        if self._pwr_lines is None:
            self._pwr_lines = await self._exec_cmd("pwr")
        return self._pwr_lines

    async def get_device_info(self) -> DeviceInfo:
        """Retrieve device information from info command.

        Returns:
            DeviceInfo with manufacturer, model, version, barcode, etc.
        """
        info = await self.info()

        pwr_lines = await self._pwr_table_lines()
        pack_count = (
            PwrTableCommand(pwr_lines).pack_count if is_flat_pwr(pwr_lines) else 1
        )

        return DeviceInfo(
            manufacturer=info.manufacturer.value if info.manufacturer.value else "Pylontech",
            model=info.device_name.value if info.device_name.value else "Unknown",
            barcode=info.module_barcode.value if info.module_barcode.value else "Unknown",
            firmware_version=info.main_sw_version.value if info.main_sw_version.value else "Unknown",
            connection_type=ConnectionType.TCP_CONSOLE,
            variant=BatteryVariant.PYLONTECH_STANDARD,
            pack_count=pack_count,
            device_name=info.device_name.value,
            hardware_version=info.hard_version.value,
            device_address=info.device_address.value,
            cell_count=info.cell_number.value,
            max_charge_current=info.max_charge_current.value,
            max_discharge_current=info.max_discharge_current.value,
            bmu_modules=list(info.bmu_modules),
            bmu_pcbas=list(info.bmu_pcbas),
        )

    async def get_battery_data(self) -> BatteryData:
        """Fetch current battery telemetry from pwr and unit commands.

        Returns:
            BatteryData with all available measurements
        """
        # Fetch both pwr and unit data
        pwr = await self.pwr()
        unit = await self.unit()

        # Build temperature dictionary
        temperatures = {
            "average": pwr.avg_temp.value,
            "pack": pwr.temp.value,
            "cell_low": pwr.cell_temp_low.value,
            "cell_high": pwr.cell_temp_high.value,
            "unit_low": pwr.unit_temp_low.value,
            "unit_high": pwr.unit_temp_high.value,
        }

        # Extract cell voltages and temps from unit data
        cell_voltages = []
        cell_temps = []
        for unit_val in unit.values:
            # Each unit may have cell-level data
            if hasattr(unit_val, 'cell_volt_low') and unit_val.cell_volt_low.value:
                cell_voltages.append(unit_val.cell_volt_low.value)
            if hasattr(unit_val, 'cell_bolt_high') and unit_val.cell_bolt_high.value:
                cell_voltages.append(unit_val.cell_bolt_high.value)
            if hasattr(unit_val, 'cell_temp_low') and unit_val.cell_temp_low.value:
                cell_temps.append(unit_val.cell_temp_low.value)
            if hasattr(unit_val, 'cell_temp_high') and unit_val.cell_temp_high.value:
                cell_temps.append(unit_val.cell_temp_high.value)

        return BatteryData(
            # Pack-level measurements
            pack_voltage=pwr.volt.value,
            pack_current=pwr.curr.value,
            soc=pwr.charge_ah_perc.value,

            # Capacity
            remaining_capacity=pwr.charge_ah.value,
            total_capacity=None,  # Not directly available in console protocol

            # Power (calculated)
            power=pwr.volt.value * pwr.curr.value if pwr.volt.value and pwr.curr.value else None,

            # Temperatures
            temperatures=temperatures,
            avg_temperature=pwr.avg_temp.value,

            # Cell-level data
            cell_voltages=cell_voltages,
            cell_temps=cell_temps,

            # Battery states
            base_state=pwr.base_state.value,
            volt_state=pwr.volt_state.value,
            curr_state=pwr.curr_state.value,
            temp_state=pwr.temp_state.value,

            # Cell states
            cell_volt_state=pwr.cell_volt_state.value,
            cell_temp_state=pwr.cell_temp_state.value,

            # Unit states
            unit_volt_state=pwr.unit_volt_state.value,
            unit_temp_state=pwr.unit_temp_state.value,

            # Charge metrics
            charge_ah=pwr.charge_ah.value,
            charge_ah_perc=pwr.charge_ah_perc.value,
            charge_wh=pwr.charge_wh_wh.value,
            charge_wh_perc=pwr.charge_wh_perc.value,

            # Voltage extremes
            cell_volt_low=pwr.cell_volt_low.value,
            cell_volt_high=pwr.cell_bolt_high.value,
            unit_volt_low=pwr.unit_volt_low.value,
            unit_volt_high=pwr.unit_volt_high.value,

            # Temperature extremes
            cell_temp_low=pwr.cell_temp_low.value,
            cell_temp_high=pwr.cell_temp_high.value,
            unit_temp_low=pwr.unit_temp_low.value,
            unit_temp_high=pwr.unit_temp_high.value,

            # DC voltage
            dc_voltage=pwr.dc_voltage.value,
            bat_voltage=pwr.bat_voltage.value,

            # Error code
            error_code=pwr.error_code.value,

            # Alarms - empty for console protocol
            alarms={},

            # Cycle count - not available in console protocol
            cycle_count=None,
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<TCPConsoleProtocol host={self.host} port={self.port}>"
