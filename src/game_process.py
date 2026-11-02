"""
Polls the process list to determine whether Elite Dangerous is currently
running, mirroring EDMC-Telemetry's Telemetry/GameRunning topic.
"""

import threading
import time

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

PROCESS_NAMES = ("elitedangerous64.exe", "elitedangerous32.exe", "elitedangerous.exe")


class GameRunningWatcher(threading.Thread):
    def __init__(self, on_change, poll_interval=5.0):
        super().__init__(daemon=True)
        self.on_change = on_change  # on_change(running: bool)
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._last = None

    def stop(self):
        self._stop.set()

    def _is_running(self):
        if psutil is None:
            return None
        try:
            for p in psutil.process_iter(["name"]):
                name = (p.info.get("name") or "").lower()
                if name in PROCESS_NAMES:
                    return True
        except Exception:
            pass
        return False

    def run(self):
        while not self._stop.is_set():
            running = self._is_running()
            if running is not None and running != self._last:
                self._last = running
                self.on_change(running)
            time.sleep(self.poll_interval)
