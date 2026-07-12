import pytest

import pylontech
from conftest import read_fixture


def test_detail_capacity_and_cycles():
    detail = pylontech.PwrDetailCommand(read_fixture("pwr_detail_pack1.txt"))
    assert detail.total_capacity == pytest.approx(100.0)  # 100000 mAh -> 100 Ah
    assert detail.cycle_count == 40471
    assert detail.max_voltage == pytest.approx(54.0)  # 54000 mV -> 54 V


def test_detail_statuses():
    detail = pylontech.PwrDetailCommand(read_fixture("pwr_detail_pack1.txt"))
    assert detail.soh_status == "Normal"
    assert detail.heater_status == "OFF"
    assert detail.system_fault == "0x0"


def test_detail_ignores_unknown_lines_gracefully():
    detail = pylontech.PwrDetailCommand([" ----------------------------", " Power  1"])
    assert detail.total_capacity is None
    assert detail.cycle_count is None
