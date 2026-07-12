"""Smoke test: the pure parser module imports standalone and fixtures load."""

import pylontech
from conftest import read_fixture


def test_pylontech_imports_without_home_assistant():
    assert hasattr(pylontech, "PwrCommand")


def test_flat_fixture_has_header_and_sixteen_rows():
    lines = read_fixture("pwr_flat.txt")
    assert lines[0].startswith("Power")
    assert len(lines) == 17  # header + 16 slot rows
