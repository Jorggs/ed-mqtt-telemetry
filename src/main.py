"""
ED MQTT Telemetry (standalone) -- system tray entry point.

Reads Elite Dangerous's journal files and Status.json directly (no EDMC
install required) and republishes them to a user-configured MQTT broker
using the same topic tree as fasteddy516/EDMC-Telemetry.
"""

import queue
import threading
import tkinter as tk

import pystray

import config
from engine import Engine
from gui_settings import SettingsWindow
from icon_art import make_icon

STATE_STOPPED = "stopped"
STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_ERROR = "error"

COLORS = {
    STATE_STOPPED: (130, 130, 130, 255),
    STATE_CONNECTING: (230, 175, 40, 255),
    STATE_CONNECTED: (45, 175, 90, 255),
    STATE_ERROR: (205, 55, 55, 255),
}


def make_icon_image(color):
    # Same artwork as the .exe icon, plus a status dot in the given colour.
    return make_icon(64, color)


class App:
    def __init__(self):
        self.settings = config.load_settings()
        self.engine = None
        self.status = STATE_STOPPED
        self.action_queue = queue.Queue()
        self._icon_lock = threading.RLock()

        self.icon = pystray.Icon(
            "ed_mqtt_telemetry",
            make_icon_image(COLORS[STATE_STOPPED]),
            "ED MQTT Telemetry (stopped)",
            menu=self._build_menu(),
        )

        # Hidden root window: owns the one-and-only Tk mainloop, used for
        # the settings dialog. Never shown itself.
        self.tk_root = tk.Tk()
        self.tk_root.withdraw()

    # ---- menu -----------------------------------------------------------

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                "Start monitoring",
                self._queue_action("start"),
                enabled=lambda item: not self._running(),
            ),
            pystray.MenuItem(
                "Stop monitoring",
                self._queue_action("stop"),
                enabled=lambda item: self._running(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings...", self._queue_action("settings")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._queue_action("exit")),
        )

    def _running(self):
        return self.engine is not None and self.engine.running

    def _queue_action(self, name):
        def handler(icon, item):
            self.action_queue.put(name)
        return handler

    # ---- status / logging -------------------------------------------------

    def _log(self, msg):
        print(msg, flush=True)

    def _refresh_icon(self):
        # Redraw the tray icon and tooltip from the current status.
        with self._icon_lock:
            status = self.status
            try:
                self.icon.icon = make_icon_image(COLORS[status])
                self.icon.title = f"ED MQTT Telemetry ({status})"
                self.icon.update_menu()
            except Exception as e:
                self._log(f"Tray icon update failed: {e}")

    def _set_status(self, status):
        self.status = status
        self._refresh_icon()

    def _tray_ready(self, icon):
        # Runs once the tray icon exists. MQTT can connect before this point,
        # in which case that status change was never drawn -- so draw the
        # current status now.
        icon.visible = True
        self._refresh_icon()

    def _on_mqtt_status(self, connected):
        if connected:
            self._set_status(STATE_CONNECTED)
        elif self._running():
            self._set_status(STATE_CONNECTING)

    # ---- engine control ------------------------------------------------

    def start_engine(self):
        if self._running():
            return
        self.settings = config.load_settings()
        self.engine = Engine(self.settings, on_log=self._log, on_mqtt_status=self._on_mqtt_status)
        self._set_status(STATE_CONNECTING)
        try:
            self.engine.start()
        except Exception as e:
            self._log(f"Failed to start: {e}")
            self._set_status(STATE_ERROR)

    def stop_engine(self):
        if self.engine:
            self.engine.stop()
        self._set_status(STATE_STOPPED)

    def open_settings(self):
        def on_save(new_settings):
            self.settings = new_settings
            if self._running():
                self.stop_engine()
                self.start_engine()
        SettingsWindow(self.settings, on_save, parent=self.tk_root).show()

    # ---- main loop --------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                action = self.action_queue.get_nowait()
                if action == "start":
                    self.start_engine()
                elif action == "stop":
                    self.stop_engine()
                elif action == "settings":
                    self.open_settings()
                elif action == "exit":
                    self.stop_engine()
                    self.icon.stop()
                    self.tk_root.quit()
                    return
        except queue.Empty:
            pass
        self.tk_root.after(200, self._poll_queue)

    def run(self):
        # pystray's own event loop runs in a background thread; the Tk
        # mainloop (required for the settings dialog) owns the main thread.
        threading.Thread(
            target=lambda: self.icon.run(setup=self._tray_ready), daemon=True
        ).start()
        if self.settings.get("autostart", True):
            self.start_engine()
        self.tk_root.after(200, self._poll_queue)
        self.tk_root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    main()
