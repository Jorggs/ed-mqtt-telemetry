# ED MQTT Telemetry (standalone)

A standalone Windows system-tray app that reads Elite Dangerous's journal
files and `Status.json` **directly** (no EDMC install required) and
republishes them to a user-configured MQTT broker, using the **same topic
tree** as [fasteddy516/EDMC-Telemetry](https://github.com/fasteddy516/EDMC-Telemetry)
(the EDMC plugin this replaces). If you've already built sensors,
ESPHome displays, or Home Assistant automations against that plugin's
topics, they should keep working unchanged.

## Why this exists

EDMC-Telemetry is a *plugin* — it requires the full
[ED Market Connector](https://github.com/EDCD/EDMarketConnector) app to be
installed and running. This project reads the same underlying data sources
(the journal log files and `Status.json` that Elite Dangerous itself writes
to `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`) without
needing EDMC at all — just a single `.exe`.

## Important: building the .exe

PyInstaller builds a native executable for whatever OS it runs on, so the
`.exe` **must be built on Windows** (or via the included CI workflow) — it
can't be cross-compiled from Linux/macOS. Two ways to get the binary:

1. **GitHub Actions (recommended, zero setup):** push this repo to GitHub.
   The included workflow (`.github/workflows/build-windows.yml`) builds
   `ED-MQTT-Telemetry.exe` automatically on a Windows runner every time you
   push, and uploads it as a workflow artifact. Push a tag like `v1.0.0` and
   it'll also attach the exe to a GitHub Release.
2. **Locally on a Windows PC:** install Python 3.10+, then double-click
   `build.bat` (or run it from a command prompt). The finished exe appears
   at `dist\ED-MQTT-Telemetry.exe`.

## Running it

Launch the exe — it sits in the system tray (a small circular icon that
turns grey → amber → green as it goes from stopped → connecting →
connected). Right-click for:

- **Start / Stop monitoring**
- **Settings...** — configure the MQTT broker, credentials, topic layout,
  and journal folder
- **Exit**

By default it auto-starts monitoring and auto-detects your journal folder
at `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`.
Settings are stored in `%APPDATA%\EDMQTTTelemetry\settings.json` (same
structure as EDMC-Telemetry's own `settings.json`, so if you've customised
topics there before you can copy that file over).

## Topic reference

With default settings (`root = "Telemetry"`):

| Topic | Description |
|---|---|
| `Telemetry/FeedActive` | `True`/`False`, retained, set via MQTT Last-Will-and-Testament — always reflects whether this app is currently connected. |
| `Telemetry/GameRunning` | `True`/`False` — whether the Elite Dangerous process is currently running. |
| `Telemetry/Journal` | *(Raw mode)* the raw JSON line for every journal event, published as-is. |
| `Telemetry/Journal/<EventName>` | *(Processed mode, default)* one topic per event type, e.g. `Telemetry/Journal/Docked`, `Telemetry/Journal/FSDJump` — payload is the full event JSON. |
| `Telemetry/Dashboard` | *(Raw mode)* the full `Status.json` content, published as-is whenever it changes. |
| `Telemetry/Dashboard/<Key>` | *(Processed mode, default)* one topic per top-level Status.json key (`Flags`, `Flags2`, `FireGroup`, `GuiFocus`, `Cargo`, `LegalState`, etc.) — published only when the value changes. |
| `Telemetry/Dashboard/Pips/Sys`, `.../Eng`, `.../Wep` | Individual pip values, broken out from the `Pips` array. |
| `Telemetry/Dashboard/Fuel/Main`, `.../Reservoir` | Individual fuel values, broken out from the `Fuel` object. |
| `Telemetry/Location/System` | Current star system, tracked internally — only published when it changes. |
| `Telemetry/Location/Station` | Current station (blank when not docked) — only published when it changes. |
| `Telemetry/Location/State` | *(off by default — verbose)* a best-effort snapshot of commander/ship/rank/location state, rebuilt from journal events. |

All of the above topic **names** are customizable in Settings → Data, exactly
like the original plugin's `settings.json` (`topics.root`, `topics.dashboard`,
etc.) — the JSON keys match one-for-one.

### A note on `Telemetry/Location/State`

This is a reconstruction, not a byte-for-byte copy of EDMC's internal
`state` object — it covers commander name, credits, ship, rank/progress/
reputation, and current system/station/body, built up by watching the
journal stream from scratch each time the app starts. If you need something
that's guaranteed to match the game exactly, use the **Processed journal
topics** (`Telemetry/Journal/<EventName>`) — those are the raw event
payloads Elite Dangerous itself writes, unmodified.

## Project layout

```
src/
  main.py              tray icon + app entry point
  engine.py            wires everything together, publishes to MQTT
  config.py            settings load/save (%APPDATA%\EDMQTTTelemetry\settings.json)
  journal_watcher.py    tails the newest Journal.*.log, handles rotation
  dashboard_watcher.py  watches Status.json for changes
  game_process.py       detects whether Elite Dangerous is running
  state_tracker.py      builds the best-effort "Location/State" snapshot
  mqtt_publisher.py     paho-mqtt wrapper (LWT, TLS, topic helpers)
  gui_settings.py       tkinter settings dialog
requirements.txt
build.bat                        local Windows build script
.github/workflows/build-windows.yml   CI build via GitHub Actions
```

## Limitations

- Windows only (relies on `Saved Games\...` path conventions and Windows-style
  system tray via `pystray`'s win32 backend).
- MQTT v3.1.1 over TCP (same as the original plugin) — no WebSockets.
- `Location/State` is best-effort, as noted above.
