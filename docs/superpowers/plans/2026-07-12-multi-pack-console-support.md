# Multi-pack Console Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the TCP console protocol drive a multi-pack Pylontech stack in Home Assistant, fixing the five defects that prevent setup on a six-pack US5000 stack (upstream issue jtubb#2).

**Architecture:** Add two pure parsers to `pylontech.py` for the flat multi-pack `pwr` table and the `pwr <index>` detail view (no Home Assistant imports, fully unit-tested). Wire them into `TCPConsoleProtocol`: fix the line ending, cache the flat `pwr` per connection, derive `pack_count`, add a used `pack_id` parameter, merge flat + detail per pack, and stop crashing on the unsupported `unit` command. Preserve the existing header-format single-pack path via format detection.

**Tech Stack:** Python 3.11+ (async), Home Assistant custom component, `pytest` for parser unit tests (dev-only, not a runtime dependency).

## Global Constraints

- No runtime external dependencies: `manifest.json` `requirements` stays `[]`; parsers use stdlib only. Copied verbatim from the spec.
- British English and `YYYY-MM-DD` dates in new docs/comments. No em-dashes or en-dashes.
- The `sys.path.insert` import shim at the top of `protocol/tcp_console.py` is load-bearing (avoids a circular import through the package `__init__.py`). Do NOT remove it; add new imports to the existing `from pylontech import (...)` block.
- Parser classes in `pylontech.py` must not import Home Assistant, `models`, or `const` (they are unit-tested standalone).
- Unit conversions: mV→V `/1000`, mA→A `/1000`, mC→C `/1000`, mAh→Ah `/1000`.

---

### Task 1: Test scaffolding and fixtures

Establish a `pytest` harness that can import `pylontech.py` standalone (without triggering the package `__init__.py`, which imports Home Assistant), plus the captured device output as fixtures.

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/fixtures/pwr_flat.txt`
- Create: `tests/fixtures/pwr_flat_mixed.txt`
- Create: `tests/fixtures/pwr_flat_discharge.txt`
- Create: `tests/fixtures/pwr_detail_pack1.txt`
- Create: `tests/test_import.py`

**Interfaces:**
- Produces: a `pytest` setup where `import pylontech` resolves to `custom_components/pylontech/pylontech.py`, and helper `read_fixture(name)` returning the fixture's lines as `list[str]`.

- [ ] **Step 1: Create the empty package marker**

Create `tests/__init__.py` with no content.

- [ ] **Step 2: Create the conftest that puts pylontech.py on the path**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures and import path setup for parser unit tests.

`pylontech.py` is a self-contained module (stdlib only). We add its directory
to sys.path so tests can `import pylontech` without importing the package
`__init__.py`, which pulls in Home Assistant.
"""

import sys
from pathlib import Path

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
```

- [ ] **Step 3: Create the flat `pwr` fixture**

Create `tests/fixtures/pwr_flat.txt` (verbatim capture, header plus 16 slot rows):

```
Power Volt   Curr   Tempr  Tlow   Thigh  Vlow   Vhigh  Base.St  Volt.St  Curr.St  Temp.St  Coulomb  Time                 B.V.St   B.T.St   MosTempr M.T.St
1     49961  0      29200  27100  27500  3330   3331   Idle     Normal   Normal   Normal   98%      2026-07-12 10:40:33  Normal   Normal  28500    Normal
2     49964  0      28600  26900  27600  3330   3333   Idle     Normal   Normal   Normal   98%      2026-07-12 10:40:32  Normal   Normal  28100    Normal
3     49964  0      29000  27000  27100  3324   3333   Idle     Normal   Normal   Normal   95%      2026-07-12 10:40:33  Normal   Normal  28100    Normal
4     49962  0      28800  26700  26800  3329   3332   Idle     Normal   Normal   Normal   100%     2026-07-12 10:40:33  Normal   Normal  28100    Normal
5     49966  0      28800  26400  26700  3329   3335   Idle     Normal   Normal   Normal   100%     2026-07-12 10:40:32  Normal   Normal  27800    Normal
6     49965  0      28400  25900  26000  3328   3335   Idle     Normal   Normal   Normal   100%     2026-07-12 10:40:33  Normal   Normal  27400    Normal
7     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
8     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
9     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
10    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
11    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
12    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
13    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
14    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
15    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
16    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
```

- [ ] **Step 3b: Create the mixed charge/idle/discharge fixture**

