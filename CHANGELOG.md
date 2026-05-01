# Changelog

## 2026.5.0

### Changes
- Options flow: saving device-selection or duplicate-item settings now immediately re-runs entity discovery with the just-saved options, so newly enabled devices and duplicate item entities are reflected without waiting for a reload.
- Client robustness: JSON endpoint requests now retry login on `403` responses as well as `401`/HTML login responses.
- Testing: added a local pytest setup with coverage for item naming, state parsing, and translation key consistency, and added the test job to the GitHub validation workflow.
- CI maintenance: updated GitHub workflow actions to the current Node.js 24-compatible action versions.
- Documentation: refreshed the README feature summary and corrected the evcc guide battery SoC example entity.

## 2026.4.3

### Changes
- Options UI: grouped the device enable/disable checkboxes into a dedicated collapsible section so the form stays shorter and easier to scan.
- Translations: added localized section labels for the device-selection block in `de`, `en`, `fr`, `it`, and `nl`.

## 2026.4.2

### Changes
- Updated the README to document the new duplicate-item option and the new installation method via the HACS default repository list.
- Added a new option to disable duplicate item entities by default while keeping the UID-based channel item active as the preferred entity; this also improves handling for duplicate-linked channels such as Shelly devices.
- Thing sensors, diagnostics buttons, and parent-device registration now respect the selected device set more strictly, avoiding `via_device` links to deselected parent devices.
- Expanded item-name normalization for additional patterns, including new `kgshelly` handling, plus `pvplant`, `batteryflex`, `solarwattBattery BatteryFlex`, `myreserveethernet_acs`, and variable KACO SunSpec segments.

## 2026.4.1

### Changes
- Discovery refresh: pressing `Update data` now triggers an immediate data refresh and device discovery instead of waiting for the next periodic poll, so newly discovered item sensors and thing diagnostics entities are added right away.
- Diagnostics: compact item statistics, energy sensor write snapshots, and problem-item summaries are now built via shared helpers and tolerate missing or malformed `statusInfo` payloads more robustly.
- Internal cleanup: shared helpers now centralize thing-entity discovery, unique ID construction, selected-device filtering, and repeated config-flow checkbox/error handling.

## 2026.4.0

### Changes
- Removed the `Name prefix` option.
- Device-based entity IDs: item sensor `entity_id`s now use the current Home Assistant device name, including user-renamed device names from setup/device settings. This follows the device-name-first structure planned for a future Home Assistant naming update.
- Entity IDs are rebuilt automatically during initial setup using the schema `device name + sensor name`.
- Integration options now include an explicit action to rebuild entity IDs again using the schema `device name + sensor name`.
- Technical vendor/device prefixes and installation-specific IDs are stripped more consistently during item-name normalization.
- Repeated channel fragments such as `Battery Battery ...` are normalized to a single term.
- Power sensors: transient `unavailable` item values are now debounced with a configurable poll threshold; the last valid power value is kept until the configured unavailable limit is reached, and `0` disables the debounce entirely.
- Sensor type detection: metadata mapping now derives Home Assistant sensor types more reliably from `/rest/things`, including typed `itemType` metadata and `channelTypeUID` fallback inference for channels such as current and voltage.
- Device registry compatibility: fixed `via_device` handling for SOLARWATT sub-devices so Home Assistant no longer warns about references to non-existing parent devices.
- Internal cleanup: removed unused client URL state, consolidated device-name lookup into a shared helper, and simplified the naming/migration flow.

## 2026.3.5

### Changes
- Login/connection fix: setup now validates the connection directly via login + `/rest/items` instead of failing early on a separate probe request that newer SOLARWATT firmware can answer with `401` even when login works.
- Client compatibility: login handling is now more tolerant of current SOLARWATT manager behavior, including redirects and managers that expose the local UI/API via HTTP or HTTPS.
- Registry refactor: split legacy upgrade migrations and ongoing registry cleanup into separate modules, so non-legacy cleanup is no longer grouped under `legacy_migrations.py`.
- Coordinator refactor: moved API client, state parsing, and sensor metadata heuristics into dedicated modules so `coordinator.py` only handles update orchestration.

## 2026.3.4

### Important before updating
- Before updating, enable the integration option `Enable all available sensors (otherwise, the core sensors such as PV, grid, battery, and consumption are enabled)`. This avoids devices ending up with only disabled sensors after the update.

### Changes
- Device mapping: devices are now derived from `/rest/things`, and related item sensors are assigned to the matching devices.
- Device selection: setup and options now let you choose which SOLARWATT things should be created, and the selection is applied consistently to linked item sensors and thing diagnostics entities.
- Options cleanup: the `Enable all sensors` setting has been removed.
- Migration cleanup: obsolete legacy diagnostics entities and orphaned legacy root devices are cleaned up during reload/update.
- Diagnostics cleanup: thing diagnostics for devices without channels are removed during reload/update so no empty diagnostics device remains.

