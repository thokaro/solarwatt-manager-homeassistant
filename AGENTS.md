# AGENTS.md

# SOLARWATT Manager Home Assistant

Diese Datei beschreibt die Regeln für KI-Agenten, die an diesem Repository arbeiten.

Der Agent soll diese Regeln vor jeder Änderung berücksichtigen.

---

# Ziel des Projekts

Die SOLARWATT Manager Integration integriert zum einen lokalen Inhalt vom SOLARWATT Manager Flex oder Rail und/oder Daten vom SOLARWATT Manager Portal aktuell via https://hems.kiwigrid.com/v11/ Datenpunkte bzw. API.

Die Integration soll:

- zuverlässig
- wartbar
- performant
- Home-Assistant-konform

sein.

Neue Features dürfen bestehende Installationen niemals verschlechtern.

Rückwärtskompatibilität besitzt grundsätzlich höchste Priorität.

---

# Grundprinzipien

Immer:

- bestehende Architektur respektieren
- vorhandenen Code wiederverwenden
- möglichst wenig ändern
- keine unnötigen Refactorings
- keine kosmetischen Änderungen ohne Nutzen

Nicht:

- Dateien komplett neu schreiben
- große Umstrukturierungen durchführen
- API ändern ohne Notwendigkeit
- bestehende Sensornamen ändern

---

# Vorgehensweise

Vor jeder Aufgabe:

1. Aufgabe verstehen
2. relevante Dateien analysieren
3. kurzen Plan erstellen
4. bestehende Implementierung prüfen
5. Änderungen durchführen
6. Ergebnis validieren

Nicht das komplette Repository analysieren.

Nur Dateien öffnen, die tatsächlich benötigt werden.

---

# Coding Style

Der bestehende Coding Style hat Vorrang.

Nutze:

- Python 3.13+
- Typannotationen
- async/await
- f-Strings
- match/case sofern sinnvoll
- dataclasses nur wenn sinnvoll

Vermeide:

- globale Variablen
- verschachtelte if-Konstruktionen
- unnötige Klassen
- unnötige Helper

---

# Home Assistant

Die Integration soll den aktuellen Home Assistant Standards entsprechen.

Nutze bevorzugt:

ConfigEntry

DataUpdateCoordinator

CoordinatorEntity

EntityDescription

DeviceInfo

Device Registry

Entity Registry

Translations

Diagnostics

Repairs

OptionsFlow

---

# Async

Alle Netzwerkzugriffe müssen async erfolgen.

Keine blockierenden Funktionen.

Nicht verwenden:

time.sleep()

requests

subprocess

threading

Nutzen:

aiohttp

asyncio

Home Assistant Helper

---

# Coordinator

Alle Cloud-Daten werden ausschließlich über den Coordinator aktualisiert.

Der Coordinator besitzt die vollständige API-Antwort.

Sensoren dürfen niemals selbst HTTP Requests durchführen.

Keine Logik in Sensoren implementieren.

---

# API

Die API besitzt eine zentrale Implementierung.

Neue Endpunkte immer zuerst dort ergänzen.

Nicht:

Sensor -> API

Sondern:

API

↓

Coordinator

↓

Sensor

↓

Home Assistant

---

# Cache

API Antworten sollen vollständig gecached werden.

Mehrere Sensoren dürfen niemals denselben Endpunkt mehrfach abrufen.

Wenn Daten bereits vorhanden sind:

immer Cache verwenden.

---

# Fehlerbehandlung

Exceptions niemals verschlucken.

Nicht:

except:
    pass

Sondern:

- passende Exception
- sinnvolle Logmeldung
- Home Assistant Exception falls erforderlich

---

# Logging

Nutze ausschließlich

logging.getLogger(__name__)

Keine print()

Keine Debug-Ausgaben im fertigen Code.

Debug Logging sparsam einsetzen.

---

# Geräte

Jedes physische Gerät besitzt genau ein Device.

Mehrere Sensoren gehören demselben Device an.

DeviceInfo niemals doppelt erzeugen.

---

# Unique IDs

Unique IDs dürfen niemals verändert werden.