Create `tests/fixtures/pwr_flat_mixed.txt` (verbatim capture while cycling;
packs 1-3 charging, 4 idle, 5-6 discharging):

```
Power Volt   Curr   Tempr  Tlow   Thigh  Vlow   Vhigh  Base.St  Volt.St  Curr.St  Temp.St  Coulomb  Time                 B.V.St   B.T.St   MosTempr M.T.St
1     50538  257    29300  27100  27700  3368   3370   Charge   Normal   Normal   Normal   98%      2026-07-12 11:03:39  Normal   Normal  28700    Normal
2     50537  301    28700  27000  27600  3368   3374   Charge   Normal   Normal   Normal   98%      2026-07-12 11:03:38  Normal   Normal  28200    Normal
3     50530  1673   29200  27100  27100  3360   3439   Charge   Normal   Normal   Normal   96%      2026-07-12 11:03:39  Normal   Normal  28300    Normal
4     50537  0      28900  26700  26900  3367   3371   Idle     Normal   Normal   Normal   100%     2026-07-12 11:03:39  Normal   Normal  28300    Normal
5     50545  -642   28900  26500  26800  3367   3373   Dischg   Normal   Normal   Normal   100%     2026-07-12 11:03:38  Normal   Normal  27900    Normal
6     50545  -516   28500  25900  26000  3367   3373   Dischg   Normal   Normal   Normal   100%     2026-07-12 11:03:39  Normal   Normal  27500    Normal
7     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
8     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
9     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
10    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
11    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
12    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
13    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
14    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
15    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
16    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
```

- [ ] **Step 3c: Create the all-discharge fixture**

Create `tests/fixtures/pwr_flat_discharge.txt` (verbatim capture, all six packs
discharging with large negative currents):

```
Power Volt   Curr   Tempr  Tlow   Thigh  Vlow   Vhigh  Base.St  Volt.St  Curr.St  Temp.St  Coulomb  Time                 B.V.St   B.T.St   MosTempr M.T.St
1     50430  -17300 29300  27200  27700  3360   3363   Dischg   Normal   Normal   Normal   98%      2026-07-12 11:05:52  Normal   Normal  28700    Normal
2     50455  -16444 28800  27000  27700  3362   3368   Dischg   Normal   Normal   Normal   98%      2026-07-12 11:05:50  Normal   Normal  28300    Normal
3     50446  -1883  29300  27100  27200  3298   3375   Dischg   Normal   Normal   Normal   96%      2026-07-12 11:05:51  Normal   Normal  28300    Normal
4     50443  -8974  28900  26800  26900  3358   3365   Dischg   Normal   Normal   Normal   100%     2026-07-12 11:05:51  Normal   Normal  28300    Normal
5     50452  -8470  29000  26500  26800  3359   3371   Dischg   Normal   Normal   Normal   100%     2026-07-12 11:05:50  Normal   Normal  27900    Normal
6     50420  -9228  28600  26000  26000  3356   3369   Dischg   Normal   Normal   Normal   100%     2026-07-12 11:05:51  Normal   Normal  27500    Normal
7     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
8     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
9     -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
10    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
11    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
12    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
13    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
14    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
15    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
16    -      -      -      -      -      -      -      Absent   -        -        -        -        -                    -        -
```

- [ ] **Step 4: Create the `pwr 1` detail fixture**

Create `tests/fixtures/pwr_detail_pack1.txt` (verbatim capture; blank lines omitted to mirror `_exec_cmd`):

```
 ----------------------------
 Power  1
 Voltage         : 49961       mV
 Current         : 0           mA
 Temperature     : 29200       mC
 Coulomb         : 98          %
 Total Coulomb   : 100000      mAH
 Max Voltage     : 54000       mV
 Charge Times    : 40471
 Basic Status    : Idle
 Volt Status     : Normal
 Current Status  : Normal
 Tmpr. Status    : Normal
 Coul. Status    : Normal
 Soh. Status     : Normal
 Heater Status   : OFF
 Protect ENA     : BOV BHV BLV BUV POV PHV PLV PUV CBOT CBHT CBLT CBUT DBOT DBHT DBLT DBUT POT PHT COC COC2 COCA DOCA DOC DOC2 SC LCOUL
 Bat Events      : 0x0
 Power Events    : 0x0
 System Fault    : 0x0
 ----------------------------
```

- [ ] **Step 5: Write the import smoke test**

Create `tests/test_import.py`:

