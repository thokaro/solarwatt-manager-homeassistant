# SOLARWATT-Manager Integration von Home Assistant fuer evcc

Diese Anleitung beschreibt, wie Sensoren der Custom-Integration **SOLARWATT Manager** in **evcc** verwendet werden koennen.

Aktuelle Versionen der Integration stellen die fuer evcc wichtigen Leistungswerte bereits als eigene Sensoren bereit. Die frueher noetigen Template-Helfer fuer saldierte Netzleistung und Batterieleistung sind daher normalerweise nicht mehr notwendig.

## 1. Geeignete Sensoren in Home Assistant finden

Oeffne in Home Assistant das jeweilige SOLARWATT Geraet und suche nach diesen Sensoren:

| evcc Verwendung | Empfohlener Sensor |
|---|---|
| Grid Power | `Grid Power` |
| PV Power | `Production` oder `Power Produced Latest` |
| Battery Power | `Battery Power` |
| Battery SoC | `Battery SoC`, `State Of Charge` oder der SoC-Sensor deiner Batterie |
| Grid Energy | Netzbezug/Energieverbrauch aus dem Netz |
| PV Energy | PV-Erzeugung/Energieproduktion |
| Battery Energy | Batterieentladung oder Speicherverbrauch, falls gewuenscht |

Je nach Konfiguration koennen die Entity-IDs unterschiedlich aussehen. Beispiele:

```text
sensor.energy_overview_grid_power
sensor.energy_overview_battery_power
sensor.energy_overview_production
sensor.energy_overview_battery_soc
sensor.kiwigrid_hems_powerproduced_latest_today
sensor.kiwigrid_hems_workproduced_aggregated_year
```

Wichtig fuer evcc:

- Grid Power: positiver Wert = Netzbezug, negativer Wert = Einspeisung
- Battery Power: positiver Wert = Batterie entlaedt, negativer Wert = Batterie laedt
- PV Power: aktueller PV-Erzeugungswert in W
- Energiezaehler sollten kWh liefern und fuer Langzeitstatistiken geeignet sein

## 2. Beispiel fuer evcc

Passe die Entity-IDs an deine Home-Assistant-Installation an.

```yaml
meters:
  - name: grid
    type: template
    template: homeassistant
    usage: grid
    uri: http://homeassistant.local:8123/
    power: sensor.energy_overview_grid_power
    energy: sensor.kiwigrid_hems_workin_aggregated_year

  - name: pv
    type: template
    template: homeassistant
    usage: pv
    uri: http://homeassistant.local:8123/
    power: sensor.energy_overview_production
    energy: sensor.kiwigrid_hems_workproduced_aggregated_year

  - name: battery
    type: template
    template: homeassistant
    usage: battery
    uri: http://homeassistant.local:8123/
    power: sensor.energy_overview_battery_power
    soc: sensor.energy_overview_battery_soc
```

Wenn du lokale Manager-Sensoren statt HEMS-Sensoren nutzt, ersetze die `energy`-Eintraege durch die passenden lokalen Energiezaehler.

## 3. Optional: Template-Helfer fuer aeltere Sensoren

Nur wenn deine Installation noch keine direkten `Grid Power`- oder `Battery Power`-Sensoren hat, kannst du weiterhin Template-Sensoren verwenden.

### Grid Power

```jinja2
{{ states('sensor.DEIN_NETZBEZUG_SENSOR')|float(0)
   - states('sensor.DEINE_EINSPEISUNG_SENSOR')|float(0) }}
```

### Battery Power

```jinja2
{{ states('sensor.DEINE_BATTERIE_ENTLADUNG')|float(0)
   - states('sensor.DEINE_BATTERIE_LADUNG')|float(0) }}
```

Lege diese Helfer in Home Assistant unter `Einstellungen -> Geraete & Dienste -> Helfer -> Template -> Sensor` an, setze die Einheit auf `W` und die Geraeteklasse auf `Leistung`.

## 4. evcc neu starten und Home Assistant autorisieren

Nach dem Anpassen der evcc-Konfiguration muss evcc neu gestartet werden.

Empfohlener Weg:

1. Oeffne die evcc Weboberflaeche.
2. Wechsle zu **Konfiguration**.
3. Scrolle nach unten und klicke auf **Neustarten**.

Nach dem Neustart erscheint im Bereich **Integration** ein Hinweis zum Home-Assistant-Autorisierungsstatus. Dort muss einmalig eine Autorisierung auf der Home-Assistant-Instanz durchgefuehrt werden, damit evcc auf die Sensoren zugreifen darf.