## 2026.3.3

### Changes
- Naming normalization: all device-type rules that strip installation-specific IDs now keep the device ID when multiple devices of that normalized type are present.
- Duplicate-device detection: the multi-device check runs during setup/reload and when pressing `Update data`
- Legacy migration: normalized entity IDs with and without a retained device ID are migrated to the stable raw item-name unique IDs.
- State parsing: OpenHAB states `UNDEF` and `UNINITIALIZED` are now treated like `NULL` and exposed as unavailable instead of invalid string values for numeric Home Assistant sensors.

## 2026.3.2

### Changes
- Naming normalization: all device-type rules that strip installation-specific IDs now keep the device ID only when multiple devices of that normalized type are present in the current item set; existing legacy normalized IDs with and without the device ID are migrated to the stable raw item-name unique IDs.
- Sensor enablement: the `Enable all sensors` option now enables integration-disabled item sensors immediately, auto-enables newly discovered sensors while active, and disables only the sensors it had auto-enabled when turned off again.
- Config flow/options flow: normalized form input handling, preserved internal option keys, and returned field-specific validation errors for host, credentials, scan interval, and energy delta.
- Entity helpers: extracted item-sensor unique ID migration and enablement logic into a shared helper module used during setup and sensor creation.
- Client robustness: unified JSON fetch handling for `/rest/items` and `/rest/things` with one reauthentication retry when SOLARWATT returns `401` or an HTML login page.
- Documentation/translations: updated the `Enable all sensors` wording in the README and all shipped UI translations to match the new behavior.

## 2026.3.1

### Changes
- HACS minimum Home Assistant version raised to `2024.6.0` because runtime data is now stored via `entry.runtime_data`.
- Runtime data handling: migrated coordinator storage/access from `hass.data` to `entry.runtime_data` across setup, platforms, and diagnostics.
- Branding: moved assets from `brands/solarwatt_manager/` to `custom_components/solarwatt_manager/brand/` and added `@2x` icon/logo variants.
- Translations: replaced `strings.json` with `translations/en.json` and added `fr`, `it`, and `nl` translation files.
- Entity metadata: unified device metadata via shared `build_device_info()` helper and aligned the model string.
- Client cleanup: removed unused item-fetch path from the coordinator client.

## 2026.3.0

### Changes
- Added GitHub validation workflow (`hacs/action` + `hassfest`) for HACS/Home Assistant checks.
- Added HACS brand assets under `brands/solarwatt_manager/`.
- Improved config-flow host validation/normalization (hostname/IPv4 with optional `:port`; URL-style input is rejected).
- Changed expected input/connection logs in config flow from `error` to `warning`.
- Updated discovery behavior: new item/thing entities are discovered on setup and when pressing the refresh button (not on every poll cycle).
- The diagnostics button now triggers a full discovery refresh (`items` + `/rest/things`).
- Switched sensor `unique_id` to raw item keys and added migration for existing entities.
- Manifest updates: `integration_type` added and logger namespace aligned.

## 2026.2.4

### Changes
- Name normalization: added `solarwattBattery_batteryflex_BatteryFlex_<ID>_...` rules so these BatteryFlex item names are normalized to `batteryflex_...` consistently.

## 2026.2.3

### Changes
- Name normalization: `mystrom_switch_<ID>_...` now keeps the device ID and is normalized to `mystrom_<ID>_...` (avoids collisions when multiple myStrom devices are present).
- Display names: added formatting replacements for `fronius` -> `Fronius` and `mystrom` -> `myStrom`.

## 2026.2.2

### Changes
- Setup robustness: ensure coordinator/client cleanup if config-entry initialization fails.
- State parsing: keep textual `ON`/`OFF` values for non-switch items and pass OpenHAB item type through parsing.
- Connectivity probing: map probe transport errors to connection errors instead of "not a manager".
- Thing sensors: dynamically add newly discovered `/rest/things` entities after setup.

## 2026.2.1

### Changes
- Documentation: moved/renamed the evcc guide to `docs/evvc-guide-german.md` and linked it from the README.
- Documentation: added a Kiwigrid items overview and refined item descriptions/translations.
- Energy sensors: keep the last valid energy value when incoming data is invalid (NULL/unavailable); preserve delta-based updates.

## 2026.2.0

### Notes
- Switched to calendar-based versioning (format: `YYYY.M.PATCH`) to better align with the Home Assistant ecosystem.

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
