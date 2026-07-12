import pytest

import pylontech
from conftest import read_fixture


def test_is_flat_pwr_true_for_flat_table():
    assert pylontech.is_flat_pwr(read_fixture("pwr_flat.txt")) is True


def test_is_flat_pwr_false_for_legacy_header_format():
    legacy = ["Total AverageVoltage : 49961 mV", "Average temperature : 29 C"]
    assert pylontech.is_flat_pwr(legacy) is False


def test_pack_count_counts_only_present_packs():
    table = pylontech.PwrTableCommand(read_fixture("pwr_flat.txt"))
    assert table.pack_count == 6
    assert sorted(table.packs) == [1, 2, 3, 4, 5, 6]


def test_absent_packs_are_excluded():
    table = pylontech.PwrTableCommand(read_fixture("pwr_flat.txt"))
    assert table.pack(7) is None
    assert table.pack(16) is None


def test_pack_one_values():
    pack = pylontech.PwrTableCommand(read_fixture("pwr_flat.txt")).pack(1)
    assert pack.volt == pytest.approx(49.961)
    assert pack.curr == pytest.approx(0.0)
    assert pack.temp == pytest.approx(29.2)
    assert pack.cell_volt_low == pytest.approx(3.330)
    assert pack.cell_volt_high == pytest.approx(3.331)
    assert pack.cell_temp_low == pytest.approx(27.1)
    assert pack.cell_temp_high == pytest.approx(27.5)
    assert pack.base_state == "Idle"
    assert pack.volt_state == "Normal"
    # The Time column contains a space; SOC must be 98, not the date token.
    assert pack.soc == 98


def test_pack_three_indexing():
    pack = pylontech.PwrTableCommand(read_fixture("pwr_flat.txt")).pack(3)
    assert pack.soc == 95
    assert pack.cell_volt_low == pytest.approx(3.324)
    assert pack.cell_volt_high == pytest.approx(3.333)
    assert pack.base_state == "Idle"


def test_current_sign_charge_idle_discharge():
    table = pylontech.PwrTableCommand(read_fixture("pwr_flat_mixed.txt"))
    assert table.pack_count == 6
    # Charging pack: positive current.
    assert table.pack(1).curr == pytest.approx(0.257)
    assert table.pack(1).base_state == "Charge"
    # Idle pack: zero.
    assert table.pack(4).curr == pytest.approx(0.0)
    assert table.pack(4).base_state == "Idle"
    # Discharging packs: negative current, "Dischg" state.
    assert table.pack(5).curr == pytest.approx(-0.642)
    assert table.pack(5).base_state == "Dischg"
    assert table.pack(6).curr == pytest.approx(-0.516)


def test_all_packs_discharging():
    table = pylontech.PwrTableCommand(read_fixture("pwr_flat_discharge.txt"))
    assert table.pack_count == 6
    assert table.pack(1).curr == pytest.approx(-17.3)
    assert table.pack(1).base_state == "Dischg"
    assert all(p.base_state == "Dischg" for p in table.packs.values())
    assert all(p.curr < 0 for p in table.packs.values())


def test_corrupted_or_garbage_rows_are_skipped():
    # Real serial noise: a truncated absent fragment and a non-ASCII first
    # token. Neither is a valid present-pack row, so both are ignored.
    lines = [
        "Power Volt Curr Tempr Tlow Thigh Vlow Vhigh Base.St Volt.St Curr.St Temp.St Coulomb",
        "9     -      -      -      -      -      -",
        "��u     Absent   -   -   -   -   -   -   -   -   -   -",
    ]
    table = pylontech.PwrTableCommand(lines)
    assert table.packs == {}


def test_present_row_with_corrupt_numeric_is_skipped():
    # A row that passes the present-row check but has a corrupt numeric token
    # (e.g. a replacement char from serial-noise decoding) must be skipped
    # without failing the whole table, so the other packs still parse.
    good = "1     49961  0      29200  27100  27500  3330   3331   Idle     Normal   Normal   Normal   98%      2026-07-12 10:40:33  Normal   Normal  28500    Normal"
    bad = "2     4996�  0      29200  27100  27500  3330   3331   Idle     Normal   Normal   Normal   98%      2026-07-12 10:40:33  Normal   Normal  28500    Normal"
    table = pylontech.PwrTableCommand([good, bad])
    assert table.pack_count == 1
    assert table.pack(1).volt == pytest.approx(49.961)
    assert table.pack(2) is None
