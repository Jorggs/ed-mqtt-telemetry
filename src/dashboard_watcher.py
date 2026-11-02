"""
Watches Status.json (the "dashboard" file Elite Dangerous updates continuously
while flying) and calls back whenever its content changes.
"""

import json
import os
import threading
import time


class DashboardWatcher(threading.Thread):
    def __init__(self, journal_path, on_status, on_log=None, poll_interval=0.2):
        super().__init__(daemon=True)
        self.status_file = os.path.join(journal_path, "Status.json")
        self.on_status = on_status  # on_status(data: dict)
        self.on_log = on_log or (lambda msg: None)
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._last_mtime = None

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                if os.path.exists(self.status_file):
                    mtime = os.path.getmtime(self.status_file)
                    if mtime != self._last_mtime:
                        # tiny delay -- the game can be mid-write
                        time.sleep(0.02)
                        try:
                            with open(self.status_file, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read().strip()
                            if content:
                                data = json.loads(content)
                                self.on_status(data)
                            # Only commit the mtime once we've successfully
                            # parsed it -- if the read caught a partial write,
                            # leave _last_mtime alone so we retry next poll
                            # instead of silently losing that update forever.
                            self._last_mtime = mtime
                        except (json.JSONDecodeError, OSError):
                            pass
            except Exception as e:
                self.on_log(f"Dashboard watcher error: {e}")
            time.sleep(self.poll_interval)