```python
"""Smoke test: the pure parser module imports standalone and fixtures load."""

import pylontech
from conftest import read_fixture


def test_pylontech_imports_without_home_assistant():
    assert hasattr(pylontech, "PwrCommand")


def test_flat_fixture_has_header_and_sixteen_rows():
    lines = read_fixture("pwr_flat.txt")
    assert lines[0].startswith("Power")
    assert len(lines) == 17  # header + 16 slot rows
```

- [ ] **Step 6: Run the smoke tests**

Run: `pip install pytest && python -m pytest tests/ -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "test: add pytest scaffolding and captured device fixtures"
```

---

### Task 2: Flat multi-pack `pwr` parser

Parse the flat `pwr` table into per-pack records keyed by pack index, skipping absent slots, reading only columns 0 to 12 (stopping before the space-containing `Time` column).

**Files:**
- Modify: `custom_components/pylontech/pylontech.py` (add new code after the `PwrCommand` class, around line 247)
- Test: `tests/test_pwr_table.py`

**Interfaces:**
- Produces:
  - `class PwrPack` dataclass with fields: `index: int`, `volt: float`, `curr: float`, `temp: float`, `cell_temp_low: float`, `cell_temp_high: float`, `cell_volt_low: float`, `cell_volt_high: float`, `base_state: str`, `volt_state: str`, `curr_state: str`, `temp_state: str`, `soc: int`.
  - `class PwrTableCommand` with `__init__(self, lines)`, attribute `packs: dict[int, PwrPack]`, property `pack_count -> int`, method `pack(self, pack_id: int) -> PwrPack | None`.
  - `def is_flat_pwr(lines) -> bool` — True when the response is the flat multi-pack table.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pwr_table.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_pwr_table.py -v`
Expected: FAIL with `AttributeError: module 'pylontech' has no attribute 'is_flat_pwr'` (and `PwrTableCommand`).

- [ ] **Step 3: Implement the parser**

In `custom_components/pylontech/pylontech.py`, add after the `PwrCommand` class (after its `__str__`, around line 247):

```python
def _is_present_pwr_row(tokens: list[str]) -> bool:
    """True for a flat-table data row describing a present pack."""
    return len(tokens) > 12 and tokens[0].isdigit() and tokens[8] != "Absent"


def is_flat_pwr(lines) -> bool:
    """Return True if a `pwr` response is the flat multi-pack table.

    The flat table has a header row naming the Volt, Curr and Base.St
    columns. The legacy single-pack format has no such header.
    """
    for line in lines:
        if "Volt" in line and "Curr" in line and "Base.St" in line:
            return True
    return False


@dataclass
class PwrPack:
    """One pack's data from a row of the flat `pwr` table."""

    index: int
    volt: float  # V
    curr: float  # A (signed)
    temp: float  # C
    cell_temp_low: float  # C
    cell_temp_high: float  # C
    cell_volt_low: float  # V
    cell_volt_high: float  # V
    base_state: str
    volt_state: str
    curr_state: str
    temp_state: str
    soc: int  # %


