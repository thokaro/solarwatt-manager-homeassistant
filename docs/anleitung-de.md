# SOLARWATT Manager für Home Assistant

[English README](../README.md) | **Deutsche Anleitung**

Die Integration verbindet einen SOLARWATT Manager Flex oder Rail mit Home Assistant. Du kannst lokale Live-Daten, Daten aus dem SOLARWATT Manager Portal oder beide Quellen gemeinsam verwenden. Diese Anleitung beschreibt Installation, Einrichtung und Nutzung für die Version 2026.10.0.

## Voraussetzungen und Datenquellen

Als Mindestversion ist Home Assistant **2024.12.0** hinterlegt.

| Datenquelle | Zugang | Verfügbare Daten | Internet nötig |
| --- | --- | --- | --- |
| Lokaler SOLARWATT Manager | Host/IP und lokale Zugangsdaten | SOLARWATT Flow, lokale Gerätemetadaten und Diagnose | Nein |
| KiwiGrid Online | Benutzername/E-Mail und Passwort des SOLARWATT Manager Portals | KiwiGrid Flow, KiwiGrid Stats, unterstützte Portalgeräte und Steuerung | Ja |

Für den lokalen Betrieb muss die Firmware die Endpunkte `/rest/hems-configurator/energy-overview` und `/rest/hems-configurator/things` bereitstellen. EnergyManager pro wird über diese lokale Anbindung nicht unterstützt; die Portal-Anbindung kann für dort unterstützte Geräte dennoch genutzt werden.

Bei kombinierter Einrichtung arbeiten die Quellen unabhängig voneinander. Lokale Live-Werte können bei einem Portalausfall weiter aktualisiert werden. Welche Sensoren und Steuerungen verfügbar sind, hängt von den Daten ab, die dein Manager bzw. das Portal liefert.

## Installation

### Über HACS

1. Öffne HACS in Home Assistant.
2. Suche nach **SOLARWATT Manager**, gegebenenfalls mit dem Filter **Integration**.
3. Lade die Integration herunter. Das Repository ist in der HACS-Standardliste enthalten.
4. Starte Home Assistant neu.

### Manuell

1. Lade das Repository herunter.
2. Kopiere den Ordner `custom_components/solarwatt_manager` in das Konfigurationsverzeichnis von Home Assistant. Das Ergebnis muss `config/custom_components/solarwatt_manager/manifest.json` enthalten.
3. Starte Home Assistant neu.

## Verbindung einrichten

Öffne **Einstellungen → Geräte & Dienste → Integration hinzufügen** und suche nach **SOLARWATT Manager**. Mindestens eine Datenquelle muss vollständig eingerichtet sein.

### Lokaler SOLARWATT Manager

- **Host/IP:** Standard ist `energymanager.local`. Alternativ kannst du eine IPv4-Adresse oder einen Hostnamen angeben, bei Bedarf mit `:port`. Trage keine vollständige URL mit `http://` oder `https://` ein; die Integration probiert beide Protokolle automatisch.
- **Benutzername:** Vorbelegt ist `installer`. Diesen kannst du in der Regel unverändert lassen, auch wenn die lokale Weboberfläche nur ein Passwort abfragt.
- **Passwort:** Verwende das Passwort der lokalen Weboberfläche des Managers. Dies ist nicht das Passwort deines Portal-Kontos.

Home Assistant muss den Manager im lokalen Netzwerk erreichen können. Wenn `energymanager.local` nicht aufgelöst wird, verwende die IP-Adresse des Managers.

### KiwiGrid Online

Trage im Abschnitt **KiwiGrid Online (SOLARWATT Manager portal)** den Benutzernamen bzw. die E-Mail-Adresse und das Passwort deines Portal-Kontos ein. Beide Felder zusammen aktivieren die Online-Anbindung automatisch.

Für eine reine Portal-Installation kannst du die vorbelegten lokalen Werte `energymanager.local` und `installer` unverändert lassen und das lokale Passwort leer lassen. Diese ungenutzten Standardwerte werden dann ignoriert.

