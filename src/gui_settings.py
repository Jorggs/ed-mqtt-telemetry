"""
Settings window: two tabs (Connection, Data) matching the fields exposed by
EDMC-Telemetry's own settings dialog, plus a couple of standalone-only extras
(journal folder override, autostart).
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import config


class SettingsWindow:
    def __init__(self, settings, on_save, parent=None):
        self.settings = settings
        self.on_save = on_save  # on_save(new_settings)

        # If a parent Tk root is supplied (the tray app's hidden main-thread
        # root), open as a Toplevel so we never spin up a second mainloop.
        # Otherwise (e.g. running this file standalone for testing) create
        # our own Tk root.
        self.root = tk.Toplevel(parent) if parent is not None else tk.Tk()
        self.root.title("ED MQTT Telemetry - Settings")
        self.root.geometry("480x520")
        self.root.resizable(False, False)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.conn_tab = ttk.Frame(nb)
        self.data_tab = ttk.Frame(nb)
        nb.add(self.conn_tab, text="Connection")
        nb.add(self.data_tab, text="Data")

        self.vars = {}
        self._build_connection_tab()
        self._build_data_tab()

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.root.destroy).pack(side="right")

    # ---- layout helpers -----------------------------------------------

    def _row(self, parent, r, label, key, width=28, show=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
        var = tk.StringVar(value=str(self.settings.get(key, "")))
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show)
        entry.grid(row=r, column=1, sticky="w", padx=6, pady=4)
        self.vars[key] = var
        return entry

    def _check(self, parent, r, label, key, col=0):
        var = tk.BooleanVar(value=bool(self.settings.get(key, False)))
        cb = ttk.Checkbutton(parent, text=label, variable=var)
        cb.grid(row=r, column=col, sticky="w", padx=6, pady=4)
        self.vars[key] = var
        return cb

    def _combo(self, parent, r, label, key, options):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
        var = tk.StringVar(value=str(self.settings.get(key, options[0])))
        combo = ttk.Combobox(parent, textvariable=var, values=options, state="readonly", width=15)
        combo.grid(row=r, column=1, sticky="w", padx=6, pady=4)
        self.vars[key] = var
        return combo

    # ---- tabs -----------------------------------------------------------

    def _build_connection_tab(self):
        f = self.conn_tab
        r = 0
        self._row(f, r, "Broker Address:", "broker"); r += 1
        self._row(f, r, "Port:", "port"); r += 1
        self._row(f, r, "QoS (0/1/2):", "qos"); r += 1
        self._row(f, r, "Keepalive (s):", "keepalive"); r += 1
        self._row(f, r, "Client ID:", "client_id"); r += 1
        self._row(f, r, "Username:", "username"); r += 1
        self._row(f, r, "Password:", "password", show="*"); r += 1
        self._check(f, r, "Encrypted connection (TLS)", "encryption"); r += 1
        self._row(f, r, "CA Cert path:", "ca_certs", width=34); r += 1
        self._row(f, r, "Client Cert path:", "certfile", width=34); r += 1
        self._row(f, r, "Client Key path:", "keyfile", width=34); r += 1
        self._check(f, r, "Skip certificate verification", "tls_insecure"); r += 1

    def _build_data_tab(self):
        f = self.data_tab
        r = 0
        self._row(f, r, "Root topic:", "topics.root"); r += 1
        self._check(f, r, "Convert topics to lowercase", "lowercase_topics"); r += 1

        ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        self._check(f, r, "Publish Dashboard", "dashboard"); r += 1
        self._combo(f, r, "Dashboard format:", "dashboard_format", ["Processed", "Raw"]); r += 1

        ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        self._check(f, r, "Publish Journal", "journal"); r += 1
        self._combo(f, r, "Journal format:", "journal_format", ["Processed", "Raw"]); r += 1
        ttk.Label(f, text="Excluded event types (comma-separated):").grid(
            row=r, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 0)
        )
        r += 1
        excl_var = tk.StringVar(
            value=", ".join(self.settings.get("excluded_journal_events", []))
        )
        self.vars["excluded_journal_events"] = excl_var
        ttk.Entry(f, textvariable=excl_var, width=48).grid(
            row=r, column=0, columnspan=2, sticky="w", padx=6, pady=4
        )
        r += 1

        ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        self._check(f, r, "Publish current System/Station", "location"); r += 1
        self._check(f, r, "Publish internal state (best-effort, verbose)", "state"); r += 1

        ttk.Separator(f, orient="horizontal").grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        ttk.Label(f, text="Journal folder (blank = auto-detect):").grid(
            row=r, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 0)
        )
        r += 1
        jp_var = tk.StringVar(value=self.settings.get("journal_path", ""))
        self.vars["journal_path"] = jp_var
        entry = ttk.Entry(f, textvariable=jp_var, width=38)
        entry.grid(row=r, column=0, sticky="w", padx=6, pady=4)
        ttk.Button(f, text="Browse...", command=lambda: self._browse(jp_var)).grid(
            row=r, column=1, sticky="w", padx=6, pady=4
        )
        r += 1
        self._check(f, r, "Start monitoring automatically on launch", "autostart"); r += 1

    def _browse(self, var):
        path = filedialog.askdirectory(title="Select Elite Dangerous journal folder")
        if path:
            var.set(path)

    # ---- special handling for nested "topics.root" key ------------------

    def _row(self, parent, r, label, key, width=28, show=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
        if key == "topics.root":
            initial = self.settings.get("topics", {}).get("root", "Telemetry")
        else:
            initial = self.settings.get(key, "")
        var = tk.StringVar(value=str(initial))
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show)
        entry.grid(row=r, column=1, sticky="w", padx=6, pady=4)
        self.vars[key] = var
        return entry

    # ---- save -------------------------------------------------------------

    def _save(self):
        new_settings = json_copy(self.settings)
        try:
            for key, var in self.vars.items():
                value = var.get()
                if key == "topics.root":
                    new_settings["topics"]["root"] = value
                elif key == "excluded_journal_events":
                    new_settings[key] = [
                        s.strip() for s in value.split(",") if s.strip()
                    ]
                elif key in ("port", "keepalive", "qos"):
                    new_settings[key] = int(value)
                elif isinstance(var, tk.BooleanVar):
                    new_settings[key] = bool(value)
                else:
                    new_settings[key] = value
        except ValueError as e:
            messagebox.showerror("Invalid value", f"Please check numeric fields.\n{e}")
            return

        config.save_settings(new_settings)
        self.on_save(new_settings)
        self.root.destroy()

    def show(self):
        # Only run our own mainloop if we created a standalone Tk root
        # (no parent was supplied). When embedded as a Toplevel of the tray
        # app's hidden root, that root's mainloop is already running.
        if self.root.master is None:
            self.root.mainloop()


def json_copy(d):
    import json as _json
    return _json.loads(_json.dumps(d))
