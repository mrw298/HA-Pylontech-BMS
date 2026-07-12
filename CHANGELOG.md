# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
  - Show correct per-pack device identity (model, serial/barcode, firmware,
    cell count) via `info <index>`, instead of cloning one value to every
    pack. Fixes mixed stacks (e.g. US5000 + US2000C) and the "Unknown"
    barcode/firmware caused by an order-sensitive `info` parser. Entity
    unique IDs are bumped (`-v3`), so stale "Unknown" devices/entities from
    earlier versions should be deleted after upgrading.

### Added
- Per-pack total capacity and health statuses from the `pwr <index>`
  detail view.
- Per-cell voltages and a per-pack cells-balancing count from the
  `bat <index>` command.

## [1.1.0] - 2024-11-12

### Added
- Multi-pack support with separate devices per pack
- Per-pack sensor detection and entity creation
- Binary protocol support for enhanced data access
- SOK battery variant support
- Customizable device names via configuration
- Console protocol support for v3+ firmware
- Dynamic sensor discovery based on BMS capabilities
- Comprehensive status sensors (protect, system, fault, alarm)
- Temperature sensors with proper naming (cells 1-4, 5-8, etc.)

### Fixed
- Byte order correction for binary protocol (little-endian)
- Two-byte prefix handling in analog data responses
- Cell count and temperature sensor parsing
- Entity naming and suggested_object_id generation
- Device grouping and hierarchy

### Changed
- Removed verbose debugging logs for production use
- Improved error handling and connection validation
- Enhanced sensor precision for voltage readings (3 decimals)
- Optimized polling intervals and connection management

## [1.0.0] - Initial Release

### Added
- Initial implementation of Pylontech BMS integration
- TCP console protocol support
- Basic sensor entities
- Config flow for setup
