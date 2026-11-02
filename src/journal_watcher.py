"""
Tails the newest Journal.*.log file in the Elite Dangerous journal folder,
handling log rotation (a new file appears whenever the game restarts / a new
session begins).

On startup it does a silent "priming" pass over the current journal file so
that internal state (current system, station, ship, etc.) can be
reconstructed immediately, without re-publishing every historical event to
MQTT. After priming, it seeks to the end of file and begins live tailing.
"""

import glob
import json
import os
import threading
import time


class JournalWatcher(threading.Thread):
    def __init__(self, journal_path, on_event, on_log=None, on_primed=None, poll_interval=0.5):
        super().__init__(daemon=True)
        self.journal_path = journal_path
        self.on_event = on_event  # on_event(data: dict, raw_line: str, live: bool)
        self.on_log = on_log or (lambda msg: None)
        self.on_primed = on_primed or (lambda: None)
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self.current_file = None
        self.current_fh = None

    def stop(self):
        self._stop.set()

    def _latest_journal_file(self):
        pattern = os.path.join(self.journal_path, "Journal.*.log")
        files = glob.glob(pattern)
        if not files:
            return None
        files.sort(key=lambda f: os.path.getmtime(f))
        return files[-1]

    def _open(self, path, prime):
        self.current_file = path
        self.current_fh = open(path, "r", encoding="utf-8", errors="ignore")
        if prime:
            self.on_log(f"Priming state from {os.path.basename(path)} ...")
            for line in self.current_fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    self.on_event(data, line, False)
                except Exception:
                    pass
            self.on_log("Priming complete, now tailing live events.")
            self.on_primed()
        else:
            # New session file appeared after we were already running --
            # read it from the start since it's brand new.
            self.current_fh.seek(0)

    def run(self):
        first_file = True
        while not self._stop.is_set():
            try:
                latest = self._latest_journal_file()
                if latest and latest != self.current_file:
                    if self.current_fh:
                        self.current_fh.close()
                    self._open(latest, prime=first_file)
                    first_file = False

                if self.current_fh:
                    line = self.current_fh.readline()
                    if line:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                data = None
                            if data is not None:
                                try:
                                    self.on_event(data, line, True)
                                except Exception as e:
                                    self.on_log(f"Error handling journal event: {e}")
                    else:
                        time.sleep(self.poll_interval)
                else:
                    time.sleep(self.poll_interval)
            except Exception as e:
                self.on_log(f"Journal watcher error: {e}")
                time.sleep(self.poll_interval)
