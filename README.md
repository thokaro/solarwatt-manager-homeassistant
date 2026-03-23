[![Version](https://img.shields.io/github/v/release/thokaro/solarwatt-manager-homeassistant)](https://github.com/thokaro/solarwatt-manager-homeassistant/releases)
[![HACS Category](https://img.shields.io/badge/HACS-Integration-41BDF5.svg)](https://hacs.xyz/docs/categories/integration/)
[![Platform](https://img.shields.io/badge/Platform-Home%20Assistant-41BDF5.svg)](https://www.home-assistant.io/)
[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://paypal.me/thokaro)
[![Support via Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/thokaro)

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

### Option 1: One‑click repository add via My Home Assistant (HACS)

1. Make sure **HACS** is installed in your Home Assistant instance
2. Click the button below and follow the prompts (this **adds the repository to HACS**; installation is still done in HACS):

[![Open your Home Assistant instance and add this repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thokaro&repository=solarwatt-manager-homeassistant&category=integration)

3. In **HACS → Integrations**, search for **SOLARWATT Manager** and install it
4. Restart Home Assistant

---

### Option 2: Installation via HACS (manual)

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

### Option 3: Manual Installation

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
5. Select the SOLARWATT devices you want to create

### Options

You can adjust these in the integration options:

* **Update interval (seconds)** – polling interval
* **Name prefix (optional)** – prefix for entity names
* **Energy delta (kWh)** – write energy updates only if the change is >= threshold; set to `0` to write every update
* **Device selection** – choose which detected SOLARWATT devices should be created in Home Assistant

---

## 🔋 Energy Dashboard

Energy sensors are provided in kWh and prepared for the Energy Dashboard (`device_class: energy`, `state_class: total_increasing`). Which sensors you use depends on your setup.

---

## 🚗 evcc Sensors

If you want to use sensors from this integration in **evcc**, please refer to the instructions (in german).

* [evvc-guide-german.md](docs/evvc-guide-german.md)

---

## 📋 Kiwigrid Items

Here you will find an overview of the most important Kiwigrid items.

* [kiwigrid-items.md](docs/kiwigrid-items.md)

---

## 🧠 Naming Strategy

* Internal sensor keys remain unchanged for stability
* Display names:

  * remove technical prefixes (e.g. `harmonized`)
  * replace underscores (`_`) with spaces
  * Title Case formatting with exceptions for common acronyms/brands (e.g. `BMS`, `SoC`, `SoH`, `AC`, `DC`, `PV`, `MPPT`, `SMA`, `KEBA`, `SunSpec`, `Modbus`, `FoxESS`)


This keeps entities readable without breaking existing statistics.

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
│     ├─ coordinator.py      # polling + data parsing
│     ├─ diagnostics.py      # diagnostics output
│     ├─ entity_helpers.py   # current entity/device helper utilities
│     ├─ legacy_migrations.py # upgrade cleanup for older entity/device layouts
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
│  ├─ evvc-guide-german.md   # EVVC setup guide
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
