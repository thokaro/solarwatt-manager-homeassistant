# Changelog

## Unreleased

### 🛠️ Changes

- Documented the existing battery backup status, reserve, mode, and charge sensors with an emergency-power notification example. Added regression coverage for the KATEK SolBrid payload from issue #19, both backup flag states, reserve limits, and omitted fields. Existing entities, names, unique IDs, and polling behavior are unchanged; no migration is required.
- Gave month and year analytics requests their own 30 second timeout, while today's requests keep the 10 second default. Those ranges are priced one ISO week at a time on the portal and regularly need longer than 10 seconds, so their daily cache entry was never stored and the request was repeated on every poll instead of once per day.

## 2026.9.3

**Update behavior:** Month/year autarky and self-consumption ratios now update once
per calendar day. Energy totals, including derived Total sensors, continue to update
at the configured KiwiGrid Stats interval. Today's ratios also retain that interval.

### ✨ Features

- Added protection for derived KiwiGrid Stats Total energy sensors against downward portal corrections. Persist the highest calculated total across restarts while retaining the corrected raw value for calendar-year rollover, so corrections do not cause false meter resets or get counted twice. Explicit calibration and offset changes remain supported.

### 🛠️ Changes

- Consolidated daily analytics cache handling for completed-day totals and portal ratios, with one validation and expiry path and explicit tracking of cache hits. The refactor preserves the polling, request counts, retries, and Total protection described in this release.
- Extended the finance daily cache to consumption, production, and storage month/year totals. Completed days are fetched once per calendar day and combined with today's matching WORK energy series on every Stats poll. Production and storage each add one current-day WORK request per poll; existing live POWER sensors remain unchanged.
- Month/year autarky and self-consumption ratios now retain the portal value from the first successful Stats poll of each day. Today's ratios remain live; percentages are never added together.
- Regular analytics requests decrease from 14 to 8 per Stats poll, with 10 daily summary requests instead of 2: approximately 17,272 fewer requests per day at a 30-second Stats interval, excluding retries and reloads.

### ⬆️ Upgrade notes

- Existing sensor names and unique IDs remain unchanged; no config-entry migration is required. Derived Total energy sensors still follow the Stats interval. Corrections to completed-day energy values appear after the next daily refresh; month/year ratios update daily. Reloading the integration clears the caches.
- Existing Total state records acquire the optional persisted high-water value automatically from their saved base and last year value; no manual storage migration is needed. Downward corrections remain visible in the source year sensor while derived Total sensors wait for the corrected sum to catch up.

## 2026.9.2

### ✨ Features

- Added separate configurable KiwiGrid Flow and Stats intervals so local values and cloud devices can remain responsive while cloud Flow and analytics are polled less often. Existing installations retain their previous intervals until the new options are changed; entity identifiers and config-entry versions are unchanged.
- Cache the complete KiwiGrid user profile for a configurable duration, defaulting to one hour. Refresh failures retain the previous profile, while integration reloads and credential changes clear the cache. Changes to profile preferences such as currency appear after cache expiry and the next device/statistics poll.

### 🐛 Fixes

- Preserve the last valid finance day, month, and year values and report a partial error when today's finance response is malformed. Valid empty time series remain supported.
- Clarified local Manager and SOLARWATT Manager portal credentials in all five translations, including the relevant login URLs and the local default username. Connection descriptions use plain text without relying on Markdown links or line breaks.

### 🛠️ Changes

- Grouped polling intervals with their respective local and KiwiGrid Online connection settings. The general section is now named Sensor settings and contains only sensor thresholds, with updated descriptions in all five languages.
- Reduced the portal load of the finance month and year totals by requesting their completed days once per day and adding today's aggregate on each statistics poll. This optimization is limited to additive finance totals; ratio series such as independence continue to use server-calculated values. A later correction to an already completed day becomes visible with the next daily refresh.
- Set the default HEMS device interval to 30 seconds for new or not explicitly configured entries. Saved intervals remain unchanged. Without an explicit Stats interval, statistics follow the HEMS device interval; set Stats to 300 seconds to reduce regular analytics requests.

### ⬆️ Upgrade notes

- No config-entry migration is required. Entity unique IDs and existing sensor names remain unchanged.
- After updating and restarting Home Assistant, adjust the separate intervals in the integration options. For example: local 15 seconds, Flow 30 seconds, devices 30 seconds, Stats 300 seconds, and profile cache 3600 seconds.
- The profile cache is enabled by default. Profile preferences such as currency can take up to the cache duration plus one device/statistics poll to update; live energy and finance values continue to follow their own polling intervals.

### 🙏 Thanks

- Thanks to Alexander (@twonky4) for the finance optimization and insights into the Kiwigrid API's server-side workload in [PR #17](https://github.com/thokaro/solarwatt-manager-homeassistant/pull/17).

## 2026.9.1

