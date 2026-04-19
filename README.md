[![Version](https://img.shields.io/github/v/release/thokaro/solarwatt-manager-homeassistant)](https://github.com/thokaro/solarwatt-manager-homeassistant/releases)
[![Platform](https://img.shields.io/badge/Platform-Home%20Assistant-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS Default Repository](https://img.shields.io/badge/HACS-Default%20Repository-41BDF5.svg)](https://hacs.xyz)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://paypal.me/thokaro)
[![Support via Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/thokaro)

# SOLARWATT Manager – Home Assistant Integration

This custom integration connects a **SOLARWATT Manager** like FLEX or Rail to **Home Assistant** and provides energy- and power-related sensors.

Note for users with **vision** components: If you need write/control functions such as work mode, maximum charge current, or discharge current, try https://github.com/nathanmarlor/foxess_modbus

⚠️ **EnergyManager pro** is not supported by this integration, use https://github.com/Mas2112/solarwatt-energymanager-homeassistant instead.

---

## ✨ Features

* Local polling of SOLARWATT Manager data
* Energy Dashboard ready (correct `device_class` & `state_class`)
* Automatic unit normalization (Wh → kWh)
* Item names are normalized and installation-specific IDs are removed.
* Item `entity_id`s are derived from the Home Assistant device name and the normalized channel name, following the device-based naming structure planned for future Home Assistant releases
* Entities are assigned to their corresponding SOLARWATT devices
* Human‑friendly display names (Title Case; BMS/SoC/SoH preserved)
* Per-device diagnostics based on `/rest/things`, including status sensors with thing properties as attributes and refresh buttons to update item and thing discovery on demand
* Optional duplicate item handling: keep one UID-based channel entity active and create the duplicates as disabled entities
* Stable `unique_id`s (safe for long‑term statistics)
* Works with Home Assistant statistics & history

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
4. Enter the required connection details:
   * **Host**: hostname or IPv4 address, optionally with `:port`
   * **Username** / **Password**: your SOLARWATT login credentials
   * Optional tuning values such as **Update interval**, **Energy delta**, and **Power unavailable threshold** can be set here already or adjusted later in the integration options
   * If needed, you can later disable duplicate item entities in the integration options without removing them completely from Home Assistant
   * Do not enter a full URL. The integration automatically tries HTTP and HTTPS.
5. Select the SOLARWATT devices you want to create (KiwiGrid and battery devices are preselected by default)

### Options

You can adjust these in the integration options:

* **Update interval (seconds)** – polling interval
* **Energy delta (kWh)** – write energy updates only if the change is >= threshold; set to `0` to write every update
* **Power unavailable threshold (polls)** – applies to power sensors only. If SOLARWATT briefly returns `unavailable`, the last valid power value is kept until the configured consecutive poll limit is reached. Example: `3` means the 1st and 2nd `unavailable` poll keep the previous value, and the sensor only switches to `unavailable` on the 3rd poll. Set to `0` to disable this debounce completely.
* **Disable duplicate item entities** – disabled by default. When enabled and a thing channel exposes multiple linked items for the same value, the integration keeps the UID-based channel item (for example `keba_wallbox_12345678_channels_state`) active and creates the additional item entities as disabled-by-default entries. They remain visible in Home Assistant and can still be enabled manually.
* **Device selection** – choose which detected SOLARWATT devices should be created in Home Assistant
* **Rebuild entity IDs when saving** – rebuild managed `entity_id`s using `device name + sensor name`

---

## 🔋 Energy Dashboard

Energy sensors are provided in kWh and prepared for the Energy Dashboard (`device_class: energy`, `state_class: total` or `total_increasing`, depending on whether the value is cumulative or strictly increasing). Which sensors you use depends on your setup.

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

This project is licensed under the **MIT License**.

---

## 🙏 Disclaimer

This project is not affiliated with or endorsed by **Solarwatt GmbH**. All trademarks belong to their respective owners.