class PwrTableCommand:
    """Parses the flat multi-pack `pwr` table (one row per pack slot).

    Only columns 0 to 12 are read; the Time column (index 13) contains a
    space, so positional parsing past column 12 is unreliable. Absent slots
    (Base.St == "Absent") are skipped. Packs are keyed by their reported
    index so a non-contiguous stack is still addressed correctly.
    """

    def __init__(self, lines) -> None:
        """Initialize by parsing every present pack row."""
        self.packs: dict[int, PwrPack] = {}
        for line in lines:
            tokens = line.split()
            if not _is_present_pwr_row(tokens):
                continue
            index = int(tokens[0])
            self.packs[index] = PwrPack(
                index=index,
                volt=int(tokens[1]) / 1000,
                curr=int(tokens[2]) / 1000,
                temp=int(tokens[3]) / 1000,
                cell_temp_low=int(tokens[4]) / 1000,
                cell_temp_high=int(tokens[5]) / 1000,
                cell_volt_low=int(tokens[6]) / 1000,
                cell_volt_high=int(tokens[7]) / 1000,
                base_state=tokens[8],
                volt_state=tokens[9],
                curr_state=tokens[10],
                temp_state=tokens[11],
                soc=int(tokens[12].replace("%", "")),
            )

    @property
    def pack_count(self) -> int:
        """Number of present packs."""
        return len(self.packs)

    def pack(self, pack_id: int) -> PwrPack | None:
        """Return the pack with this 1-based index, or None if absent."""
        return self.packs.get(pack_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_pwr_table.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add custom_components/pylontech/pylontech.py tests/test_pwr_table.py
git commit -m "feat: parse flat multi-pack pwr table"
```

---

### Task 3: Per-pack `pwr <index>` detail parser

Parse the `Key : value unit` detail view for the fields the flat table lacks: total capacity, cycle count, max voltage, and health statuses.

**Files:**
- Modify: `custom_components/pylontech/pylontech.py` (add after `PwrTableCommand`)
- Test: `tests/test_pwr_detail.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `class PwrDetailCommand` with `__init__(self, lines)` and attributes `total_capacity: float | None` (Ah), `cycle_count: int | None`, `max_voltage: float | None` (V), `soh_status: str | None`, `heater_status: str | None`, `system_fault: str | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pwr_detail.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_pwr_detail.py -v`
Expected: FAIL with `AttributeError: module 'pylontech' has no attribute 'PwrDetailCommand'`.

- [ ] **Step 3: Implement the parser**

In `custom_components/pylontech/pylontech.py`, add after `PwrTableCommand`:

```python
class PwrDetailCommand:
    """Parses `pwr <index>` per-pack detail (Key : value unit lines).

    Complementary to the flat table: supplies total capacity, max voltage,
    cycle count and health statuses, which the flat table does not carry.
    """

    def __init__(self, lines) -> None:
        """Initialize by scanning the detail lines for known keys."""
        self.total_capacity: float | None = None  # Ah
        self.cycle_count: int | None = None
        self.max_voltage: float | None = None  # V
        self.soh_status: str | None = None
        self.heater_status: str | None = None
        self.system_fault: str | None = None

        for line in lines:
            if ":" not in line:
                continue
            key, _, rest = line.partition(":")
            key = key.strip()
            tokens = rest.split()
            value = tokens[0] if tokens else ""
            if not value:
                continue
            if key == "Total Coulomb":
                self.total_capacity = int(value) / 1000
            elif key == "Charge Times":
                self.cycle_count = int(value)
            elif key == "Max Voltage":
                self.max_voltage = int(value) / 1000
            elif key == "Soh. Status":
                self.soh_status = value
            elif key == "Heater Status":
                self.heater_status = value
            elif key == "System Fault":
                self.system_fault = value
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_pwr_detail.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add custom_components/pylontech/pylontech.py tests/test_pwr_detail.py
git commit -m "feat: parse per-pack pwr detail view"
```

---

### Task 4: Console protocol line ending, pwr caching, and pack_count

Fix the line ending (defect 1), cache the flat `pwr` per connection, and derive `pack_count` in `get_device_info` (defect 2).

**Files:**
- Modify: `custom_components/pylontech/protocol/tcp_console.py`

**Interfaces:**
- Consumes: `is_flat_pwr`, `PwrTableCommand` from `pylontech` (Task 2).
- Produces: `TCPConsoleProtocol._pwr_table_lines(self) -> tuple[str, ...]` (cached flat `pwr`); `get_device_info()` now sets `DeviceInfo.pack_count`.

- [ ] **Step 1: Add the new parser imports**

In `custom_components/pylontech/protocol/tcp_console.py`, extend the existing import block (lines 23-29) to:

```python
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
```

- [ ] **Step 2: Add a per-connection pwr cache field**

In `__init__` (after `self.writer = None`, around line 53) add:

```python
        # Cached flat `pwr` response for the current connection (cleared on
        # connect/disconnect) so pack_count and every per-pack fetch reuse it.
        self._pwr_lines: tuple[str, ...] | None = None
```

- [ ] **Step 3: Clear the cache on connect and disconnect**

In `connect` (after the `open_connection` assignment, before the debug log, around line 59) add:

```python
        self._pwr_lines = None
```

In `disconnect`, inside the `if self.writer is not None:` block (after `self.writer = None`, around line 68) add:

```python
            self._pwr_lines = None
```

- [ ] **Step 4: Fix the line ending**

In `_exec_cmd` (line 83) change:

```python
        self.writer.write((cmd + "\r").encode("ascii"))
```

to:

```python
        # Device requires CR+LF; CR alone is not accepted over ser2net bridges.
        self.writer.write((cmd + "\r\n").encode("ascii"))
```

- [ ] **Step 4b: Harden line decoding against serial noise**

Real captures show occasional non-ASCII line noise, which would make a strict
ASCII decode raise `UnicodeDecodeError` and fail the whole update. In
`_exec_cmd` (around line 95) change:

```python
                    line = linebytes.decode("ascii")
```

to:

```python
                    # Tolerate occasional serial line noise: a stray non-ASCII
                    # byte becomes a replacement char and the malformed line is
                    # skipped downstream rather than failing the whole read.
                    line = linebytes.decode("ascii", errors="replace")
```

- [ ] **Step 5: Add the cached pwr-table helper**

Add this method to `TCPConsoleProtocol` (after the `unit` method, around line 119):

```python
    async def _pwr_table_lines(self) -> tuple[str, ...]:
        """Fetch the flat `pwr` response once per connection and cache it."""
        if self._pwr_lines is None:
            self._pwr_lines = await self._exec_cmd("pwr")
        return self._pwr_lines
```

- [ ] **Step 6: Set pack_count in get_device_info**

In `get_device_info` (lines 121-144), after `info = await self.info()` add:

```python
        pwr_lines = await self._pwr_table_lines()
        pack_count = (
            PwrTableCommand(pwr_lines).pack_count if is_flat_pwr(pwr_lines) else 1
        )
```

and add `pack_count=pack_count,` to the `DeviceInfo(...)` constructor call (e.g. immediately after the `variant=` line).

- [ ] **Step 7: Syntax-check the module**

Run: `python -m py_compile custom_components/pylontech/protocol/tcp_console.py`
Expected: no output (exit 0). (The module cannot be imported without Home Assistant; syntax check plus review is the gate here.)

- [ ] **Step 8: Verify parser tests still pass**

Run: `python -m pytest tests/ -v`
Expected: PASS (all previous tests).

- [ ] **Step 9: Commit**

```bash
git add custom_components/pylontech/protocol/tcp_console.py
git commit -m "fix: CR+LF line ending, pwr caching, and pack_count detection"
```

---

### Task 5: Per-pack battery data (flat + detail merge, with legacy fallback)

Add the used `pack_id` parameter (defect 3), select the pack from the flat table and enrich it with the detail view (defect 4), and stop calling `unit` unconditionally (defect 5).

**Files:**
- Modify: `custom_components/pylontech/protocol/tcp_console.py` (replace `get_battery_data`, lines 146-245)

**Interfaces:**
- Consumes: `_pwr_table_lines` (Task 4); `is_flat_pwr`, `PwrTableCommand`, `PwrDetailCommand`, `PwrCommand` from `pylontech`.
- Produces: `get_battery_data(self, pack_id: int = 1) -> BatteryData` used by `coordinator.py`.

- [ ] **Step 1: Replace get_battery_data with a dispatcher plus two paths**

Replace the entire `get_battery_data` method (lines 146-245) with:

```python
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
            cell_voltages=[],
            cell_temps=[],
            base_state=pack.base_state,
            volt_state=pack.volt_state,
            curr_state=pack.curr_state,
            temp_state=pack.temp_state,
            cell_volt_low=pack.cell_volt_low,
            cell_volt_high=pack.cell_volt_high,
            cell_temp_low=pack.cell_temp_low,
            cell_temp_high=pack.cell_temp_high,
            charge_ah_perc=pack.soc,
            cycle_count=detail.cycle_count,
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
            cycle_count=None,
        )
```

Note: the original method passed `alarms={}`, but `BatteryData` has no
`alarms` field, so that kwarg would raise `TypeError`. It is omitted here (a
latent sixth defect, previously masked by the earlier missing-`pack_id` crash).

- [ ] **Step 2: Syntax-check the module**

Run: `python -m py_compile custom_components/pylontech/protocol/tcp_console.py`
Expected: no output (exit 0).

- [ ] **Step 3: Review checklist (manual)**

Confirm by reading the diff:
- `get_battery_data` signature is `(self, pack_id: int = 1)`.
- The flat path never calls `self.unit()`.
- The legacy path's `BatteryData(...)` field set matches the original method (compare against git history of lines 180-245), except the invalid `alarms={}` kwarg is intentionally omitted (BatteryData has no `alarms` field).
- `BatteryData` required fields (`pack_voltage`, `pack_current`, `soc`, `remaining_capacity`, `total_capacity`) are supplied on both paths.

- [ ] **Step 4: Verify parser tests still pass**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/pylontech/protocol/tcp_console.py
git commit -m "fix: per-pack battery data via flat+detail pwr, drop unit dependency"
```

---

### Task 6: Coordinator defensive pack_count

Make the coordinator robust to a missing `pack_count` so a future protocol gap cannot reintroduce the `None + 1` crash, and use one consistent source for the count.

**Files:**
- Modify: `custom_components/pylontech/coordinator.py`

**Interfaces:**
- Consumes: `DeviceInfo.pack_count` (Task 4).
- Produces: `PylontechUpdateCoordinator.pack_count` defaulted to at least 1.

- [ ] **Step 1: Default pack_count to 1**

In `__init__` change line 50:

```python
        self.pack_count = device_info.pack_count
```

to:

```python
        self.pack_count = device_info.pack_count or 1
```

- [ ] **Step 2: Use self.pack_count in the device-info tuple**

In `__init__` change the comprehension (lines 54-57) to use `self.pack_count`:

```python
        self.pack_device_infos = tuple(
            _pack_device(device_info, pack_id, device_name)
            for pack_id in range(1, self.pack_count + 1)
        )
```

- [ ] **Step 3: Use self.pack_count in the update loop**

In `_async_update_data` change line 72:

```python
            for pack_id in range(1, self.device_info_model.pack_count + 1):
```

to:

```python
            for pack_id in range(1, self.pack_count + 1):
```

- [ ] **Step 4: Use self.pack_count in detect_sensors**

In `detect_sensors` change line 214:

```python
            for pack_id in range(1, self.device_info_model.pack_count + 1):
```

to:

```python
            for pack_id in range(1, self.pack_count + 1):
```

- [ ] **Step 5: Syntax-check the module**

Run: `python -m py_compile custom_components/pylontech/coordinator.py`
Expected: no output (exit 0).

- [ ] **Step 6: Commit**

```bash
git add custom_components/pylontech/coordinator.py
git commit -m "fix: default coordinator pack_count to 1 defensively"
```

---

### Task 7: Changelog entry

Record the fix in the changelog for a clean upstream PR.

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add an Unreleased section**

In `CHANGELOG.md`, insert immediately after the header block (after line 6, before `## [1.1.0]`):

```markdown
## [Unreleased]

### Fixed
- Multi-pack console protocol setup on stacks such as the US5000 (issue #2):
  - Send CR+LF line endings so ser2net-bridged consoles accept commands.
  - Derive `pack_count` from the `pwr` table instead of leaving it unset.
  - Add and use a `pack_id` parameter when fetching per-pack data.
  - Parse the flat multi-pack `pwr` table by pack index, skipping absent slots.
  - Stop calling the `unit` command unconditionally; it is not supported on
    all firmware and now degrades gracefully.
  - Tolerate non-ASCII serial line noise instead of failing the update cycle.

### Added
- Per-pack total capacity, cycle count and health statuses from the
  `pwr <index>` detail view.

```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for multi-pack console fixes"
```

---

## Manual validation (maintainer, on hardware)

Not automated. After the tasks above, run the branch against the live stack:

1. Set up the integration against the console (TCP or ser2net bridge).
2. Confirm setup succeeds (no `TypeError` about `NoneType + int`, no crash on `unit`).
3. Confirm six pack devices appear, each with voltage, current, power, SOC,
   cell voltage/temperature extremes, states, total capacity and cycle count.
4. When a pack is charging/discharging, capture `pwr` and note the sign of the
   `Curr` column; if charge is negative, adjust the power sign expectation and
   add the charging fixture as a further parser test.

## Self-review notes

- **Spec coverage:** defects 1-5 → Tasks 4, 4, 5, 2+5, 5; flat parsing → Task 2;
  detail enrichment → Task 3; model mapping (total_capacity, cycle_count,
  remaining_capacity, status_groups) → Task 5; coordinator defensive default →
  Task 6; backward-compat detection → Tasks 2 (`is_flat_pwr`) + 5 (dispatch);
  testing → Tasks 1-3; changelog → Task 7. The spec's "remove sys.path import
  hack" tidy is intentionally dropped (documented in Global Constraints) because
  it is load-bearing.
- **Placeholders:** none; every code step is complete.
- **Type consistency:** `PwrTableCommand.pack()` returns `PwrPack | None`;
  `PwrDetailCommand` attribute names match their uses in Task 5;
  `_pwr_table_lines` return type matches its consumers.
```
