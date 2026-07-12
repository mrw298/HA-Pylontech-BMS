import pytest

import pylontech
from conftest import read_fixture


def test_bat_parses_fifteen_cells():
    bat = pylontech.BatPackCommand(read_fixture("bat_pack1.txt"))
    assert len(bat.cells) == 15
    assert len(bat.cell_voltages) == 15


def test_bat_cell_voltage_values():
    bat = pylontech.BatPackCommand(read_fixture("bat_pack1.txt"))
    assert bat.cell_voltages[0] == pytest.approx(3.465)
    assert bat.cell_voltages[3] == pytest.approx(3.455)


def test_bat_no_cells_balancing_when_all_n():
    bat = pylontech.BatPackCommand(read_fixture("bat_pack1.txt"))
    assert bat.balancing_count == 0


def test_bat_pack3_high_cell_still_parses():
    bat = pylontech.BatPackCommand(read_fixture("bat_pack3.txt"))
    assert len(bat.cells) == 15
    # Cell 9 reports a High volt state at 3562 mV; voltage still parses.
    assert bat.cell_voltages[9] == pytest.approx(3.562)


def test_bat_balancing_count_counts_y_rows():
    # Synthetic input (constructed for this test): two cells report BAL=Y.
    lines = [
        "Battery  Volt     Curr     Tempr    Base State   Volt. State  Curr. State  Temp. State  SOC          Coulomb      BAL",
        "0        3465     -149     27800    Dischg       Normal       Normal       Normal       100%         92713 mAH      Y",
        "1        3466     -149     27800    Dischg       Normal       Normal       Normal       100%         92713 mAH      N",
        "2        3467     -149     27800    Dischg       Normal       Normal       Normal       100%         92713 mAH      Y",
    ]
    bat = pylontech.BatPackCommand(lines)
    assert bat.balancing_count == 2
    assert bat.cell_voltages[0] == pytest.approx(3.465)
    assert bat.cell_voltages[2] == pytest.approx(3.467)
