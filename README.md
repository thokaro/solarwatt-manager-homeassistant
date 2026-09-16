[![Version](https://img.shields.io/github/v/release/thokaro/solarwatt-manager-homeassistant)](https://github.com/thokaro/solarwatt-manager-homeassistant/releases)
[![Platform](https://img.shields.io/badge/Platform-Home%20Assistant-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS Default Repository](https://img.shields.io/badge/HACS-Default%20Repository-41BDF5.svg)](https://hacs.xyz)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://paypal.me/thokaro)
[![Support via Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/thokaro)

# SOLARWATT Manager – Home Assistant Integration

This custom integration connects a **SOLARWATT Manager** like FLEX or Rail to **Home Assistant** and provides local Manager data, optional **KiwiGrid HEMS** data from the SOLARWATT Manager Portal, analytics, controls, live flow values, and diagnostic sensors.

The minimum supported Home Assistant version is **2024.12.0**.

Note for users with **vision** components: If you need write/control functions such as work mode, maximum charge current, discharge current, or battery SoC via Modbus, try [nathanmarlor/foxess_modbus](https://github.com/nathanmarlor/foxess_modbus). For SOLARWATT Vision battery setups, the fork [WiIIiam278:feat/ivo-and-ivt](https://github.com/WiIIiam278/foxess_modbus/tree/feat/ivo-and-ivt) may be the better fit.

⚠️ **EnergyManager pro** is not supported through the local Manager API in this integration. You can still use the optional **KiwiGrid HEMS** / SOLARWATT Manager Portal connection for supported HEMS devices, analytics, and controls. If you need direct local EnergyManager pro support, use https://github.com/Mas2112/solarwatt-energymanager-homeassistant instead.

---

## ✨ Features

* Local polling of SOLARWATT Manager data
* Local values from `/rest/hems-configurator/energy-overview` and device metadata from `/rest/hems-configurator/things`
* Automatic KiwiGrid HEMS polling when KiwiGrid/SOLARWATT Manager Portal login credentials are configured
* KiwiGrid HEMS devices, including smart-heater temperature, diagnostics, today values, month totals, year totals, and finance values
* Separate `KiwiGrid Flow` device for live SOLARWATT Manager Portal energy-flow values
* KiwiGrid HEMS controls for supported devices:
  * `select` entity for optimization mode (`Not optimized`, `PV optimized`, `Departure time`)
  * `switch` entity for supported plug/EV station switching
* Energy Dashboard ready (correct `device_class` & `state_class`)
* Separate polling intervals for local values, cloud Flow, devices, and statistics; HEMS devices default to 30 seconds
* Configurable user profile cache, defaulting to one hour
* Automatic normalization of units and item names, including Wh → kWh conversion, removal of installation-specific IDs, collapsed duplicate fragments and preserved abbreviations such as BMS/SoC/SoH
* Device-based entity structure: entities are assigned to their SOLARWATT devices, while Home Assistant manages their `entity_id`s from integration-provided naming suggestions and the user's naming preference
* Human-friendly display names (Title Case; BMS/SoC/SoH preserved)
* Per-device diagnostics from the available local thing-metadata endpoint, with status sensors, thing properties as attributes, and refresh buttons for item and thing discovery
* Stable `unique_id`s and metadata for long-term statistics, history, and Home Assistant statistics

---

## 📦 Installation

This integration is part of the default **HACS** repository list.

### Option 1: Installation via HACS

1. Make sure **HACS** is installed in your Home Assistant instance
2. Open **HACS**
3. Search for **SOLARWATT Manager**
4. If needed, filter by **Type: Integration**
5. Install the integration
6. Restart Home Assistant

---

### Option 2: Manual Installation

1. Download or clone this repository
2. Copy the folder:

```
custom_components/solarwatt_manager
```

into your Home Assistant configuration directory:

```
config/custom_components/
```

3. Restart Home Assistant

---

## ⚙️ Configuration

After restarting Home Assistant:

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **SOLARWATT Manager**
4. Enter at least one connection type:
   * **Local Host/IP**: hostname or IPv4 address, optionally with `:port`. New forms are prefilled with `energymanager.local`.
   * **Local username** / **Local password**: your local SOLARWATT Manager credentials
   * Optional tuning values such as **Update interval**, **Energy delta**, and **Power unavailable threshold** can be set here already or adjusted later in the integration options
   * Optional KiwiGrid HEMS credentials can be configured with **KiwiGrid (SOLARWATT Manager Portal) username or email address** and **KiwiGrid (SOLARWATT Manager Portal) password**. Entering both fields automatically activates KiwiGrid HEMS, KiwiGrid Flow, and the available HEMS devices and statistics.
   * Do not enter a full URL for the local host. The integration automatically tries HTTP and HTTPS.
5. Select the SOLARWATT devices you want to create. SOLARWATT Flow, KiwiGrid Flow, KiwiGrid Stats, and battery devices are preselected when available.

At least one complete data source is required. You can configure **local access only**,
**KiwiGrid Online only**, or **both**. Saving an installation without either a local
Manager connection or complete KiwiGrid credentials is rejected.
For a KiwiGrid-only installation, the untouched local defaults are ignored automatically.

### Local SOLARWATT Manager vs. KiwiGrid Online

The setup and options forms separate both data sources into their own sections:

| Area | Connection | Data provided | Internet required |
| --- | --- | --- | --- |
| **Local SOLARWATT Manager** | Manager host/IP plus local username and password | `SOLARWATT Flow` and locally detected device metadata | No |
| **KiwiGrid Online (SOLARWATT Portal)** | Portal username/email plus password | `KiwiGrid Flow`, `KiwiGrid Stats`, supported portal devices, diagnostics, and controls | Yes |

When both sources are configured, they remain independent: local live values continue
to work during a portal outage, while KiwiGrid Online adds portal devices and statistics.
The integration keeps both flow devices separate, so their origin is always visible in
Home Assistant.

### SOLARWATT Flow (local)

`SOLARWATT Flow` is the local live energy-flow view. It reads the Manager's
`/rest/hems-configurator/energy-overview` endpoint directly and therefore does not need
the SOLARWATT Portal or an internet connection. It is updated with the general **Update
interval** and contains current power values rather than the portal's historical
statistics.

Its visible sensor names match the equivalent `KiwiGrid Flow` names where the same value
exists, including `PV Out`, `Consumption In`, `Grid In`, `Grid Out`, `Grid Balance`,
`Battery In`, `Battery Out`, `Battery Balance`, and `Battery SoC`. Additional calculated
sensors split household consumption into `Consumption From PV`, `Consumption From Grid`,
and `Consumption From Battery`.

For the balance sensors, a positive `Grid Balance` means grid import and a negative value
means export. A positive `Battery Balance` means battery discharge; a negative value means
charging. The separate `Battery In`/`Battery Out` and `Grid In`/`Grid Out` sensors always
remain non-directional positive values.

### Options

You can adjust these in the integration options:

The local update interval is in **Local SOLARWATT Manager**. Cloud device, Flow,
Stats, and profile cache intervals are in **KiwiGrid Online**. **Sensor settings**
contains the energy-change and power-unavailable thresholds.

* **Update interval (seconds)** – polling interval for local Manager devices and `SOLARWATT Flow`
* **Energy delta (kWh)** – write energy updates only if the change is >= threshold; set to `0` to write every update
* **Power unavailable threshold (polls)** – applies to power sensors only. If SOLARWATT briefly returns `unavailable`, the last valid power value is kept until the configured consecutive poll limit is reached. Example: `3` means the 1st and 2nd `unavailable` poll keep the previous value, and the sensor only switches to `unavailable` on the 3rd poll. Set to `0` to disable this debounce completely.
* **KiwiGrid HEMS credentials** – when both the username/email and password are entered, the integration signs in automatically and activates the detected HEMS devices, `KiwiGrid Flow`, and `KiwiGrid Stats`.
* **HEMS device interval (seconds)** – polling interval for physical KiwiGrid devices. The default is `30` seconds.
* **KiwiGrid Flow interval (seconds)** – separate polling interval for live cloud energy-flow and consumer values. When not yet configured, it follows the existing update interval.
* **KiwiGrid Stats interval (seconds)** – separate polling interval for all cloud analytics, including today, month, year, and derived Total values. When not yet configured, it follows the existing HEMS interval (`30` seconds for new entries). Set it to `300` seconds, for example, to reduce analytics requests.
* **User profile cache duration (seconds)** – reuse the complete profile response, including the currency preference, for `3600` seconds by default. After expiry, the next device or statistics poll refreshes the profile. Failed refreshes retain the last valid profile and are retried on a later poll. Reloading the integration or changing credentials clears the cache.
* **Device selection** – choose which detected SOLARWATT devices should be created in Home Assistant

All interval options accept `10` to `3600` seconds. Existing installations keep their
previous Flow and Stats cadence until these options are changed; no migration is
required. The profile cache is enabled by default. Profile changes can therefore take
up to the cache duration plus one device/statistics poll to appear.

Connection settings can also be changed with Home Assistant's **Reconfigure** action.
Changed credentials are validated before they are saved. If either the local Manager or
KiwiGrid HEMS rejects its credentials during an update, Home Assistant opens a
reauthentication flow. In combined installations, the other working source remains
available and the integration keeps the last valid snapshot of the failed source.
Failed device and statistics polls are retried at their respective intervals.
Failed Flow polls wait at least the HEMS device interval and the Flow interval.
Within a HEMS poll, up to four isolated connection failures are retried once in
sequence after the bounded parallel first pass. Endpoints that still fail keep their
latest successful cached payload and are reported as partial diagnostics without
marking the complete HEMS source unavailable. Consumption, production, storage, and
finance month and year totals read their completed days once per day and add today's
aggregate on every Stats poll. Energy totals use matching `WORK` day series; production
and storage each require one additional daily-range request per Stats poll. Derived
Total sensors therefore continue to follow the Stats interval. A later correction to
an already completed day becomes visible with the next daily refresh.
Month and year independence ratios (autarky and self-consumption) are fetched directly
from the portal on the first successful Stats poll of each calendar day and retain
that snapshot for the rest of the day. Today's ratios still follow the Stats interval.
Reloading the integration or changing credentials clears these daily caches.

Compared with the finance-only daily cache, regular analytics requests decrease from
14 to 8 per Stats poll, plus 10 daily summary requests instead of 2. For example:

| Stats interval | Previous requests/day | New requests/day | Requests saved/day |
| --- | ---: | ---: | ---: |
| 30 seconds | 40,322 | 23,050 | 17,272 |
| 60 seconds | 20,162 | 11,530 | 8,632 |
| 300 seconds | 4,034 | 2,314 | 1,720 |

These estimates cover analytics only, assume continuous operation with successful
requests and no reloads, and apply away from month/year boundaries. On the first day
of a period, its completed-day requests are skipped. Device, Flow, profile, and
authentication requests are additional and unchanged.

The integration identifies a local installation by the Manager's detected location UID
and a cloud-only installation by an anonymized account identifier. Changing the local
hostname or IP address through **Reconfigure** therefore keeps the same Home Assistant
devices and entity unique IDs.

---

### Poll interval assignment

Poll intervals are assigned by data source, not by sensor type or device class. A power
sensor therefore does not automatically use the faster update interval.

| Data source / device | Poll configuration |
| --- | --- |
| All local SOLARWATT Manager devices and items | Update interval |
| Local `SOLARWATT Flow` | Update interval |
| `KiwiGrid Flow`, including live consumer values | KiwiGrid Flow interval |
| KiwiGrid batteries, PV plants, EV chargers, plugs, smart heaters, meters, inverters, and other physical HEMS devices | HEMS device interval |
| `KiwiGrid Stats`, including today, month, year, and derived Total values | KiwiGrid Stats interval |
| `KiwiGrid Stats` consumption, production, storage, and finance month/year totals | Completed days once per day when statistics are polled; today's value on every Stats poll |
| `KiwiGrid Stats` independence month/year ratios | First successful Stats poll of each calendar day |

For example, set the local update interval to `15`, Flow to `30`, HEMS devices to
`30`, Stats to `300`, and the profile cache to `3600` seconds. Local power remains
fast, cloud Flow requests are halved compared with a 15-second interval, and regular
statistics requests fall by about 60% compared with a 120-second interval.

The shared coordinator checks due groups at the shortest active polling interval.
An interval that is not a multiple of that timer is served on the next coordinator
update; network delays can also extend the effective interval. Groups that are not
due reuse their complete cached payloads. All entities read the shared snapshot;
individual entities do not perform HTTP requests.

---

## ☁️ KiwiGrid Online (HEMS)

KiwiGrid Online is the optional portal-backed part of the integration. It uses the same SOLARWATT/KiwiGrid web login flow as the SOLARWATT Manager Portal. You only need username/email address and password; no local Manager address is required for an online-only installation.

When complete portal credentials are configured, the integration adds supported HEMS data from the SOLARWATT Manager Portal:

* HEMS devices such as batteries, PV systems, EV chargers, plugs, smart heaters, meters, and inverters
* Current smart-heater temperature assigned to the API-provided device name
* current device state, diagnostic metadata, and supported optimization settings
* today values for consumption, production, storage, independence, and finance
* month and year energy totals for consumption and production
* live flow values under the separate `KiwiGrid Flow` device
* controls for supported EV charger and plug optimization or switching

HEMS metadata such as type, device state, optimization mode, switch state, and override requirements is exposed as diagnostic sensors. Device metadata such as manufacturer, model, firmware, and serial number is mapped to Home Assistant device information instead of separate ordinary sensors.

Physical HEMS devices are attached to their real device where possible. Daily and monthly/yearly portal statistics are grouped under the `KiwiGrid Stats` device, for example:

```
sensor.kiwigrid_stats_today_consumption_powerconsumed
sensor.kiwigrid_stats_month_consumption_workconsumed
sensor.kiwigrid_stats_year_consumption_workconsumed
```

Today values expose totals and the latest live value where available. Month and year values expose energy totals in kWh.

For year-based KiwiGrid energy statistics, the integration also creates derived `Total ...`
sensors with `state_class: total_increasing`. These sensors keep a persistent rollover
base, so when the portal year value resets at the start of a new year, the last value
from the previous year is added to the new year value.
They also persist the highest calculated total. If the portal corrects a year value
downward, the Total sensor holds its previous value until the corrected calculation
catches up. For example, calculated values of `1000 → 990 → 995 → 1002 kWh` are
published as `1000 → 1000 → 1000 → 1002 kWh`. The corrected raw year value is still
used for rollover, so the correction is not added back at New Year. This protection
survives restarts and does not require additional requests. Explicit offset and
calibration services can still change the displayed total, including lowering it.

The offset can be calculated automatically from the KiwiGrid year history. The
service reads completed previous years only and stores their sum as the offset. The
current year is not read for the offset because it already comes from the live year
sensor. The Total sensor value is therefore:

```
max(previous highest calculated total, rollover base + current year value) + calibration offset
```

The history service supplies the calibration offset from completed previous years.

`max_years` limits how many completed previous years are read. For example, in 2026
`max_years: 3` reads at most 2025, 2024, and 2023, stopping earlier when no value is
returned. The calculation runs in the background so Home Assistant's service call does
not time out while historic KiwiGrid values are being fetched. Historic KiwiGrid requests
may run for up to 5 minutes each. When calculating all sensors, fetched year payloads are
reused across sensors.

For all registered Total stats sensors, use the all-service:

```yaml
service: solarwatt_manager.calculate_all_stats_values
data:
  max_years: 20
```

For one or more selected sensors:

```yaml
service: solarwatt_manager.calculate_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
data:
  max_years: 20
```

To calibrate a Total sensor to a known meter value, set `value`. This is the desired
Total sensor value in kWh. The integration stores the required offset internally:

```yaml
service: solarwatt_manager.set_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
data:
  value: 12345.67
```

To set the offset itself, use `offset`. This value is added directly to the calculated
Total value:

```yaml
service: solarwatt_manager.set_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
data:
  offset: 1000
```

The current offset is exposed as a sensor attribute.

Use either `value` or `offset`, not both. To remove the calibration:

```yaml
service: solarwatt_manager.reset_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
```

### KiwiGrid Flow

`KiwiGrid Flow` is a dedicated device for live energy-flow and consumer values from the SOLARWATT Manager Portal. It is independent from the local `SOLARWATT Flow` device and is also available when both local Manager access and KiwiGrid HEMS are configured. Example sensors:

```
sensor.kiwigrid_flow_consumption_in
sensor.kiwigrid_flow_grid_in
sensor.kiwigrid_flow_grid_out
sensor.kiwigrid_flow_battery_out
sensor.kiwigrid_flow_battery_soc
sensor.kiwigrid_flow_battery_balance_evcc
sensor.kiwigrid_flow_solarwatt_battery_vision_three_out
sensor.kiwigrid_flow_mystrom_waschmaschine_consumption
sensor.kiwigrid_flow_keba_p30_pv_edition_consumption
sensor.kiwigrid_flow_mystrom_wasserpumpe_consumption
```

These sensors show the current portal values.

`Battery Balance EVCC` is the automatically inverted `Battery Balance` value:
battery discharge is positive and battery charging is negative, matching EVCC's
battery-meter sign convention.

### HEMS Controls

For devices that expose supported optimization metadata in the SOLARWATT Manager Portal, the integration can create:

* an optimization mode `select`
* an on/off `switch`

The switch keeps the requested state locally for a short time after sending the command so the Home Assistant UI does not immediately jump back when the HEMS endpoint still returns the old state for a moment.

---

## 🔋 Energy Dashboard

Energy sensors are provided in kWh and prepared for the Energy Dashboard (`device_class: energy`, `state_class: total` or `total_increasing`, depending on whether the value is cumulative or strictly increasing). Which sensors you use depends on your setup.

---

## SOLARWATT Firmware 10.26.24.4

On a tested SOLARWATT Manager with KiwOS Edge `10.26.24.4` / EM setup feature `4.64.1.45`, local values and device metadata are exposed under:

* `/rest/hems-configurator/energy-overview` - live production, grid, household, and battery power values
* `/rest/hems-configurator/things` - thing/device metadata

The integration reads local values directly from the HEMS configurator Energy Overview endpoint. They are exposed under the dedicated `SOLARWATT Flow` device. Stable internal item keys still follow the JSON fields, while the visible sensor names match their `KiwiGrid Flow` counterparts where equivalent:

* `production` → `PV Out`
* `feedIn` → `Grid Out`
* `feedOut` → `Grid In`
* `householdConsumption` → `Consumption In`
* `storagePowerIn` → `Battery In`
* `storagePowerOut` → `Battery Out`
* Derived values include `Grid Balance`, `Battery Balance`, `Consumption Direct Consumption`, and `Battery SoC`

The `SOLARWATT Flow` device must be enabled in the integration options/device selection for those sensors to be created.

Firmware must provide both HEMS configurator endpoints. The former `/rest/things`
metadata fallback and legacy item aliases are no longer supported.

For SOLARWATT Vision battery SoC, use the FoxESS integration [nathanmarlor/foxess_modbus](https://github.com/nathanmarlor/foxess_modbus/) or preferably the fork [WiIIiam278:feat/ivo-and-ivt](https://github.com/WiIIiam278/foxess_modbus/tree/feat/ivo-and-ivt). You can then create a SOLARWATT-adjusted SoC as a template sensor.

In `configuration.yaml`:

```yaml
template:
  - sensor:
      - name: "SOLARWATT Speicher SoC"
        unique_id: solarwatt_speicher_soc
        unit_of_measurement: "%"
        device_class: battery
        state_class: measurement
        availability: "{{ is_number(states('sensor.foxess_battery_soc')) }}"
        state: >
          {% set reserve = 10 %}
          {% set fox = states('sensor.foxess_battery_soc') | float %}
          {% set solarwatt = ((fox - reserve) / (100 - reserve)) * 100 %}
          {{ solarwatt | clamp(0, 100) | round(0) }}
```

Adjust only this entity ID to match your FoxESS SoC sensor:

```yaml
sensor.foxess_battery_soc
```

The `reserve` value (`10` in the example) represents the storage reserve configured in EnergyManager. Adjust it if your EnergyManager reserve is different.

---

## 🚗 evcc Sensors

For a local evcc setup, use `Grid Balance`, `PV Out`, `Battery Balance`, and
`Battery SoC` from the `SOLARWATT Flow` device. Local `Battery Balance` already
uses evcc's expected sign convention: positive means discharging and negative
means charging.

When using `KiwiGrid Flow` instead, select `Battery Balance EVCC` for battery
power because the regular online `Battery Balance` uses the opposite sign. Keep
Grid, PV, and battery power on the same flow source when possible so their update
timestamps match. Entity IDs are managed by Home Assistant; copy the actual IDs
from your installation rather than relying only on the examples.

The full configuration examples and migration notes are available in the German guide:

* [evcc guide (German)](docs/evcc-guide-german.md)

---

## 📋 Kiwigrid Items

Here you will find an overview of the most important Kiwigrid items.

* [kiwigrid-items.md](docs/kiwigrid-items.md)

---

## 🧠 Naming Strategy

* The integration provides normalized sensor-name suggestions while Home Assistant creates and manages entity IDs
* Duplicate words and installation-specific IDs are removed where possible
* Physical KiwiGrid HEMS entities stay on their device
* KiwiGrid statistics are grouped under `KiwiGrid Stats`
* Live flow and consumer values are grouped under `KiwiGrid Flow`
* Home Assistant 2026.8 and newer can recreate existing IDs from the entity or device page using the user's selected naming pattern

The integration does not rewrite existing entity IDs, so user-defined IDs and references in automations remain unchanged unless the user explicitly recreates them in Home Assistant.

---

## 🛠️ Development

### Repository Structure

```
.
├─ custom_components/
│  └─ solarwatt_manager/
│     ├─ __init__.py         # integration setup
│     ├─ button.py           # diagnostics refresh button
│     ├─ client.py           # local Manager API and KiwiGrid HEMS wrapper
│     ├─ config_flow.py      # UI config flow
│     ├─ const.py            # constants & defaults
│     ├─ coordinator.py      # polling orchestration + thing discovery
│     ├─ diagnostics.py      # diagnostics output
│     ├─ entity_helpers.py   # entity/device helper utilities
│     ├─ hems_api.py         # local HEMS configurator mapping helpers
│     ├─ hems_client.py      # KiwiGrid HEMS login, endpoints, and payload mapping
│     ├─ manifest.json       # integration metadata
│     ├─ naming.py           # name normalization/formatting
│     ├─ registry_cleanup.py # ongoing registry cleanup for current layouts
│     ├─ registry_migrations.py # upgrade paths for older entity/device layouts
│     ├─ select.py           # KiwiGrid HEMS optimization mode select entities
│     ├─ sensor.py           # sensor entity definitions
│     ├─ sensor_meta.py      # Home Assistant sensor metadata heuristics
│     ├─ state_parser.py     # item state parsing + normalization
│     ├─ switch.py           # KiwiGrid HEMS switch entities
│     ├─ brand/
│     │  ├─ icon.png
│     │  ├─ icon@2x.png
│     │  ├─ logo.png
│     │  └─ logo@2x.png
│     └─ translations/
│        ├─ de.json          # German translations
│        ├─ en.json          # English translations
│        ├─ fr.json          # French translations
│        ├─ it.json          # Italian translations
│        └─ nl.json          # Dutch translations
├─ docs/
│  ├─ evcc-guide-german.md   # evcc setup guide
│  └─ kiwigrid-items.md      # item reference for KiwiGrid systems
├─ tests/                    # pytest coverage for mapping, naming, parsing, translations
├─ CHANGELOG.md              # release history
├─ hacs.json                 # HACS metadata
├─ LICENSE
├─ pyproject.toml            # package metadata and pytest configuration
└─ README.md
```

### Versioning

The integration version is defined in:

```
custom_components/solarwatt_manager/manifest.json
pyproject.toml
```

See `CHANGELOG.md` for release notes. GitHub releases follow calendar-based versioning 📅:

```
YYYY.M.PATCH
```

---

## 🐞 Issues & Support

Please report bugs and feature requests via GitHub Issues:

* [https://github.com/thokaro/solarwatt-manager-homeassistant/issues](https://github.com/thokaro/solarwatt-manager-homeassistant/issues)

Include logs and (if possible) diagnostics to help troubleshooting.

Diagnostic exports anonymize device, entity, and item identifiers and redact credentials,
personal labels, location data, error messages, and text sensor values. Numeric readings,
units, device status, and counters remain available. These changes affect only the export;
live entities and their identifiers remain unchanged.

---

## 📄 License

This project is licensed under the **Apache License 2.0**.

---

## 🙏 Disclaimer

This project is not affiliated with or endorsed by **Solarwatt GmbH**. All trademarks belong to their respective owners.
