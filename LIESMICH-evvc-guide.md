# 🔌 SOLARWATT-Manager Integration von Home Assistant für evcc

Diese Anleitung beschreibt, wie die Custom-Integration **SOLARWATT Manager** in **Home Assistant** genutzt wird, um Messwerte für **evcc** bereitzustellen ⚡️.

Da der SOLARWATT Manager einige Leistungswerte nicht direkt im von evcc erwarteten Format liefert, müssen **zwei zusätzliche Template-Sensoren (Helfer)** angelegt werden.

---

## 1. Benötigte Helfer (Template-Sensoren) 🧩

### Warum sind diese Helfer notwendig?

- **Netzleistung (Grid)**  
  Der SOLARWATT Manager stellt Netzbezug und Netzeinspeisung als **zwei getrennte Sensoren** bereit.  
  evcc erwartet jedoch von dem *power* Sensor **einen saldierten Leistungswert**:
  - positiver Wert = Netzbezug  
  - negativer Wert = Einspeisung  

- **Batterieleistung (Battery)**  
  Die vom Batteriemanagementsystem gelieferte Leistung hat ein **invertiertes Vorzeichen** und muss für evcc korrigiert werden 🔋.

---

## 1.1 Helfer: Grid Power für evcc

**Pfad in Home Assistant:**  
`Einstellungen → Geräte & Dienste → Helfer → Template → Sensor`

### Zustand (Template)

```jinja2
{{ states('sensor.vision_kiwigrid_power_in') | int
   - states('sensor.vision_kiwigrid_power_out') | int }}
```

Die Entitäts-IDs können bei euch natürlich abweichen.

### Einstellungen

| Feld | Wert |
|------|------|
| Name | Kiwigrid Power Grid EVCC |
| Entitäts-ID | `sensor.kiwigrid_power_grid_evcc` |
| Maßeinheit | `W` |
| Geräteklasse | Leistung |
| Zustandsklasse | – |
| Gerät | Vision (hier idealerweise das SOLARWATT Manager Gerät wählen) |

**Ergebnis:**

- positiver Wert → Netzbezug  
- negativer Wert → Einspeisung  

---

## 1.2 Helfer: Battery Power für evcc

**Pfad in Home Assistant:**  
`Einstellungen → Geräte & Dienste → Helfer → Template → Sensor`

### Zustand (Template)

```jinja2
{{ -1 * states('sensor.vision_foxess_battery_bms_power') | int }}
```

### Einstellungen

| Feld | Wert |
|------|------|
| Name | FoxEss Battery BMS Power EVCC |
| Entitäts-ID | `sensor.foxess_battery_bms_power_evcc` |
| Maßeinheit | `W` |
| Geräteklasse | Leistung |
| Zustandsklasse | – |
| Gerät | Vision (hier idealerweise das SOLARWATT Manager Gerät wählen) |

**Ergebnis:**

- positiver Wert → Batterie entlädt  
- negativer Wert → Batterie lädt  

---

## 2. evcc: Messpunkte aus Home Assistant ⚙️

Nachdem die beiden Helfer angelegt wurden, können diese in evcc als Messpunkte für **Grid** und **Battery** verwendet werden. Für **PV** benötigen wir keinen zusätzlichen Helfer.

### Beispiel: `meters`-Konfiguration

```yaml
meters:
  - name: grid
    type: template
    template: homeassistant
    usage: grid
    uri: http://homeassistant.local:8123/
    power: sensor.kiwigrid_power_grid_evcc
    energy: sensor.vision_kiwigrid_work_consumed_from_grid_total

  - name: pv
    type: template
    template: homeassistant
    usage: pv
    uri: http://homeassistant.local:8123/
    power: sensor.vision_kiwigrid_power_produced
    energy: sensor.vision_kiwigrid_work_produced_total

  - name: battery
    type: template
    template: homeassistant
    usage: battery
    uri: http://homeassistant.local:8123/
    power: sensor.foxess_battery_bms_power_evcc
    energy: sensor.vision_kiwigrid_work_consumed_from_storage_total
    soc: sensor.vision_foxess_battery_bms_soc
```

---

## 3. evcc neu starten & Home Assistant autorisieren 🔄

Nach dem Anpassen der Konfiguration muss **evcc neu gestartet** werden, damit die Änderungen wirksam werden.

**Empfohlener Weg:**

1. Öffne die **evcc Weboberfläche**
2. Wechsle zu **Konfiguration**
3. Scrolle ganz nach unten und klicke auf **Neustarten**

Nach dem Neustart erscheint im Bereich **Integration** ein Hinweis zum **Home-Assistant Autorisierungsstatus**.

➡️ Dort muss einmalig eine **Autorisierung auf der Home-Assistant-Instanz** durchgeführt werden, damit evcc auf die Sensoren zugreifen darf.

---
