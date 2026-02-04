# Changelog

## 2026.2.0

### Notes
- Switched to calendar-based versioning (format: `YYYY.M.PATCH`) to better align with the Home Assistant ecosystem.
- No functional regressions compared to previous releases.

### Changes
- Added an Energy Delta threshold (kWh) to reduce energy sensor writes; updates only when the delta is reached (0 = always).
- Expanded display-name replacements (AC, DC, PV, MPPT, ACS, SMA, KEBA, SunSpec, INV, Modbus, FoxESS, FoxESSInv).

## v0.4.1

### Changes
- Sensor display names are now Title Case with exceptions for BMS/SoC/SoH.

## v0.4.0

### Highlights
- More stable polling with a higher minimum update interval
- More robust unit detection and normalization
- Improved diagnostics for support

### Changes
- Raised the minimum update interval to 10 seconds; updated validation messages accordingly.
- Added unit detection from `stateDescription.pattern`, normalized Unicode/units, and auto-converted milli/micro units.
- Items with names ending in `Seconds`/`sec` are classified as `SensorDeviceClass.DURATION` (default unit: seconds).
- Items containing `temperature`/`temperatur` in the name are classified as `SensorDeviceClass.TEMPERATURE` (default unit: C).
- Expanded diagnostics: compact item payloads, stats, samples (first/last 50), and a compact Things summary.

## v0.3.1

### Added
- Batteryflex normalization (strip installation IDs) and default-enabled sensor groups for `harmonized_` and `batteryChannelGroup_`.
- SunspecNext KACO normalization: device block shortened to `kacoinv_` while preserving suffix groups like `harmonized_`, `inverter_`, `limitable_`.

### Changed
- Diagnostics device model renamed to `Manager flex - rail`.
- Documentation updated: diagnostics entities exposed from `/rest/things`.

## v0.3.0

### Added
- Diagnostics data from `/rest/things` with devices and their attributes exposed as diagnostic entities.
- Button to refresh diagnostics data on demand.

### Changed
- Diagnostics data fetched only on setup/update or via the refresh button (no polling).

## v0.2.0

### Added
- New toggle to enable all sensors by default (or keep only the core PV/grid/battery/consumption set).

### Changed
- Dropped the `item_names` filter; all items are now loaded every update (existing `item_names` options are ignored).
- Cleaned up `naming.py`: grouped default patterns and cached normalization regexes for faster lookups.

## v0.1.1

### Changes
- Smarter connection errors: clearer auth vs connectivity vs non-SOLARWATT host detection.
- UI texts polished: added missing strings and translations.
- Better device UX: configuration URL shown in Home Assistant.
- Expanded name normalization (foxessinv, foxessmeter, keba, mystrom, sma, pvplant).
- Sensors now use CoordinatorEntity for consistent polling.

## v0.1.0

### Changes
- Added a full Home Assistant config flow (host/IP, credentials, optional item list, scan interval, name prefix).
- Implemented local polling of the SOLARWATT REST API with robust session cookie handling for IP hosts.
- Added sensor metadata mapping and unit normalization (Wh -> kWh) for Energy Dashboard compatibility.
- Normalized entity names to improve readability while keeping stable identifiers.
- Added diagnostics output with redaction for sensitive data.
- Declared minimum Home Assistant version 2023.8.0 (HACS).