### Fixes
- Anonymized the complete diagnostics export, including Portal usernames, device/entity/item keys, network and location fields, user labels, error messages, and string sensor values. Numeric readings and structural diagnostics remain available; live entities and cached data are unchanged.
- Replaced deprecated Home Assistant device-registry lookups and parent links with config-entry-scoped lookups and `via_device_id`. Updated device selection, cleanup, diagnostics, and identifier migration to the new registry API while retaining compatibility with older supported Home Assistant versions. Existing identifiers and entity unique IDs remain unchanged; no config-entry migration is required.

### Changes
- Shared select/switch discovery, including device selection, duplicate prevention, and callback cleanup, with platform tests preserving capability differences, late discovery, stable IDs, and command targets.
- Reused the existing entityless-device cleanup for empty-channel devices and shared HEMS identifier resolution between select and switch entities, preserving device selection and identifier behavior.
- Reused common Home Assistant test stubs across platform, registry, and identifier tests.

## 2026.9.0

### Breaking Changes
- Removed the legacy `/rest/things` metadata fallback. Local Manager firmware must now provide `/rest/hems-configurator/things` and `/rest/hems-configurator/energy-overview`.
- Aligned visible SOLARWATT Flow sensor names with their KiwiGrid Flow counterparts, including PV Out, Grid In/Out, Consumption In, Battery In/Out, and balance values, without changing canonical sensor unique IDs.
- Removed locally generated compatibility aliases for item names from the former OpenHAB endpoints. Their old registry entries are disabled by the integration and should be replaced with the canonical `SOLARWATT Flow` sensors.

### Changes
- Added `Battery Balance EVCC` to KiwiGrid Flow, automatically inverting `Battery Balance` so battery discharge is positive and charging is negative as expected by EVCC.
- Renamed the local `Energy Overview` device to `SOLARWATT Flow` while preserving its stable device identifier.
- Removed the redundant local `Battery Charge Power` and `Battery Discharge Power` sensors so SOLARWATT Flow uses the same canonical battery flow values as KiwiGrid Flow: `Battery In`, `Battery Out`, and `Battery Balance`.
- Removed the separate KiwiGrid HEMS activation checkbox; complete Portal credentials now activate HEMS, KiwiGrid Flow, detected HEMS devices, and statistics automatically. Existing entries are migrated and their obsolete checkbox value is removed.
- Separated local SOLARWATT Manager, KiwiGrid Online, and general settings into described setup/options sections. A complete local or KiwiGrid Online source remains mandatory, while configuring both is supported.
- Prefilled new local Manager host fields with `energymanager.local`, while leaving the untouched local defaults inactive in KiwiGrid-only installations.
- Updated the evcc documentation for the local `SOLARWATT Flow` device, including current sensor names, separate local/online examples, sign conventions, and guidance for preserved entity IDs.
- Removed the legacy `/rest/items` polling path and its duplicate-item entity option; local values now come directly from the HEMS configurator Energy Overview endpoint. Existing entries are migrated and their obsolete duplicate option is removed.
- Increased the default KiwiGrid HEMS poll interval from 60 to 120 seconds for new or not explicitly configured entries.
- Retried up to four isolated KiwiGrid HEMS connection failures sequentially after each bounded parallel polling pass, while keeping all analytics periods on the configured HEMS interval.
- Kept KiwiGrid HEMS available when only individual cloud endpoints fail, retaining their latest cached payload and exposing the failures as partial diagnostics.

## 2026.8.0

### Changes
- Added KiwiGrid smart heaters, including the current temperature and maximum AC input power on the API-named device.
- Added validated reauthentication and reconfiguration flows for local Manager and KiwiGrid HEMS connection settings.
- Removed the integration-specific entity ID rebuild option and automatic entity-registry renaming. Home Assistant now controls entity ID naming, and existing entity IDs remain unchanged unless the user explicitly recreates them in Home Assistant 2026.8 or newer.
- Kept local Manager and KiwiGrid HEMS data independently available when only one configured source fails, using the last valid snapshot for the unavailable source.
- Added HEMS retry backoff and availability-transition logging to avoid repeated requests and warning spam during outages.
- Fixed temporary KiwiGrid HEMS login failures such as HTTP 503 being misclassified as invalid credentials and unnecessarily triggering reauthentication.
- Fixed the synthetic `KiwiGrid Stats` diagnostics sensor remaining `unknown` after successful analytics updates.
- Fixed battery device headers showing a backup or minimum state-of-charge value instead of the current `State of Charge`.
- Updated CI to test Python 3.13 and 3.14 and to run Ruff and MyPy checks.
- Reused one authenticated KiwiGrid HEMS client per config entry, fetched independent HEMS endpoints with bounded concurrency, and kept the latest successful payload for temporarily failing endpoints.
- Reused cached HEMS device metadata for the fast KiwiGrid Flow poll instead of requesting all device-name endpoints every time.
- Fixed device selection and orphan-device cleanup for cloud-only KiwiGrid HEMS entries.
- Raised the minimum supported Home Assistant version to 2024.12.0 to match Python 3.13 and enabled MyPy checks for all integration modules.
- Replaced host/IP-based config-entry and device identifiers with stable installation IDs. Existing devices are migrated in place, so changing the Manager address does not create duplicates and entity unique IDs remain unchanged.
- Removed the superseded registry migrations from older releases; the migration module now contains only the stable installation-ID migration, while ongoing empty-device handling stays in registry cleanup.
- Redacted connection and installation identifiers from diagnostics and updated device lookup to use the stable registry anchor.
- Cached the working local items/things endpoint after capability detection, avoiding repeated `404` fallback requests on old and new Manager firmware.
- Reused cached local thing metadata for Energy Overview compatibility aliases instead of requesting device metadata during every local value poll.
- Fixed duplicate local and KiwiGrid HEMS devices in setup device selection, including KEBA wallboxes and multiple named myStrom switches.
- Normalized display-name acronyms consistently to `PV`, `SoC`, and `EV` without changing other name casing.