### Geräte auswählen

Wähle nach der Verbindungsprüfung die gewünschten Geräte aus. Lokaler Flow, KiwiGrid Flow, erkannte KiwiGrid-HEMS-Geräte einschließlich KiwiGrid Stats, Standortgeräte und Speicher sind standardmäßig ausgewählt, sofern vorhanden.

Die Auswahl kannst du später in den Optionen ändern. Für lokale Live-Sensoren und den kiwiOS-Versionssensor muss **SOLARWATT Flow** aktiviert sein. Für Portal-Batteriewerte muss das entsprechende Batteriegerät aktiviert sein.

## Optionen und Aktualisierung

Öffne die Optionen der Integration unter **Einstellungen → Geräte & Dienste → SOLARWATT Manager**. Verbindungseinstellungen können außerdem über **Neu konfigurieren** geändert werden. Neue Zugangsdaten werden vor dem Speichern geprüft.

| Einstellung | Standard bei neuer Einrichtung | Wirkung |
| --- | --- | --- |
| Lokales Update-Intervall | 15 Sekunden | Lokale Werte und SOLARWATT Flow |
| HEMS-Geräteintervall | 30 Sekunden | Physische Portalgeräte, etwa Batterie, Wallbox oder Schaltsteckdose |
| KiwiGrid-Flow-Intervall | Übernimmt zunächst das lokale Update-Intervall | Live-Energieflüsse aus dem Portal |
| KiwiGrid-Stats-Intervall | Übernimmt zunächst das HEMS-Geräteintervall | Tageswerte und regelmäßig aktualisierte Statistikwerte |
| Cache-Dauer des Benutzerprofils | 3600 Sekunden | Wiederverwendung des Portalprofils, einschließlich Währung |
| Schwellwert Energy-Änderung | 0,01 kWh | Energieänderungen erst ab dieser Differenz schreiben; `0` schreibt jedes Update |
| Power-unavailable-Schwellwert | 3 Abfragen | Kurzzeitig fehlende Leistungswerte überbrücken; `0` deaktiviert dies |

Alle Zeitintervalle einschließlich Profil-Cache erlauben **10 bis 3600 Sekunden**. Bestehende Installationen behalten ihre bisherigen Flow- und Stats-Intervalle, bis du sie änderst. Ein Stats-Intervall von beispielsweise `300` Sekunden verringert die Zahl der Statistikabfragen.

Beim Power-unavailable-Schwellwert `3` bleibt bei den ersten beiden aufeinanderfolgenden `unavailable`-Werten der letzte gültige Leistungswert stehen. Erst beim dritten wechselt der Sensor auf `unavailable`.

Monats- und Jahres-Energiesummen kombinieren zwischengespeicherte abgeschlossene Tage mit dem heutigen Wert. Korrekturen abgeschlossener Tage erscheinen beim nächsten täglichen Abruf. Monats- und Jahresquoten für Autarkie und Eigenverbrauch werden einmal täglich aktualisiert; heutige Quoten folgen dem Stats-Intervall. Neuladen der Integration leert diese täglichen Caches und den Profil-Cache.

## Sensoren zuordnen

### Lokaler und Online-Energiefluss

**SOLARWATT Flow** enthält lokale Live-Werte. **KiwiGrid Flow** enthält die Live-Werte des Portals. Beide Geräte bleiben getrennt sichtbar.

| Sensorname | Bedeutung |
| --- | --- |
| PV Out | Aktuelle PV-Leistung |
| Consumption In | Aktuelle Verbrauchsleistung |
| Grid In / Grid Out | Netzbezug / Einspeisung |
| Battery In / Battery Out | Batterieladung / Entladung |
| Battery SoC | Ladezustand in Prozent, sofern geliefert |
| Grid Balance | Positiv bei Netzbezug, negativ bei Einspeisung |

