"""Shared pytest fixtures and import path setup for parser unit tests.

`pylontech.py` is a self-contained module (stdlib only). We add its directory
to sys.path so tests can `import pylontech` without importing the package
`__init__.py`, which pulls in Home Assistant.
"""

import sys
from pathlib import Path

# Make conftest itself importable for test modules
sys.path.insert(0, str(Path(__file__).parent))

_PYLONTECH_DIR = Path(__file__).parent.parent / "custom_components" / "pylontech"
sys.path.insert(0, str(_PYLONTECH_DIR))

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> list[str]:
    """Return the fixture file's lines, mirroring what `_exec_cmd` yields.

    `_exec_cmd` returns response lines with the command echo, the `@`
    separator, and the end prompts already stripped, and it drops blank
    lines. The fixture files already contain only those lines.
    """
    text = (_FIXTURE_DIR / name).read_text()
    return [line for line in text.splitlines() if line != ""]
