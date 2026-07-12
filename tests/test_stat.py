import pylontech
from conftest import read_fixture


def test_stat_pack1_cycle_count_and_no_faults():
    stat = pylontech.StatCommand(read_fixture("stat_pack1.txt"))
    assert stat.cycle_count == 725
    assert stat.protection_events == 0


def test_stat_pack3_cycle_count_and_fault_sum():
    stat = pylontech.StatCommand(read_fixture("stat_pack3.txt"))
    assert stat.cycle_count == 919
    # COCA 1907 + Bat OV 6988 + Bat HV 716 + Bat LV 162 + Bat UV 6 + Pwr LV 82
    assert stat.protection_events == 9861


def test_stat_tolerates_line_noise_and_colonless_line():
    # The corrupted 'LifeWa}&(' label and the colon-less 'Device address'
    # line must not break parsing of CYCLE Times / protection counts.
    stat = pylontech.StatCommand(read_fixture("stat_pack1.txt"))
    assert stat.cycle_count == 725


def test_stat_missing_fields_are_none():
    stat = pylontech.StatCommand(["Device address           1"])
    assert stat.cycle_count is None
    assert stat.protection_events is None