Beim **lokalen** `Battery Balance` bedeutet ein positiver Wert Entladung und ein negativer Wert Ladung. Im **Online-Flow** hat `Battery Balance` das umgekehrte Vorzeichen. Dort liefert `Battery Balance EVCC` den invertierten Wert für evcc.

Die Einzelwerte für Bezug, Einspeisung, Ladung und Entladung sind nicht vorzeichenbehaftet. Lokale berechnete Sensoren teilen den Verbrauch außerdem in `Consumption From PV`, `Consumption From Grid` und `Consumption From Battery` auf.

Übernimm die tatsächlichen Entity-IDs aus **Entwicklerwerkzeuge → Zustände**. Home Assistant verwaltet die IDs; Beispiele müssen nicht mit deiner Installation übereinstimmen. Bestehende benutzerdefinierte IDs werden von der Integration nicht umbenannt.

### Portalgeräte und Steuerung

Je nach API-Daten erscheinen Batterien, Wechselrichter, PV-Anlagen, Zähler, Wallboxen, Schaltsteckdosen und Heizgeräte mit ihren Sensoren. Unterstützte Geräte erhalten zusätzlich einen Schalter oder eine Auswahl für den Optimierungsmodus: **Nicht optimiert**, **PV-optimiert** oder **Abfahrtszeit**.

### Batterie und Notstrom

Wenn das Portal die Felder liefert, erscheinen auf dem Batteriegerät unter anderem:

| Sensorname | Bedeutung |
| --- | --- |
| Backup Active | Notstrom aktuell aktiv: Text `"true"` oder `"false"` |
| Backup Available | Notstromfähigkeit verfügbar, nicht zwingend aktiv |
| Backup State Of Charge | Notstromreserve in Prozent |
| State Of Charge | Aktueller Ladezustand in Prozent |
| Mode | Vom Portal gemeldeter Betriebsmodus |

Die Backup-Flags sind normale Textsensoren, keine Binärsensoren. Sie folgen dem HEMS-Geräteintervall. Bei einem Verbindungsfehler können zwischengespeicherte Werte stehen bleiben und bestätigen dann keinen aktuellen Notstromzustand.

Beispiel für den YAML-Editor einer Automation; ersetze die Entity-ID durch deinen Sensor:

```yaml
alias: Batterie meldet Notstrom
triggers:
  - trigger: state
    entity_id: sensor.your_battery_backup_active
    from: "false"
    to: "true"
actions:
  - action: persistent_notification.create
    data:
      title: Notstrom aktiv
      message: Die Batterie meldet aktiven Notstrombetrieb.
mode: single
```

Durch `from: "false"` wird beim erstmaligen Verfügbarwerden mit Zustand `"true"` keine Meldung ausgelöst.

## Statistiken und Energie-Dashboard

**KiwiGrid Stats** bündelt Tages-, Monats- und Jahresstatistiken. Für geeignete Jahres-Energiesensoren erzeugt die Integration zusätzliche **Total**-Sensoren mit `state_class: total_increasing`. Sie übernehmen den Vorjahresstand beim Jahreswechsel und speichern diesen über Neustarts hinweg.

Korrigiert das Portal einen Jahreswert nach unten, hält der Total-Sensor den bisherigen Höchstwert, bis die Berechnung diesen wieder erreicht. Explizite Kalibrierungen können den angezeigten Wert dennoch senken.

Verwende für das Energie-Dashboard passende kumulative Energiesensoren in kWh. Die Leistungswerte in W aus den Flow-Geräten sind keine Energiezähler. Welche Total-Sensoren zu Netzbezug, Einspeisung oder Batterie passen, hängt von den verfügbaren Daten deiner Anlage ab.

### Frühere Jahre berücksichtigen

Die Aktion `calculate_all_stats_values` liest abgeschlossene Vorjahre und speichert deren Summe als Offset für alle registrierten Statistik-Total-Sensoren. Das aktuelle Jahr stammt bereits vom laufenden Jahressensor. Die Berechnung läuft im Hintergrund; einzelne historische Anfragen können bis zu fünf Minuten dauern.

