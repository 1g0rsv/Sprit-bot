# Sprit-bot
Sprit Bot – Überwachung von Kraftstoffpreisen
# Sprit Bot – Überwachung von Kraftstoffpreisen

**Sprit Bot** ist ein Pet Project zur Überwachung von Kraftstoffpreisen an Tankstellen in Deutschland. Das Projekt sammelt Daten von der [ADAC-Spritpreis-API](https://github.com/TomBursch/ADAC-Spritpreis-API), speichert diese in einer SQLite-Datenbank und informiert Telegram-Abonnenten über signifikante Preisänderungen.

## Funktionalitäten

- **Datensammlung (Collector):**
  - Periodisches Abfragen der API des ADAC-Spritpreis‑Services, um aktuelle Preise für Diesel, E10 und Super an mehreren Tankstellen zu erhalten.
  - Filterung von Mikroveränderungen mithilfe eines Debounce‑Mechanismus: Preisänderungen, die unter einem definierten Schwellenwert (z. B. 0,02 oder 0,01) liegen, werden ignoriert, bis sich der Preis in mindestens zwei aufeinanderfolgenden Abfragen stabil ändert.
  - Speicherung der abgerufenen Daten in einer SQLite-Datenbank.

- **Telegram-Bot:**
  - Der Bot liest die in der Datenbank gespeicherten Preisdaten und informiert die Abonnenten in Telegram, sobald stabile Preisänderungen festgestellt werden.
  - Nutzer können sich mit dem Befehl `/start` anmelden und erhalten anschließend Benachrichtigungen zu den überwachten Tankstellen.

## Projektstruktur

Im Projektstamm sollten folgende Dateien und Ordner vorhanden sein:

- **sprit-bot-app-v1.04.py** – Die Hauptdatei des Telegram-Bots (im Container wird sie als `sprit-bot-app.py` verwendet).
- **collector.py** – Das Skript zur Datensammlung, das die API abfragt und die Ergebnisse in die Datenbank schreibt.
- **stations.json** – Eine Konfigurationsdatei, die eine Liste der Tankstellen und deren API‑URLs enthält.
- **requirements.txt** – Eine Liste der benötigten Python‑Pakete.
- **docker-compose.yml** – Die Docker‑Compose‑Datei zur Orchestrierung der Container.
- **.env** (optional) – Eine Datei zur Definition von Umgebungsvariablen (z. B. `BOT_TOKEN`).
- **data/** – Ein Ordner auf dem Host, der für die persistente Speicherung der Datenbankdateien verwendet wird (z. B. `fuel_data.db` und `subscribers.db`). Falls der Ordner noch nicht existiert, wird er beim ersten Start erstellt.

## Technologien

- **Python 3.10-slim** – Als Basis‑Image für die Container.
- **aiosqlite, aiohttp, nest_asyncio, python-telegram-bot** – Bibliotheken für asynchrone Datenbankzugriffe, HTTP-Anfragen und die Kommunikation mit der Telegram-API.
- **Docker und Docker Compose** – Für das Packaging und den Start der Anwendung in Containern.

## Docker-Konfiguration

### Dockerfile

Das folgende Dockerfile wird verwendet, um das Image zu erstellen:

```dockerfile
# Verwenden des offiziellen Python-Images (z. B. 3.10-slim)
FROM python:3.10-slim

# Setzen des Arbeitsverzeichnisses im Container
WORKDIR /app

# Kopieren der requirements.txt und Installieren der Abhängigkeiten
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Kopieren der Anwendungsdateien in das Arbeitsverzeichnis
COPY sprit-bot-app-v1.04.py /app/sprit-bot-app.py
COPY collector.py /app/collector.py
COPY stations.json /app/

# Standardmäßig wird der Telegram-Bot gestartet (dieser CMD kann via docker-compose überschrieben werden)
CMD ["python", "sprit-bot-app.py"]
