# Multi-pack console protocol support

Design spec for fixing the TCP console protocol so a multi-pack Pylontech
stack works in Home Assistant. Addresses upstream issue
[jtubb/HA-Pylontech-BMS#2](https://github.com/jtubb/HA-Pylontech-BMS/issues/2).

- **Date:** 2026-07-12
- **Branch:** `feature/multi-pack-console-support`
- **Base:** this fork (jtubb-based), aiming for a clean upstream PR.

## Problem

The console protocol layer (`protocol/tcp_console.py` and `pylontech.py`)
cannot drive a multi-pack stack. The coordinator (`coordinator.py`) is already
multi-pack aware (it loops `pack_id` from 1 to `pack_count`, keys results as
`pack_N`, and builds a device per pack), but the protocol layer beneath it is
broken in five ways. On a real six-pack US5000 stack the integration fails to
set up.

## Confirmed defects

Four are from issue #2; the fifth was found while validating against real
hardware output.

1. **Line ending.** `_exec_cmd` sends `cmd + "\r"`. The reporter's device
   (US3000C via ser2net) requires `cmd + "\r\n"`.
   Location: `protocol/tcp_console.py` `_exec_cmd`.
2. **Missing `pack_count`.** `get_device_info()` builds a `DeviceInfo` without
   setting `pack_count`, so it stays `None`. The coordinator then evaluates
   `range(1, device_info.pack_count + 1)`, raising
   `TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'`.
   Location: `protocol/tcp_console.py` `get_device_info`, consumed at
   `coordinator.py` (`__init__` and `_async_update_data`).
3. **Missing `pack_id` parameter.** `get_battery_data(self)` takes no
   `pack_id`, but `coordinator.py` calls `get_battery_data(pack_id=pack_id)`,
   raising `TypeError`.
   Location: `protocol/tcp_console.py` `get_battery_data`.
4. **Single-pack parsing.** `PwrCommand` parses a single fixed layout and does
   not select data per pack. A multi-pack stack returns one row per pack.
   Location: `pylontech.py` `PwrCommand`.
5. **Unconditional `unit` call (found during validation).**
   `get_battery_data` calls `self.unit()` unconditionally. The US5000 device
   returns `Unknown command 'unit' - try 'help'`, so setup would crash even
   after defects 1 to 4 are fixed.
   Location: `protocol/tcp_console.py` `get_battery_data`.

## Reference device output

Captured verbatim from the target six-pack US5000 stack on 2026-07-12. These
double as the test fixtures.

### `pwr` (flat table, all packs)

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

This is the verbatim capture (all packs are idle at 0 A). The `Time` column
contains a space (`2026-07-12 10:40:33`), so a naive `split()` produces two
tokens there; the parser must only read columns up to and including index 12
(Coulomb).

Column mapping after `line.split()` (0-indexed), validated against L1brTy's
US5000 fork:

| Index | Column   | Meaning              | Unit | Conversion |
|-------|----------|----------------------|------|------------|
| 0     | Power    | pack index (1-based) | -    | int        |
| 1     | Volt     | pack voltage         | mV   | /1000 → V  |
| 2     | Curr     | pack current, signed | mA   | /1000 → A  |
| 3     | Tempr    | pack temperature     | mC   | /1000 → C  |
| 4     | Tlow     | cell temp low        | mC   | /1000 → C  |
| 5     | Thigh    | cell temp high       | mC   | /1000 → C  |
| 6     | Vlow     | cell volt low        | mV   | /1000 → V  |
| 7     | Vhigh    | cell volt high       | mV   | /1000 → V  |
| 8     | Base.St  | basic state          | -    | text       |
| 9     | Volt.St  | voltage state        | -    | text       |
| 10    | Curr.St  | current state        | -    | text       |
| 11    | Temp.St  | temperature state    | -    | text       |
| 12    | Coulomb  | state of charge      | %    | strip `%`  |

Columns 13+ (Time date, Time clock, B.V.St, B.T.St, MosTempr, M.T.St) are not
read on the flat path because the Time space makes positional indexing past
column 12 unreliable.

### `pwr 1` (per-pack detail)

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

This detail view is a set of `Key : value unit` lines. It is complementary to
the flat table: it lacks cell voltage/temperature extremes but adds total
capacity, max voltage, charge/cycle count, and health statuses.

### `unit`

```
Unknown command 'unit' - try 'help'
```

Not supported on this device. `help` confirms the available commands:
`bat`, `data`, `datalist`, `disp`, `getpwr`, `help`, `info`, `log`, `login`,
`logout`, `pwr [index]`, `shut`, `soh`, `stat`, `time`, `trst`, `updata`.

## Design

### Data collection per update cycle

The coordinator brackets each cycle with `connect()` then a per-pack loop then
`disconnect()`. Per connection the protocol will:

1. Fetch the flat `pwr` table **once** and cache it on the protocol instance.
2. For each pack, fetch `pwr <index>` detail and `bat <index>` per-cell data.
3. Clear the cache on `disconnect()` (and on `connect()`).

For a six-pack stack this is 1 flat + 6 detail + 6 per-cell = 13 commands per
30 s cycle, plus `info` once at setup. `get_battery_data(pack_id)` merges the
cached flat row, the pack's detail, and its per-cell data into one
`BatteryData`. The coordinator loop is unchanged.

### Per-cell data (`bat <index>`)

`bat <index>` returns one row per cell (15 on a US5000 pack): cell index,
voltage (mV), current, temperature, base/volt/curr/temp states, SOC, coulomb
(two tokens, e.g. `92713 mAH`), and a balancing flag (`Y`/`N`). Per the chosen
scope we surface only per-cell **voltages** and a per-pack **count of cells
balancing** (skipping the redundant per-cell temp/SOC, which the flat table's
extremes already summarise). A new `BatPackCommand` parser reads the cell
voltage (token 1) and the balancing flag (last token); using the first, second,
and last tokens avoids the two-token `Coulomb` field. Cell voltages populate the
existing `BatteryData.cell_voltages` list (flattened to `cell_voltage_0..N`
sensors by existing code); the balancing count uses a new
`cells_balancing` field. The `bat <index>` fetch is wrapped so a device that
rejects it degrades to no cell data rather than failing.

### Parsing (in `pylontech.py`, no Home Assistant imports)

- **Flat table:** `PwrCommand` gains multi-pack parsing. It detects the flat
  table (a header row containing `Volt` and `Curr`, followed by digit-led data
  rows with more than 12 tokens), parses each present row (skipping any row
  whose Base.St is `Absent` or whose cells are `-`) into a per-pack record keyed
  by the integer pack index from column 0, and exposes a lookup by `pack_id`.
  Uses the existing `Voltage`, `Current`, `Temp`, `Percent`, `Text` types.
- **Per-pack detail:** a new parser (e.g. `PwrDetailCommand`) scans the
  `Key : value unit` lines and extracts Voltage, Current, Temperature, Coulomb
  (SOC), Total Coulomb (capacity), Max Voltage, Charge Times (cycle count), and
  the Basic/Volt/Current/Tmpr/Coul/Soh statuses, Heater status, and System
  Fault. Unit conversions: mV→V, mA→A, mC→C, mAh→Ah.

### Per-pack device identity (`info <index>`)

Originally `get_device_info()` called plain `info` once and the coordinator
cloned that single result to every pack, so a mixed stack (e.g. pack 2 =
US5000, pack 3 = US2000C) showed the same model/serial/firmware on every pack
device. Two defects:

- **Global metadata.** Fix: fetch `info <pack_id>` per pack at setup (static
  data, fetched once, not per cycle) and build each pack's Home Assistant
  device from its own metadata (model, real barcode as serial, firmware,
  hardware version, cell count).
- **Fragile `InfoCommand` parse.** The parser matched each field only against
  the current first line and advanced only on a match, so an unexpected line
  (`Board : NF4.E3`, present between `Board version` and `Main Soft version`
  in `info <index>` output) stalled it: everything after that line
  (`Main Soft version`, `Barcode`, `Cell Number`, ...) failed to parse,
  surfacing as "Unknown". Fix: parse order-independently by building a
  whitespace-normalised `key -> value` dict from the `key : value` lines, then
  reading known keys. Barcode is read from the `Barcode` field (with
  `Module Barcode` as a fallback).

Device and entity identities therefore change to real per-pack barcodes; the
entity `unique_id` scheme is bumped (`-v3`) so Home Assistant recreates
entities with correct identities. The config-entry identity is left unchanged
so the integration instance is not re-onboarded.

### Protocol layer (`protocol/tcp_console.py`)

- `_exec_cmd`: send `cmd + "\r\n"` (defect 1).
- `get_device_info`: after `info`, fetch the flat `pwr` table and set
  `pack_count` = number of present rows (first token is a digit and the row is
  not `Absent`). Reuse the cached flat table if already fetched this connection.
- `get_battery_data(self, pack_id: int = 1)`: use the cached flat row for
  `pack_id` for cell extremes, states, V/A/temp/SOC; fetch `pwr <pack_id>`
  detail for capacity, cycle count, max voltage, and health statuses; merge.
  Do **not** call `unit()` on this path.
- Remove the unconditional `unit()` call (defect 5). On the legacy path (see
  below) any `unit()` use is wrapped in try/except so a device without `unit`
  degrades gracefully rather than failing.

### Model mapping (`models.py`)

Populate existing `BatteryData` fields currently always `None`:

- `total_capacity` = Total Coulomb / 1000 (100 Ah).
- `cycle_count` = Charge Times (40471).
- `remaining_capacity` = `total_capacity * soc / 100`.

Health statuses (SOH, Heater, System Fault) surface through the existing
generic `status_groups` dict so no new model fields or sensor plumbing are
required. Max voltage is not surfaced unless later requested.

### Coordinator (`coordinator.py`)

No structural change. One defensive tidy: treat an absent/`None` `pack_count`
as `1` so a future protocol gap can never reintroduce the `None + 1` crash.

### Backward compatibility

`PwrCommand` detects format. If the flat multi-pack table is present it uses
the new path. Otherwise it falls back to the existing header-based single-pack
parse, left unchanged. This preserves jtubb's original device behaviour on a
best-effort basis. Caveat: the legacy header path is preserved but unverified,
because no raw output for that device family is available. `pwr <index>` and
the flat parse run only on the new path.

### Local tidy (in scope)

- Replace the `sys.path.insert` import hack at the top of
  `protocol/tcp_console.py` with a normal relative import of the command
  classes from the parent package.

Out of scope: consolidating the duplicate `PylontechBMS` (in `pylontech.py`)
and `TCPConsoleProtocol` code paths.

## Testing

New `pytest` suite over the pure parsers in `pylontech.py` (importable without
Home Assistant). Fixtures are the verbatim captures above.

- `pack_count` derived from the flat table equals 6.
- Absent slots (7 to 16) are excluded; only packs 1 to 6 are present.
- Pack 1: 49.961 V, 0 A, 29.2 C, cell volt low/high 3.330/3.331 V, SOC 98%,
  Base.St Idle. From detail: total capacity 100 Ah, cycle count 40471.
- Pack 3 (verifies indexing to a non-first row): 49.964 V, cell volt low/high
  3.324/3.333 V, SOC 95%, Base.St Idle.
- The Time column space does not misalign any parsed value (e.g. SOC for
  pack 1 is 98, not the `2026-07-12` that a positional read past column 12
  would grab).
- `info` parses barcode and firmware version.

A mixed charge/idle/discharge fixture is included (captured 2026-07-12 while
the stack was cycling). It confirms the current sign convention and the
`Dischg` state, and exercises positive, zero, and negative currents in one
table.

Manual validation: the maintainer will run the branch against the live stack
and confirm entities populate. Live Home Assistant testing is not automated
here.

## Known limitations (documented, not fixed)

- Present packs are assumed contiguous (`1..pack_count`), which holds for the
  target stack. Non-contiguous slots would need the coordinator to iterate the
  set of actually-present indices rather than a range.
- The legacy header-format path is preserved but unverified.
- 13 commands per cycle (1 flat + 6 detail + 6 per-cell) is heavier than a
  single-command design; acceptable at a 30 s interval.

## Current sign convention (confirmed)

Captured while cycling on 2026-07-12: the `Curr` column is positive when
charging (`Base.St` `Charge`) and negative when discharging (`Base.St`
`Dischg`); idle is `0`. `power = V * A` is therefore positive on charge and
negative on discharge, which is the desired behaviour with no sign adjustment.
Base states seen: `Idle`, `Charge`, `Dischg`.

## Serial line-noise robustness

A real capture showed a corrupted row: a spurious line break plus non-ASCII
bytes (`ʘu`). `_exec_cmd` decodes each line as ASCII, so a non-ASCII byte would
raise `UnicodeDecodeError` and fail the whole update cycle. The fix is to
decode with `errors="replace"`, so a noisy byte becomes a replacement
character and the malformed line is simply skipped by the parser (it never
matches a present-pack row). The `pwr <index>` detail view also gains an
extra transient line while active (`Charge Sec.` when charging, `Discharge
Sec.` when discharging), and its `Current` value is negative when
discharging; the key/value detail parser ignores unknown keys and does not
read the detail current (it uses the flat table's signed current), so both are
handled without change.

## Open dependency

None blocking. Both required raw outputs (`pwr`, `pwr 1`) and the command list
(`help`) have been captured. The legacy header format remains unavailable, and
is handled by best-effort fallback rather than verification.