```yaml
action: solarwatt_manager.calculate_all_stats_values
data:
  max_years: 20
```

Für einen ausgewählten Sensor:

```yaml
action: solarwatt_manager.calculate_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
data:
  max_years: 3
```

Im Jahr 2026 liest `max_years: 3` höchstens 2025, 2024 und 2023. Die Suche endet früher, wenn kein Wert zurückgegeben wird.

### Total-Wert kalibrieren

Mit `value` gibst du den gewünschten angezeigten Total-Wert in kWh vor:

```yaml
action: solarwatt_manager.set_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
data:
  value: 12345.67
```

Alternativ setzt `offset: 1000` direkt einen Zuschlag von 1000 kWh. Verwende entweder `value` oder `offset`. Der gespeicherte Offset ist als Sensorattribut sichtbar. Um nur diese Kalibrierung zu entfernen:

```yaml
action: solarwatt_manager.reset_stats_value
target:
  entity_id: sensor.kiwigrid_stats_total_consumption_workconsumed
```

## Firmware und Diagnose

Die Integration liest optional die Gateway-Informationen des lokalen Managers. Die kiwiOS-Version erscheint in den Geräteinformationen des Managers und als Diagnosesensor **kiwiOS-Version** auf **SOLARWATT Flow**. Die Seriennummer wird in den Geräteinformationen hinterlegt.

Gateway-Informationen werden beim Laden, über **Daten aktualisieren** und automatisch nach 24 Stunden beim nächsten Coordinator-Update abgefragt. Auch ein fehlgeschlagener Abruf wartet bis zum nächsten automatischen Versuch 24 Stunden; ein manueller Abruf bleibt möglich. Ein fehlender optionaler Gateway-Endpunkt verhindert die Energieaktualisierung nicht.

## Probleme beheben

| Problem | Prüfen |
| --- | --- |
| Lokaler Manager nicht erreichbar | Host/IP, Erreichbarkeit aus dem Home-Assistant-Netz und unterstützte Firmware prüfen; bei Namensauflösungsproblemen die IP verwenden |
| Anmeldung lokal fehlgeschlagen | Passwort der lokalen Weboberfläche und Benutzer `installer` prüfen |
| Anmeldung am Portal fehlgeschlagen | Portal-Zugangsdaten prüfen; bei abgelehnten Zugangsdaten die erneute Authentifizierung in Home Assistant durchführen |
| Sensoren fehlen | Gerät in den Optionen aktivieren; prüfen, ob die Datenquelle das benötigte Feld liefert |
| Monats- oder Jahresquote bleibt gleich | Diese Quoten werden einmal täglich aktualisiert |
| kiwiOS-Version fehlt | SOLARWATT Flow aktivieren und Daten aktualisieren; der optionale Gateway-Endpunkt muss vorhanden sein |
| Werte bleiben bei einer Störung stehen | Letzte gültige Daten können zwischengespeichert bleiben; Diagnose und Verbindungsstatus prüfen |

Für Fehlerberichte nutze die [GitHub Issues](https://github.com/thokaro/solarwatt-manager-homeassistant/issues). Nenne Integrationsversion, Firmware, verwendete Datenquellen und Schritte zum Nachstellen. Diagnose-Downloads anonymisieren Kennungen und entfernen Zugangsdaten, persönliche Bezeichnungen und Standortdaten; numerische Messwerte und Statusangaben bleiben enthalten.

## Weitere Dokumentation

- [evcc einrichten](evcc-guide-german.md)
- [KiwiGrid-Datenpunkte](kiwigrid-items.md)
- [Englische README mit weiteren technischen Details](../README.md)
- [Änderungen und Release-Hinweise](../CHANGELOG.md)

Das Projekt ist unabhängig von Solarwatt GmbH und steht unter der Apache License 2.0.
