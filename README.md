[![Version](https://img.shields.io/github/v/release/thokaro/solarwatt-manager-homeassistant)](https://github.com/thokaro/solarwatt-manager-homeassistant/releases)
[![Platform](https://img.shields.io/badge/Platform-Home%20Assistant-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS Default Repository](https://img.shields.io/badge/HACS-Default%20Repository-41BDF5.svg)](https://hacs.xyz)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://paypal.me/thokaro)
[![Support via Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/thokaro)

# SOLARWATT Manager – Home Assistant Integration

This custom integration connects a **SOLARWATT Manager** like FLEX or Rail to **Home Assistant** and provides local Manager data, optional **KiwiGrid HEMS** data from the SOLARWATT Manager Portal, analytics, controls, live flow values, and diagnostic sensors.

Note for users with **vision** components: If you need write/control functions such as work mode, maximum charge current, discharge current, or battery SoC via Modbus, try [nathanmarlor/foxess_modbus](https://github.com/nathanmarlor/foxess_modbus). For SOLARWATT Vision battery setups, the fork [WiIIiam278:feat/ivo-and-ivt](https://github.com/WiIIiam278/foxess_modbus/tree/feat/ivo-and-ivt) may be the better fit.

⚠️ **EnergyManager pro** is not supported through the local Manager API in this integration. You can still use the optional **KiwiGrid HEMS** / SOLARWATT Manager Portal connection for supported HEMS devices, analytics, and controls. If you need direct local EnergyManager pro support, use https://github.com/Mas2112/solarwatt-energymanager-homeassistant instead.

---

## ✨ Features

* Local polling of SOLARWATT Manager data
* Fallback for newer firmware that exposes `/rest/hems-configurator/things` and `/rest/hems-configurator/energy-overview` instead of the previous `/rest/things` and `/rest/items` endpoints
* Optional KiwiGrid HEMS polling using KiwiGrid/SOLARWATT Manager Portal login credentials
* KiwiGrid HEMS devices, diagnostics, today values, month totals, year totals, finance values, and PV optimization consumption
* Separate `KiwiGrid Flow` device for live SOLARWATT Manager Portal energy-flow values
* KiwiGrid HEMS controls for supported devices:
  * `select` entity for optimization mode (`Not optimized`, `PV optimized`, `Departure time`)
  * `switch` entity for supported plug/EV station switching
* Energy Dashboard ready (correct `device_class` & `state_class`)
* Separate HEMS poll interval, defaulting to 60 seconds
* Automatic normalization of units and item names, including Wh → kWh conversion, removal of installation-specific IDs, collapsed duplicate fragments, hems-period suffixes such as `..._today`, and preserved abbreviations such as BMS/SoC/SoH
* Device-based entity structure: entities are assigned to their SOLARWATT devices and `entity_id`s are built from the Home Assistant device name plus the normalized channel name
* Human-friendly display names (Title Case; BMS/SoC/SoH preserved)
* Per-device diagnostics from `/rest/things`, with status sensors, thing properties as attributes, and refresh buttons for item and thing discovery
* Optional duplicate item handling: keep one UID-based channel entity active and create duplicates as disabled entities
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
   * **Local Host/IP**: hostname or IPv4 address, optionally with `:port`
   * **Local username** / **Local password**: your local SOLARWATT Manager credentials
   * Optional tuning values such as **Update interval**, **Energy delta**, and **Power unavailable threshold** can be set here already or adjusted later in the integration options
   * If needed, you can later disable duplicate item entities in the integration options without removing them completely from Home Assistant
   * Optional KiwiGrid HEMS credentials can be configured with **KiwiGrid (SOLARWATT Manager Portal) username or email address** and **KiwiGrid (SOLARWATT Manager Portal) password**.
   * Do not enter a full URL for the local host. The integration automatically tries HTTP and HTTPS.
5. Select the SOLARWATT devices you want to create. Energy Overview, KiwiGrid Flow, KiwiGrid HEMS, and battery devices are preselected when available.

### Options

You can adjust these in the integration options:

* **Update interval (seconds)** – polling interval
* **Energy delta (kWh)** – write energy updates only if the change is >= threshold; set to `0` to write every update
* **Power unavailable threshold (polls)** – applies to power sensors only. If SOLARWATT briefly returns `unavailable`, the last valid power value is kept until the configured consecutive poll limit is reached. Example: `3` means the 1st and 2nd `unavailable` poll keep the previous value, and the sensor only switches to `unavailable` on the 3rd poll. Set to `0` to disable this debounce completely.
* **Disable duplicate item entities** – disabled by default. When enabled and a thing channel exposes multiple linked items for the same value, the integration keeps the UID-based channel item (for example `keba_wallbox_12345678_channels_state`) active and creates the additional item entities as disabled-by-default entries. They remain visible in Home Assistant and can still be enabled manually.
* **Enable KiwiGrid HEMS (SOLARWATT Manager Portal)** – disabled by default. When enabled, the integration signs in with the configured KiwiGrid/SOLARWATT Manager Portal username or email address and password and adds supported HEMS data.
* **KiwiGrid HEMS poll interval (seconds)** – separate HEMS polling interval. The default is `60` seconds so HEMS analytics and metadata are not requested as frequently as local Manager values.
* **Device selection** – choose which detected SOLARWATT devices should be created in Home Assistant
* **Rebuild entity IDs when saving** – rebuild managed `entity_id`s using `device name + sensor name`

---

## ☁️ KiwiGrid HEMS

KiwiGrid HEMS support is optional and uses the same SOLARWATT/KiwiGrid web login flow as the SOLARWATT Manager Portal. You only need username/email address and password; copied Bearer tokens are not required.

When enabled, the integration adds supported HEMS data from the SOLARWATT Manager Portal:

* HEMS devices such as batteries, PV systems, EV chargers, plugs, meters, and inverters
* current device state, diagnostic metadata, and supported optimization settings
* today values for consumption, production, storage, independence, finance, and PV optimization consumption
* month and year energy totals for consumption and production
* live flow values under the separate `KiwiGrid Flow` device
* controls for supported EV charger and plug optimization or switching

HEMS metadata such as type, device state, optimization mode, switch state, and override requirements is exposed as diagnostic sensors. Device metadata such as manufacturer, model, firmware, and serial number is mapped to Home Assistant device information instead of separate ordinary sensors.

Physical HEMS devices are attached to their real device where possible. Synthetic analytics values are grouped under the `KiwiGrid HEMS` device. Period sensors place the period at the end of the entity ID, for example:

```
sensor.kiwigrid_hems_powerconsumed_aggregated_today
sensor.kiwigrid_hems_workconsumed_aggregated_month
sensor.kiwigrid_hems_workconsumed_aggregated_year
```

Today analytics use `POWER` values and expose aggregated and latest sensors. Month and year analytics use `WORK` values and expose aggregated energy sensors in kWh.

### KiwiGrid Flow

`KiwiGrid Flow` is a dedicated device for live energy-flow values from the SOLARWATT Manager Portal. It is independent from the local `Energy Overview` device and is also available when both local Manager access and KiwiGrid HEMS are configured.

The flow sensors keep the JSON field names recognizable instead of being converted into local Energy Overview names. Examples:

```
sensor.kiwigrid_flow_consumption_in
sensor.kiwigrid_flow_grid_in
sensor.kiwigrid_flow_grid_out
sensor.kiwigrid_flow_battery_out
sensor.kiwigrid_flow_battery_soc
sensor.kiwigrid_flow_solarwatt_battery_vision_three_out
```

The live flow is requested without date parameters so Home Assistant receives the current portal values.

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

On a tested SOLARWATT Manager with KiwOS Edge `10.26.24.4` / EM setup feature `4.64.1.45`, authenticated requests to the previous endpoints return `404`:

* `/rest/items`
* `/rest/things`

The newer firmware exposes replacement data under:

* `/rest/hems-configurator/energy-overview` - live production, grid, household, and battery power values
* `/rest/hems-configurator/things` - thing/device metadata

This integration falls back to those local HEMS configurator endpoints automatically. The direct local energy overview values are exposed under a dedicated `Energy Overview` device with sensors named like the JSON fields:

* `production`
* `feedIn`
* `feedOut`
* `householdConsumption`
* `storagePowerIn`
* `storagePowerOut`

The `Energy Overview` device must be enabled in the integration options/device selection for those sensors to be created. With SOLARWATT firmware `10.26.24.4`, these local Energy Overview items are currently the only item values that can be read because the full legacy `/rest/items` payload is no longer available.

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

If you want to use sensors from this integration in **evcc**, please refer to the instructions (in German).

* [evcc guide (German)](docs/evcc-guide-german.md)

---

## 📋 Kiwigrid Items

Here you will find an overview of the most important Kiwigrid items.

* [kiwigrid-items.md](docs/kiwigrid-items.md)

---

## 🧠 Naming Strategy

* Technical item prefixes and installation-specific IDs are stripped from channel names
* Display names stay channel-based, for example `Active Power Command`
* `entity_id`s use the Home Assistant device name plus the normalized channel name, for example `sensor.vision_battery_bms_soc`
* Duplicate fragments such as `Battery Battery ...` are collapsed
* Physical KiwiGrid HEMS entities do not repeat the device name or add an extra `hems` segment, for example `sensor.kiwigrid_mystrom_waschmaschine_requires_override`
* Synthetic HEMS periods are placed at the end, for example `sensor.kiwigrid_hems_powerconsumed_aggregated_today`
* KiwiGrid Flow entities use the flow field path, for example `sensor.kiwigrid_flow_consumption_in`; nested device values use the HEMS device name where available, for example `sensor.kiwigrid_flow_solarwatt_battery_vision_three_out`
* Existing entity IDs can be rebuilt from the integration options with **Rebuild entity IDs when saving**

This keeps entities readable while making `entity_id`s match the device names configured in Home Assistant, using the device-name-first structure planned for a future Home Assistant naming update.

---

## 🛠️ Development

### Repository Structure

```
.
├─ custom_components/
│  └─ solarwatt_manager/
│     ├─ __init__.py         # integration setup
│     ├─ button.py           # diagnostics refresh button
│     ├─ hems_client.py      # KiwiGrid HEMS login, endpoints, and payload mapping
│     ├─ config_flow.py      # UI config flow
│     ├─ const.py            # constants & defaults
│     ├─ client.py           # HTTP/session client for the manager API
│     ├─ coordinator.py      # polling orchestration + thing discovery
│     ├─ diagnostics.py      # diagnostics output
│     ├─ entity_helpers.py   # current entity/device helper utilities
│     ├─ registry_cleanup.py  # ongoing registry cleanup for current layouts
│     ├─ registry_migrations.py # upgrade paths for older entity/device layouts
│     ├─ sensor_meta.py      # Home Assistant sensor metadata heuristics
│     ├─ state_parser.py     # item state parsing + normalization
│     ├─ manifest.json       # integration metadata
│     ├─ naming.py           # name normalization/formatting
│     ├─ sensor.py           # entity definitions
│     ├─ select.py           # KiwiGrid HEMS optimization mode select entities
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
├─ CHANGELOG.md              # release history
├─ hacs.json                 # HACS metadata
├─ LICENSE
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

---

## 📄 License

This project is licensed under the **Apache License 2.0**.

---

## 🙏 Disclaimer

This project is not affiliated with or endorsed by **Solarwatt GmbH**. All trademarks belong to their respective owners.