## 2026.7.4

### Changes
- Fixed KiwiGrid Stats Total sensors repeatedly adding transiently decreasing year values by limiting rollovers to actual calendar-year changes.
- Moved device selection to the top of the integration options and clarified which data sources use the local and KiwiGrid HEMS poll intervals.
- Unified local and KiwiGrid thing matching so duplicate physical devices are merged consistently during discovery and option selection.
- Added KiwiGrid HEMS update status to diagnostics and extended diagnostic redaction to serial-number fields.
- Documented the poll interval assignment for local devices, KiwiGrid Flow, physical KiwiGrid devices, and KiwiGrid Stats.

## 2026.7.3

### Changes
- KiwiGrid Stats: added derived year-to-total energy sensors with persistent rollover handling and calibration offset services.
- KiwiGrid Stats: added services to calculate offsets automatically from completed previous KiwiGrid year values, either for all Total sensors or selected sensors.

## 2026.7.2

### Changes
- KiwiGrid analytics: added month and year values for storage, independence, and finance.
- KiwiGrid analytics: removed the redundant PV optimization consumption endpoint.
- KiwiGrid analytics: removed duplicate physical-device analytics sensors and cleans up previously registered duplicates.
- Refactored KiwiGrid analytics endpoint and period mapping to share one central implementation.

## 2026.7.1

### Changes
- KiwiGrid Flow: added live consumer consumption sensors from `/v11/home/consumption/consumers`, including named sensors for HEMS consumers such as plugs and wallboxes.
- KiwiGrid Flow: fetches live consumer consumption together with `/v11/energy-flow` and maps the values to the dedicated `KiwiGrid Flow` device.
- KiwiGrid analytics: grouped synthetic analytics entities under the `KiwiGrid Stats` device and updated generated entity naming examples accordingly.
- KiwiGrid analytics: added daily `WORK` consumption totals and improved month/year consumption and production mapping for HEMS analytics payloads.
- Documentation: refreshed the README wording for KiwiGrid HEMS, KiwiGrid Flow, and naming examples to be less implementation-focused.

## 2026.7.0

### Changes
- Added optional KiwiGrid HEMS / SOLARWATT Manager Portal support for HEMS devices, analytics, finance values, live flow values, and supported optimization or switching controls.
- Added separate HEMS polling and setup fields so local Manager access, HEMS Portal access, or both can be configured. The default HEMS poll interval is now 60 seconds.
- Improved setup device selection by merging local and HEMS device variants where possible and preselecting `Energy Overview`.
- Added month and year energy totals from HEMS analytics.
- Added a dedicated `KiwiGrid Flow` device for live `/v11/energy-flow`, including named per-device flow sensors based on HEMS device metadata.
- Removed obsolete derived and UUID-based legacy KiwiGrid Flow entities during registry migration.
- Documentation: refreshed the README and updated the evcc guide to use the built-in Grid/Battery/PV sensors where available.

## 2026.6.0

### Changes
- Firmware compatibility: added fallbacks for SOLARWATT managers where authenticated requests to the previous `/rest/items` and `/rest/things` endpoints now return `404`.
- On a tested SOLARWATT Manager with KiwOS Edge `10.26.24.4` / EM setup feature `4.64.1.45`, `/rest/hems-configurator/energy-overview` returns live production, grid, household, and battery power values, while `/rest/hems-configurator/things` replaces the previous thing metadata endpoint.
- With SOLARWATT firmware `10.26.24.4`, only the Energy Overview item values can currently be read; the full legacy item list is no longer exposed through `/rest/items`.
- HEMS fallback entities now include a dedicated `Energy Overview` device with sensors named after the JSON fields: `production`, `feedIn`, `feedOut`, `householdConsumption`, `storagePowerIn`, and `storagePowerOut`.
- The `Energy Overview` device must be enabled in the integration options/device selection for those sensors to be created.
- Existing legacy-style power aliases are still generated where possible so existing SOLARWATT devices and entity IDs can keep working with the new firmware.
- Documentation: added guidance for exposing SOLARWATT Vision battery SoC via the FoxESS Modbus integration or the `WiIIiam278/foxess_modbus` `feat/ivo-and-ivt` fork, and clarified that the `10` in the SoC template represents the storage reserve configured in EnergyManager.

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
