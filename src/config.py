"""
Configuration handling for ED MQTT Telemetry (standalone).

The settings schema deliberately mirrors the settings.json format used by
fasteddy516/EDMC-Telemetry (https://github.com/fasteddy516/EDMC-Telemetry)
so that the resulting MQTT topic tree is a drop-in match for anything built
against that plugin.
"""

import json
import os

APP_NAME = "EDMQTTTelemetry"

DEFAULT_SETTINGS = {
    "version": "1.0.0",
    # --- Connection ---
    "broker": "127.0.0.1",
    "port": 1883,
    "keepalive": 60,
    "qos": 0,
    "username": "",
    "password": "",
    "client_id": "EDMCTelemetryPlugin",
    "encryption": False,
    "ca_certs": "",
    "certfile": "",
    "keyfile": "",
    "tls_insecure": False,
    # --- Data ---
    "dashboard": True,
    "dashboard_format": "Raw",         # "Processed" or "Raw" -- Raw matches the
                                        # user's existing HA package (Telemetry/Dashboard
                                        # as a single JSON blob)
    "journal": True,
    "journal_format": "Processed",     # "Processed" or "Raw"
    "location": True,
    "state": True,                     # publishes the merged Telemetry/State blob
    "ship_info": True,                 # publishes dedicated Ship/Name, Ship/Type,
                                        # Ship/JumpRange topics (extracted from
                                        # LoadGame/Loadout/ShipyardSwap, without
                                        # publishing those full raw events)
    # Journal event types that are never published to MQTT (still processed
    # internally for state-tracking purposes where relevant, e.g. Loadout's
    # MaxJumpRange feeds into Telemetry/State, but the raw event itself is
    # noisy/large and isn't republished).
    "excluded_journal_events": [
        "Fileheader",
        "Friends",
        "Materials",
        "ReceiveText",
        "Music",
        "ShipLocker",
        "Loadout",
    ],
    "lowercase_topics": False,
    # --- Standalone-only extras (not part of the original plugin schema) ---
    "journal_path": "",                # blank = auto-detect default location
    "autostart": True,                 # start monitoring as soon as the app launches
    # --- Topic names (customizable exactly like the plugin's settings.json) ---
    "topics": {
        "root": "Telemetry",
        "gamerunning": "GameRunning",
        "feedactive": "FeedActive",
        "dashboard": "Dashboard",
        "journal": "Journal",
        "location": "Location",
        "state": "State",
        "system": "System",
        "station": "Station",
        "pips": "Pips",
        "sys": "Sys",
        "eng": "Eng",
        "wep": "Wep",
        "fuel": "Fuel",
        "fuelreservoir": "Reservoir",
        "fuelmain": "Main",
        "body": "Body",
        "population": "Population",
        "starpos": "StarPos",
        "ship": "Ship",
        "shipname": "Name",
        "shiptype": "Type",
        "shiptypedisplay": "TypeDisplay",
        "jumprange": "JumpRange",
    },
}


def get_config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(get_config_dir(), "settings.json")


def default_journal_path():
    home = os.path.expanduser("~")
    return os.path.join(home, "Saved Games", "Frontier Developments", "Elite Dangerous")


def load_settings():
    path = config_path()
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if k == "topics" and isinstance(v, dict):
                    merged["topics"].update(v)
                else:
                    merged[k] = v
        except Exception:
            pass
    else:
        save_settings(merged)
    return merged


def save_settings(settings):
    path = config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
    return path


def resolved_journal_path(settings):
    p = settings.get("journal_path") or ""
    if p and os.path.isdir(p):
        return p
    return default_journal_path()
