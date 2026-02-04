[![Version](https://img.shields.io/github/v/release/thokaro/solarwatt-manager-homeassistant)](https://github.com/thokaro/solarwatt-manager-homeassistant/releases)
[![HACS Category](https://img.shields.io/badge/HACS-Integration-41BDF5.svg)](https://hacs.xyz/docs/categories/integration/)
[![Platform](https://img.shields.io/badge/Platform-Home%20Assistant-41BDF5.svg)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/thokaro/solarwatt-manager-homeassistant)](LICENSE)


# SOLARWATT Manager – Home Assistant Integration

This custom integration connects a **SOLARWATT Manager** like FLEX or Rail to **Home Assistant** and provides energy- and power-related sensors.

Note for user with **vision** components: If you want to control settings like workmode, maximum charge current or discharge current try https://github.com/nathanmarlor/foxess_modbus

⚠️ **EnergyManager pro** is not supported by this integration, use https://github.com/Mas2112/solarwatt-energymanager-homeassistant instead.

---

## ✨ Features

* Local polling of Solarwatt Manager data
* Energy Dashboard ready (correct `device_class` & `state_class`)
* Automatic unit normalization (Wh → kWh)
* Entity names are normalized and installation-specific IDs are removed.
* Human‑friendly display names (Title Case; BMS/SoC/SoH preserved)
* Diagnostics data from /rest/things with devices and their "properties" exposed as diagnostic entities
* Stable `unique_id`s (safe for long‑term statistics)
* Works with Home Assistant statistics & history

---

## 📦 Installation

### Option 1: Installation via HACS (recommended)

1. Make sure **HACS** is installed in your Home Assistant instance
2. Go to **HACS → Integrations**
3. Open the menu (⋮) in the top right corner and select **Custom repositories**
4. Add this repository URL:

```
https://github.com/thokaro/solarwatt-manager-homeassistant
```

5. Select **Integration** as the category
6. Click **Add**
7. Search for **SOLARWATT Manager** in HACS and install it
8. Restart Home Assistant

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
4. Enter the required connection details

### Options

You can adjust these in the integration options:

* **Update interval (seconds)** – polling interval
* **Name prefix (optional)** – prefix for entity names
* **Enable all sensors by default** – if off, only the core sensors (PV, grid, battery, consumption) are enabled by default; if on, all sensors are enabled regardless of the core list

---

## 🔋 Energy Dashboard

Energy sensors are provided in kWh and prepared for the Energy Dashboard (`device_class: energy`, `state_class: total_increasing`). Which sensors you use depends on your setup.

---

## 🚗 evcc Sensors

If you want to use sensors from this integration in **evcc**, please refer to the instructions (in german).

* [LIESMICH-evvc-guide.md](LIESMICH-evvc-guide.md)

---

## 🧠 Naming Strategy

* Internal sensor keys remain unchanged for stability
* Display names:

  * remove technical prefixes (e.g. `harmonized`)
  * replace underscores (`_`) with spaces
  * Title Case formatting with exceptions for `BMS`, `SoC`, and `SoH`


This keeps entities readable without breaking existing statistics.

---

## 🛠️ Development

### Repository Structure

```
custom_components/
└─ solarwatt_manager/
   ├─ __init__.py        # integration setup
   ├─ button.py          # diagnostics refresh button
   ├─ const.py           # constants & defaults
   ├─ manifest.json      # integration metadata
   ├─ sensor.py          # entity definitions
   ├─ coordinator.py     # polling + data parsing
   ├─ config_flow.py     # UI config flow
   ├─ diagnostics.py     # diagnostics output
   ├─ naming.py          # name normalization/formatting
   ├─ strings.json       # UI strings
   ├─ icon.png
   └─ translations/
      └─ de.json          # German translations
```

### Versioning

The integration version is defined in:

```
custom_components/solarwatt_manager/manifest.json
```

See `CHANGELOG.md` for release notes. GitHub releases follow calendar-based versioning:

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