Sie müssen:

- stabil
- eindeutig
- dauerhaft

sein.

UUIDs nicht kürzen.

---

# Entity IDs

Entity IDs dürfen sich ändern.

Unique IDs niemals.

---

# Entity Naming

Anzeigenamen stammen bevorzugt aus der API.

Nicht:

UUID

ID

Hash

sondern:

Gerätename

Standortname

API Name

---

# EntityDescription

Neue Sensoren sollen grundsätzlich EntityDescription verwenden.

Keine hunderte einzelner Sensor-Klassen erstellen.

---

# Device Classes

Immer passende DeviceClass verwenden.

Ebenso:

StateClass

EntityCategory

Icon

Suggested Unit

---

# Diagnostics

Diagnostics müssen anonymisiert werden.

Entfernen:

Token

IP

UUID

MAC

Seriennummer

E-Mail

Benutzername

Passwort

Standorte

GPS

---

# Translation

Keine fest codierten Texte.

Neue Texte ausschließlich in den Translation-Dateien.

---

# Optionen

Neue Optionen gehören in OptionsFlow.

Keine versteckten Konstanten.

---

# Config Flow

ConfigFlow möglichst klein halten.

Geschäftslogik gehört nicht in den Config Flow.

---

# Performance

Priorität:

API Calls minimieren

Objekte wiederverwenden

Mehrfachberechnungen vermeiden

Listen nicht mehrfach kopieren

Keine unnötigen Dict Kopien

---

# Speicher

Keine großen Datenstrukturen mehrfach halten.

Bestehende Objekte bevorzugen.

---

# Sensoren

Neue Sensoren sollen:

automatisch erkannt werden

automatisch registriert werden

automatisch aktualisiert werden

---

# Geräteerkennung

Neue Geräte dürfen keine Codeänderung benötigen.

Die API entscheidet welche Geräte existieren.

Nicht:

if device == "FoxESS"

sondern:

Gerät dynamisch erkennen.

---

# Feature Flags

Keine Hardcodierung.

Neue Geräte automatisch unterstützen.

---

# API Erweiterungen

Neue API Felder:

1. API erweitern

2. Coordinator erweitern

3. EntityDescription ergänzen

4. Tests

5. README

---

# Tests

Bestehende Tests niemals grundlos löschen.

Neue Features erhalten Tests.

Fehlerkorrekturen erhalten Regression Tests.

---

# Qualität

Vor Abschluss prüfen:

Ruff

MyPy

Home Assistant Guidelines

---

# Breaking Changes

Breaking Changes vermeiden.

Falls notwendig:

Migration implementieren.

Config Entry Version erhöhen.

Bestehende Installationen migrieren.

---

# Dokumentation

Neue Features:

README

Beispiele

Changelog

Release Notes

aktualisieren.

---

# Git

Keine Formatierungsänderungen ohne funktionalen Nutzen.

Keine Dateien verschieben.

Keine Dateien umbenennen.

---

# Pull Request

Nach Abschluss:

- kurze Zusammenfassung

- geänderte Dateien

- mögliche Auswirkungen

- Breaking Changes

- Migrationsbedarf

---

# Prioritäten

1. Funktionalität

2. Stabilität

3. Home Assistant Konformität

4. Wartbarkeit

5. Performance

6. Lesbarkeit

7. Eleganz

---

# Was vermieden werden soll

Nicht:

komplette Refactorings

unnötige Optimierungen

Namensänderungen

Code verschieben

Style-only Änderungen

unnötige Kommentare

tote Variablen

Duplicate Code

---

# Was bevorzugt wird

kleine Änderungen

wenige Dateien

hohe Lesbarkeit

bestehende Architektur

wenig Risiko

---

# Agent Workflow

Vor jeder Änderung:

- Repository analysieren

- bestehende Lösung verstehen

- Plan erstellen

- minimalen Eingriff wählen

- Änderungen durchführen

- Ergebnis validieren

- Zusammenfassung erstellen

Keine Annahmen treffen, wenn die Implementierung nicht eindeutig ist.

Im Zweifel zunächst analysieren und nachfragen.