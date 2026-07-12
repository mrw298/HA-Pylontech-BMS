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
    BatPackCommand,
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

    async def info(self, pack_id: int | None = None) -> InfoCommand:
        """Invoke the 'info' console command, optionally for one pack."""
        cmd = "info" if pack_id is None else f"info {pack_id}"
        return InfoCommand(await self._exec_cmd(cmd))

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

    async def get_device_info(self, pack_id: int | None = None) -> DeviceInfo:
        """Retrieve device information.

        With no `pack_id`, returns the top-level info and computes `pack_count`
        from the flat `pwr` table. With a `pack_id`, returns that pack's own
        metadata (`info <pack_id>`) and leaves `pack_count` unset.
        """
        info = await self.info(pack_id)

        if pack_id is None:
            pwr_lines = await self._pwr_table_lines()
            pack_count = (
                PwrTableCommand(pwr_lines).pack_count if is_flat_pwr(pwr_lines) else 1
            )
        else:
            pack_count = None

        barcode = info.barcode.value or info.module_barcode.value or "Unknown"
        firmware = info.main_sw_version.value or info.sw_version.value or "Unknown"

        return DeviceInfo(
            manufacturer=info.manufacturer.value if info.manufacturer.value else "Pylontech",
            model=info.device_name.value if info.device_name.value else "Unknown",
            barcode=barcode,
            firmware_version=firmware,
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

    async def get_battery_data(self, pack_id: int = 1) -> BatteryData:
        """Fetch one pack's telemetry.

        Uses the flat multi-pack `pwr` table when present, enriched with the
        `pwr <pack_id>` detail view. Falls back to the legacy single-pack
        parse for devices that return the older header format.
        """
        pwr_lines = await self._pwr_table_lines()
        if is_flat_pwr(pwr_lines):
            return await self._battery_data_flat(pwr_lines, pack_id)
        return await self._battery_data_legacy(pwr_lines)

    async def _battery_data_flat(
        self, pwr_lines: tuple[str, ...], pack_id: int
    ) -> BatteryData:
        """Build BatteryData for one pack from the flat table + detail view."""
        pack = PwrTableCommand(pwr_lines).pack(pack_id)
        if pack is None:
            raise ValueError(f"Pack {pack_id} not present in pwr output")

        detail = PwrDetailCommand(await self._exec_cmd(f"pwr {pack_id}"))

        try:
            bat = BatPackCommand(await self._exec_cmd(f"bat {pack_id}"))
        except Exception:  # noqa: BLE001 - device may not support 'bat <index>'
            bat = None
        cell_voltages = bat.cell_voltages if bat is not None else []
        # A bat reply that parses to zero cells is treated as "unsupported"
        # (None), not a real count of 0, keeping the None-vs-0 distinction.
        cells_balancing = bat.balancing_count if (bat is not None and bat.cells) else None

        remaining = (
            detail.total_capacity * pack.soc / 100
            if detail.total_capacity is not None
            else None
        )

        status_groups: dict[str, str] = {}
        if detail.soh_status is not None:
            status_groups["soh_status"] = detail.soh_status
        if detail.heater_status is not None:
            status_groups["heater_status"] = detail.heater_status
        if detail.system_fault is not None:
            status_groups["system_fault"] = detail.system_fault

        return BatteryData(
            pack_voltage=pack.volt,
            pack_current=pack.curr,
            soc=pack.soc,
            remaining_capacity=remaining,
            total_capacity=detail.total_capacity,
            power=pack.volt * pack.curr,
            temperatures={"pack": pack.temp},
            avg_temperature=None,
            cell_voltages=cell_voltages,
            cell_temps=[],
            base_state=pack.base_state,
            volt_state=pack.volt_state,
            curr_state=pack.curr_state,
            temp_state=pack.temp_state,
            cell_volt_low=pack.cell_volt_low,
            cell_volt_high=pack.cell_volt_high,
            cell_temp_low=pack.cell_temp_low,
            cell_temp_high=pack.cell_temp_high,
            cells_balancing=cells_balancing,
            status_groups=status_groups,
        )

    async def _battery_data_legacy(self, pwr_lines: tuple[str, ...]) -> BatteryData:
        """Legacy single-pack path for the older header-format `pwr` output.

        Preserved for devices that predate the flat multi-pack table. The
        `unit` command is optional here: some devices do not support it.
        """
        pwr = PwrCommand(pwr_lines)

        try:
            unit = await self.unit()
        except Exception:  # noqa: BLE001 - device may not support 'unit'
            unit = None

        cell_voltages = []
        cell_temps = []
        if unit is not None:
            for unit_val in unit.values:
                if hasattr(unit_val, "cell_volt_low") and unit_val.cell_volt_low.value:
                    cell_voltages.append(unit_val.cell_volt_low.value)
                if hasattr(unit_val, "cell_bolt_high") and unit_val.cell_bolt_high.value:
                    cell_voltages.append(unit_val.cell_bolt_high.value)
                if hasattr(unit_val, "cell_temp_low") and unit_val.cell_temp_low.value:
                    cell_temps.append(unit_val.cell_temp_low.value)
                if hasattr(unit_val, "cell_temp_high") and unit_val.cell_temp_high.value:
                    cell_temps.append(unit_val.cell_temp_high.value)

        temperatures = {
            "average": pwr.avg_temp.value,
            "pack": pwr.temp.value,
            "cell_low": pwr.cell_temp_low.value,
            "cell_high": pwr.cell_temp_high.value,
            "unit_low": pwr.unit_temp_low.value,
            "unit_high": pwr.unit_temp_high.value,
        }

        return BatteryData(
            pack_voltage=pwr.volt.value,
            pack_current=pwr.curr.value,
            soc=pwr.charge_ah_perc.value,
            remaining_capacity=pwr.charge_ah.value,
            total_capacity=None,
            power=pwr.volt.value * pwr.curr.value
            if pwr.volt.value and pwr.curr.value
            else None,
            temperatures=temperatures,
            avg_temperature=pwr.avg_temp.value,
            cell_voltages=cell_voltages,
            cell_temps=cell_temps,
            base_state=pwr.base_state.value,
            volt_state=pwr.volt_state.value,
            curr_state=pwr.curr_state.value,
            temp_state=pwr.temp_state.value,
            cell_volt_state=pwr.cell_volt_state.value,
            cell_temp_state=pwr.cell_temp_state.value,
            unit_volt_state=pwr.unit_volt_state.value,
            unit_temp_state=pwr.unit_temp_state.value,
            charge_ah=pwr.charge_ah.value,
            charge_ah_perc=pwr.charge_ah_perc.value,
            charge_wh=pwr.charge_wh_wh.value,
            charge_wh_perc=pwr.charge_wh_perc.value,
            cell_volt_low=pwr.cell_volt_low.value,
            cell_volt_high=pwr.cell_bolt_high.value,
            unit_volt_low=pwr.unit_volt_low.value,
            unit_volt_high=pwr.unit_volt_high.value,
            cell_temp_low=pwr.cell_temp_low.value,
            cell_temp_high=pwr.cell_temp_high.value,
            unit_temp_low=pwr.unit_temp_low.value,
            unit_temp_high=pwr.unit_temp_high.value,
            dc_voltage=pwr.dc_voltage.value,
            bat_voltage=pwr.bat_voltage.value,
            error_code=pwr.error_code.value,
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<TCPConsoleProtocol host={self.host} port={self.port}>"
