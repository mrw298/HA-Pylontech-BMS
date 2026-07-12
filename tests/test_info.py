import pylontech
from conftest import read_fixture


def test_info_pack2_us5000_all_fields():
    info = pylontech.InfoCommand(read_fixture("info_pack2.txt"))
    assert info.device_address.value == 2
    assert info.manufacturer.value == "Pylon"
    assert info.device_name.value == "US5000"
    assert info.board_version.value == "V10R04"
    assert info.main_sw_version.value == "B69.16.0.0"
    assert info.sw_version.value == "V1.3"
    assert info.barcode.value == "Y230102C50000001"
    assert info.cell_number.value == 15
    assert info.max_charge_current.value == 100000
    assert info.max_discharge_current.value == -100000


def test_info_pack3_us2000c():
    info = pylontech.InfoCommand(read_fixture("info_pack3.txt"))
    assert info.device_name.value == "US2000C"
    assert info.barcode.value == "K22D087C32000002"
    assert info.main_sw_version.value == "B69.13.0.0"
    assert info.cell_number.value == 15
    assert info.device_address.value == 3


def test_info_not_derailed_by_unexpected_board_line():
    # The 'Board : NF4.E3' line sits between 'Board version' and 'Main Soft
    # version'. Under the old sequential parser it stalled parsing and left
    # barcode/firmware None. Order-independent parsing must read them.
    info = pylontech.InfoCommand(read_fixture("info_pack2.txt"))
    assert info.barcode.value is not None
    assert info.main_sw_version.value is not None
    assert info.hard_version.value is None  # no 'Hard version' line present


def test_info_module_barcode_line_not_treated_as_bmu():
    # 'Module Barcode'/'PCBA Barcode' are fields, not BMU enumeration lines,
    # and must not be scooped into bmu_modules/bmu_pcbas.
    lines = [
        "Manufacturer        : Pylon",
        "Module Barcode      : ABC123",
        "PCBA Barcode        : DEF456",
    ]
    info = pylontech.InfoCommand(lines)
    assert info.bmu_modules == []
    assert info.bmu_pcbas == []
    assert info.module_barcode.value == "ABC123"
