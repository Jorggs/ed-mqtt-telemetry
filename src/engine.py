"""
Ties together the journal watcher, dashboard watcher, game-running watcher
and the MQTT publisher, reproducing EDMC-Telemetry's topic tree:

  <root>/FeedActive                  (retained, LWT)
  <root>/GameRunning
  <root>/Journal                     (Raw mode: full JSON per line)
  <root>/Journal/<EventName>         (Processed mode: one topic per event type)
  <root>/Dashboard                   (Raw mode: full Status.json as-is)
  <root>/Dashboard/<Key>             (Processed mode: one topic per status key)
  <root>/Dashboard/Pips/Sys|Eng|Wep
  <root>/Dashboard/Fuel/Main|Reservoir
  <root>/Location/System
  <root>/Location/Station
  <root>/Location/State              (best-effort internal state blob)
"""

import json

from config import resolved_journal_path
from dashboard_watcher import DashboardWatcher
from game_process import GameRunningWatcher
from journal_watcher import JournalWatcher
from mqtt_publisher import MQTTPublisher
from state_tracker import StateTracker


class Engine:
    def __init__(self, settings, on_log=None, on_mqtt_status=None):
        self.settings = settings
        self.on_log = on_log or (lambda msg: None)
        self.on_mqtt_status = on_mqtt_status or (lambda connected: None)

        self.mqtt = MQTTPublisher(settings, on_status=self._on_mqtt_status, on_log=self.on_log)
        self.state_tracker = StateTracker()

        self.journal_watcher = None
        self.dashboard_watcher = None
        self.game_watcher = None

        self._last_dashboard = {}
        self._latest_dashboard = None   # most recent Status.json contents
        self._game_running = None       # None until the first process check
        self._primed = False            # startup journal pass finished
        self.running = False

    def _on_mqtt_status(self, connected):
        if connected:
            self._clear_stale_raw_topics()
            self._republish_current()
        self.on_mqtt_status(connected)

    def _republish_current(self):
        """The broker connection is made in the background, so the first
        game-running / state / dashboard publishes at startup can happen
        before it is up and are silently dropped. Re-send everything we
        currently know each time we (re)connect."""
        t = self.settings["topics"]
        if self._game_running is not None:
            self.mqtt.publish([t["gamerunning"]], self._game_running, retain=True)
        if self._primed:
            self._publish_known_state()
        if self._latest_dashboard is not None:
            self._last_dashboard = {}   # forget what we think was sent
            self._on_dashboard(self._latest_dashboard)

    def _clear_stale_raw_topics(self):
        """In Processed mode the bare <root>/Journal and <root>/Dashboard topics
        are unused. If the app previously ran in Raw mode, a retained raw
        message is still sitting there and looks like 'raw data'. An empty
        retained payload deletes it from the broker."""
        t = self.settings["topics"]
        if self.settings.get("journal_format", "Processed") != "Raw":
            self.mqtt.publish_raw(self.mqtt.topic_for(t["journal"]), "", retain=True)
        if self.settings.get("dashboard_format", "Processed") != "Raw":
            self.mqtt.publish_raw(self.mqtt.topic_for(t["dashboard"]), "", retain=True)

    # ---- lifecycle ---------------------------------------------------

    def start(self):
        if self.running:
            return
        t = self.settings["topics"]
        journal_path = resolved_journal_path(self.settings)
        self.on_log(f"Journal folder: {journal_path}")

        self.mqtt.start()

        self.game_watcher = GameRunningWatcher(self._on_game_running)
        self.game_watcher.start()

        self.journal_watcher = JournalWatcher(
            journal_path, self._on_journal_event, on_log=self.on_log, on_primed=self._on_primed
        )
        self.journal_watcher.start()

        if self.settings.get("dashboard", True):
            self.dashboard_watcher = DashboardWatcher(
                journal_path, self._on_dashboard, on_log=self.on_log
            )
            self.dashboard_watcher.start()

        self.running = True

    def stop(self):
        if self.journal_watcher:
            self.journal_watcher.stop()
        if self.dashboard_watcher:
            self.dashboard_watcher.stop()
        if self.game_watcher:
            self.game_watcher.stop()
        self.mqtt.stop()
        self.running = False

    # ---- game running --------------------------------------------------

    def _on_game_running(self, running):
        t = self.settings["topics"]
        self._game_running = running
        self.mqtt.publish([t["gamerunning"]], running, retain=True)

    def _publish_location(self):
        t = self.settings["topics"]
        s = self.state_tracker.state
        self.mqtt.publish([t["location"], t["system"]], self.state_tracker.system or "", retain=True)
        self.mqtt.publish([t["location"], t["station"]], self.state_tracker.station or "", retain=True)
        self.mqtt.publish([t["location"], t["body"]], s.get("Body") or "", retain=True)
        if s.get("SystemPopulation") is not None:
            self.mqtt.publish([t["location"], t["population"]], s.get("SystemPopulation"), retain=True)
        if s.get("StarPos") is not None:
            self.mqtt.publish([t["location"], t["starpos"]], s.get("StarPos"), retain=True)

    def _publish_ship(self):
        t = self.settings["topics"]
        s = self.state_tracker.state
        # Publish the name whenever it's *known*, including empty (an unnamed
        # ship). Skipping empty values left the previous ship's name sitting
        # on the retained topic. An empty retained payload also clears the
        # retained message on the broker, which is the right outcome.
        if s.get("ShipName") is not None:
            self.mqtt.publish([t["ship"], t["shipname"]], s.get("ShipName"), retain=True)
        if s.get("ShipType"):
            self.mqtt.publish([t["ship"], t["shiptype"]], s.get("ShipType"), retain=True)
        if s.get("ShipTypeDisplay"):
            self.mqtt.publish([t["ship"], t["shiptypedisplay"]], s.get("ShipTypeDisplay"), retain=True)
        if s.get("MaxJumpRange") is not None:
            self.mqtt.publish([t["ship"], t["jumprange"]], s.get("MaxJumpRange"), retain=True)

    def _on_primed(self):
        """Called once the silent startup priming pass over the current
        journal file completes -- publish the reconstructed state/location/ship
        immediately rather than waiting for the next live event."""
        self._primed = True
        self._publish_known_state()

    def _publish_known_state(self):
        t = self.settings["topics"]
        if self.settings.get("location", True):
            self._publish_location()
        if self.settings.get("ship_info", True):
            self._publish_ship()
        if self.settings.get("state", False):
            self.mqtt.publish([t["state"]], self.state_tracker.state, retain=True)

    # ---- journal ---------------------------------------------------------

    def _on_journal_event(self, data, raw_line, live):
        t = self.settings["topics"]

        # Always keep internal state up to date, even during priming.
        location_changed, state_changed, ship_changed = self.state_tracker.ingest(data)

        if not live:
            return  # priming pass: update state silently, no publishing

        if self.settings.get("journal", True):
            event_name = data.get("event", "Unknown")
            excluded = {e.lower() for e in self.settings.get("excluded_journal_events", [])}
            if event_name.lower() not in excluded:
                if self.settings.get("journal_format", "Processed") == "Raw":
                    self.mqtt.publish_raw(self.mqtt.topic_for(t["journal"]), raw_line, retain=True)
                else:
                    self.mqtt.publish([t["journal"], event_name], data, retain=True)

        if self.settings.get("location", True) and location_changed:
            self._publish_location()

        if self.settings.get("ship_info", True) and ship_changed:
            self._publish_ship()

        if self.settings.get("state", False) and state_changed:
            self.mqtt.publish([t["state"]], self.state_tracker.state, retain=True)

    # ---- dashboard ---------------------------------------------------------

    def _on_dashboard(self, data):
        t = self.settings["topics"]
        self._latest_dashboard = data

        if self.settings.get("dashboard_format", "Processed") == "Raw":
            if data != self._last_dashboard:
                self._last_dashboard = data
                self.mqtt.publish_raw(self.mqtt.topic_for(t["dashboard"]), json.dumps(data), retain=True)
            return

        prev = self._last_dashboard
        for key, value in data.items():
            if key in ("timestamp", "event"):
                continue  # Status.json metadata, not a real dashboard value
            if key == "Pips" and isinstance(value, list) and len(value) == 3:
                prev_pips = prev.get("Pips") if isinstance(prev.get("Pips"), list) else [None, None, None]
                labels = [t["sys"], t["eng"], t["wep"]]
                for idx, label in enumerate(labels):
                    if value[idx] != (prev_pips[idx] if idx < len(prev_pips) else None):
                        self.mqtt.publish([t["dashboard"], t["pips"], label], value[idx], retain=True)
            elif key == "Fuel" and isinstance(value, dict):
                prev_fuel = prev.get("Fuel") if isinstance(prev.get("Fuel"), dict) else {}
                if value.get("FuelMain") != prev_fuel.get("FuelMain"):
                    self.mqtt.publish([t["dashboard"], t["fuel"], t["fuelmain"]], value.get("FuelMain"), retain=True)
                if value.get("FuelReservoir") != prev_fuel.get("FuelReservoir"):
                    self.mqtt.publish(
                        [t["dashboard"], t["fuel"], t["fuelreservoir"]], value.get("FuelReservoir"), retain=True
                    )
            else:
                if value != prev.get(key):
                    self.mqtt.publish([t["dashboard"], key], value, retain=True)

        self._last_dashboard = data
