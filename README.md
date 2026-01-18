[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Version](https://img.shields.io/github/v/release/thokaro/solarwatt-manager-homeassistant)](https://github.com/thokaro/solarwatt-manager-homeassistant/releases)


# SOLARWATT Manager – Home Assistant Integration

This custom integration connects a **SOLARWATT Manager** like FLEX or Rail to **Home Assistant** and provides energy- and power-related sensors.

Note: If you want to control settings like workmode, maximum charge current or discharge current try https://github.com/nathanmarlor/foxess_modbus

---

## ✨ Features

* Local polling of Solarwatt Manager data
* Energy Dashboard ready (correct `device_class` & `state_class`)
* Automatic unit normalization (Wh → kWh)
* Entity names are normalized and installation-specific IDs are removed.
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

---

## 🔋 Energy Dashboard

The following sensor types are prepared for use in the Energy Dashboard:

* **PV Production (kWh)**
* **Grid Consumption (kWh)**
* **Grid Feed-in (kWh)**
* **Battery Charging / Discharging (kWh)**
* **Household Consumption (kWh)**

All energy sensors:

* use `device_class: energy`
* use `state_class: total_increasing`
* report values in `kWh`

This guarantees compatibility with Home Assistant long‑term statistics.

---

## 🧠 Naming Strategy

* Internal sensor keys remain unchanged for stability
* Display names:

  * remove technical prefixes (e.g. `harmonized`)
  * replace underscores (`_`) with spaces

This keeps entities readable without breaking existing statistics.

---

## 🛠️ Development

### Repository Structure

```
custom_components/
└─ solarwatt_manager/
   ├─ __init__.py
   ├─ manifest.json
   ├─ sensor.py
   ├─ coordinator.py
   ├─ config_flow.py
   └─ translations/
```

### Versioning

The integration version is defined in:

```
custom_components/solarwatt_manager/manifest.json
```

GitHub releases should follow semantic versioning:

```
vX.Y.Z
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