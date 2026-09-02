# SOLARWATT-Manager Integration von Home Assistant fuer evcc

Diese Anleitung beschreibt, wie Sensoren der Custom-Integration **SOLARWATT Manager** in **evcc** verwendet werden koennen.

Aktuelle Versionen der Integration stellen die fuer evcc wichtigen Leistungswerte bereits als eigene Sensoren bereit. Die frueher noetigen Template-Helfer fuer saldierte Netzleistung und Batterieleistung sind daher normalerweise nicht mehr notwendig.

Es gibt zwei getrennte Quellen:

- **SOLARWATT Flow** liest die Live-Werte direkt vom lokalen SOLARWATT Manager. Dafuer ist keine Portal- oder Internetverbindung erforderlich.
- **KiwiGrid Flow** liest die Live-Werte ueber KiwiGrid Online beziehungsweise das SOLARWATT Manager Portal.

Fuer evcc kann eine der beiden Quellen verwendet werden. Wenn beide konfiguriert sind, sollte fuer Grid, PV und Batterie moeglichst dieselbe Quelle gewaehlt werden, damit die Leistungswerte zeitlich zusammenpassen.

## 1. Geeignete Sensoren in Home Assistant finden

Oeffne in Home Assistant das jeweilige SOLARWATT Geraet und suche nach diesen Sensoren:

| evcc Verwendung | SOLARWATT Flow (lokal) | KiwiGrid Flow (online) |
|---|---|---|
| Grid Power | `Grid Balance` | `Grid Balance` |
| PV Power | `PV Out` | `PV Out` |
| Battery Power | `Battery Balance` | `Battery Balance EVCC` |
| Battery SoC | `Battery SoC` | `Battery SoC` |

Die Flow-Geraete liefern aktuelle Leistung in W und den Batterie-SoC. Kumulative Energiezaehler in kWh stammen nicht aus SOLARWATT Flow. Die optionalen evcc-Felder `energy` und `returnEnergy` duerfen nur mit passenden kumulativen Energie-Sensoren belegt werden, nicht mit Tages-, Monats- oder Jahreswerten.

Home Assistant verwaltet die Entity-IDs. Bei einer neuen Installation mit Geraetepraefix koennen sie beispielsweise so aussehen:

```text
sensor.solarwatt_flow_grid_balance
sensor.solarwatt_flow_pv_out
sensor.solarwatt_flow_battery_balance
sensor.solarwatt_flow_battery_soc
sensor.kiwigrid_flow_grid_balance
sensor.kiwigrid_flow_pv_out
sensor.kiwigrid_flow_battery_balance_evcc
sensor.kiwigrid_flow_battery_soc
```

Bestehende Installationen behalten ihre bisherigen Entity-IDs, auch wenn das lokale Geraet jetzt `SOLARWATT Flow` heisst. Kopiere deshalb die tatsaechliche Entity-ID aus Home Assistant unter **Entwicklerwerkzeuge -> Zustaende** oder direkt aus dem jeweiligen Sensor.

Wichtig fuer evcc:

- Grid Power: positiver Wert = Netzbezug, negativer Wert = Einspeisung
- Battery Power: positiver Wert = Batterie entlaedt, negativer Wert = Batterie laedt
- PV Power: aktueller PV-Erzeugungswert in W
- Energiezaehler sollten kWh liefern und fuer Langzeitstatistiken geeignet sein

## 2. Lokales SOLARWATT Flow in evcc verwenden

Passe die Entity-IDs an deine Home-Assistant-Installation an.

```yaml
meters:
  - name: grid
    type: template
    template: homeassistant
    usage: grid
    uri: http://homeassistant.local:8123/
    power: sensor.solarwatt_flow_grid_balance

  - name: pv
    type: template
    template: homeassistant
    usage: pv
    uri: http://homeassistant.local:8123/
    power: sensor.solarwatt_flow_pv_out

  - name: battery
    type: template
    template: homeassistant
    usage: battery
    uri: http://homeassistant.local:8123/
    power: sensor.solarwatt_flow_battery_balance
    soc: sensor.solarwatt_flow_battery_soc
```

`SOLARWATT Flow Battery Balance` besitzt bereits das von evcc erwartete Vorzeichen. Ein zusaetzlicher Template-Sensor oder eine Invertierung ist nicht erforderlich.

### Alternative: KiwiGrid Flow

Wenn nur KiwiGrid Online verwendet wird, ersetze die lokalen Entity-IDs aus dem Beispiel wie folgt:

| Eintrag | KiwiGrid-Entity-ID im Beispiel |
|---|---|
| Grid `power` | `sensor.kiwigrid_flow_grid_balance` |
| PV `power` | `sensor.kiwigrid_flow_pv_out` |
| Batterie `power` | `sensor.kiwigrid_flow_battery_balance_evcc` |
| Batterie `soc` | `sensor.kiwigrid_flow_battery_soc` |

Fuer die Batterie muss `Battery Balance EVCC` verwendet werden: Der normale KiwiGrid-Sensor `Battery Balance` hat das entgegengesetzte Vorzeichen.

## 3. Optional: Template-Helfer fuer aeltere Sensoren

Nur wenn deine Installation noch keine direkten `Grid Balance`- oder `Battery Balance`-Sensoren hat, kannst du weiterhin Template-Sensoren verwenden.

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
