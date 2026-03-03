"""
app.py – Tkinter desktop UI for the Edubind Provisioning Station.

Layout:
    ┌─────────────────────────────────────────────────────┐
    │  Edubind Provisioning Station                       │
    ├─────────────┬───────────────────────────────────────┤
    │ [Settings]  │  Tabs: Provision | History            │
    │             ├───────────────────────────────────────┤
    │  Backend:   │  Provision tab:                       │
    │  [URL____]  │    Port:      [Refresh]  [Dropdown]   │
    │             │    Board:     [detected]              │
    │  Operator:  │    Device ID: [_______]               │
    │  [name___]  │    Firmware:  [Dropdown]              │
    │             │    [  Start Provisioning  ]           │
    │             │    ─────── Log ────────────           │
    │             │    [log area                ]         │
    │             │                                       │
    └─────────────┴───────────────────────────────────────┘
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

from station.backend_client import BackendClient
from station.config_injector import DeviceConfig, inject_config
from station.device_detector import DetectedDevice, list_ports
from station.flasher import flash_firmware


class ProvisioningApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Edubind Provisioning Station")
        self.geometry("900x600")
        self.resizable(True, True)

        self._client: Optional[BackendClient] = None
        self._detected_ports: list[DetectedDevice] = []
        self._firmwares: list[dict] = []
        self._current_job_id: Optional[str] = None

        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        # ---- Left panel (settings) ----
        left = ttk.LabelFrame(self, text="Settings", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        ttk.Label(left, text="Backend URL:").pack(anchor="w")
        self._backend_url_var = tk.StringVar(value="http://localhost:8080")
        ttk.Entry(left, textvariable=self._backend_url_var, width=28).pack(fill=tk.X)

        ttk.Label(left, text="Operator:").pack(anchor="w", pady=(8, 0))
        self._operator_var = tk.StringVar(value=socket.gethostname())
        ttk.Entry(left, textvariable=self._operator_var, width=28).pack(fill=tk.X)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        self._connect_btn = ttk.Button(left, text="Connect to Backend",
                                       command=self._connect_backend)
        self._connect_btn.pack(fill=tk.X)

        self._status_var = tk.StringVar(value="Not connected")
        ttk.Label(left, textvariable=self._status_var,
                  wraplength=180, foreground="red").pack(anchor="w", pady=(4, 0))

        # ---- Right panel (tabs) ----
        right = ttk.Frame(self, padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(right)
        notebook.pack(fill=tk.BOTH, expand=True)

        self._provision_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self._provision_tab, text="Provision")

        self._history_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self._history_tab, text="History")

        self._build_provision_tab()
        self._build_history_tab()

    def _build_provision_tab(self) -> None:
        tab = self._provision_tab

        # Row: Port
        row0 = ttk.Frame(tab)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="Serial port:", width=14).pack(side=tk.LEFT)
        self._port_var = tk.StringVar()
        self._port_combo = ttk.Combobox(row0, textvariable=self._port_var,
                                        state="readonly", width=25)
        self._port_combo.pack(side=tk.LEFT)
        ttk.Button(row0, text="Refresh", command=self._refresh_ports).pack(
            side=tk.LEFT, padx=4)

        # Row: Board
        row1 = ttk.Frame(tab)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Board:", width=14).pack(side=tk.LEFT)
        self._board_var = tk.StringVar(value="—")
        ttk.Label(row1, textvariable=self._board_var).pack(side=tk.LEFT)

        # Row: Device ID
        row2 = ttk.Frame(tab)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Device ID:", width=14).pack(side=tk.LEFT)
        self._device_id_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self._device_id_var, width=28).pack(side=tk.LEFT)

        # Row: Site
        row3 = ttk.Frame(tab)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Site:", width=14).pack(side=tk.LEFT)
        self._site_var = tk.StringVar()
        ttk.Entry(row3, textvariable=self._site_var, width=28).pack(side=tk.LEFT)

        # Row: Firmware
        row4 = ttk.Frame(tab)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="Firmware:", width=14).pack(side=tk.LEFT)
        self._firmware_var = tk.StringVar()
        self._firmware_combo = ttk.Combobox(row4, textvariable=self._firmware_var,
                                            state="readonly", width=40)
        self._firmware_combo.pack(side=tk.LEFT)
        ttk.Button(row4, text="Refresh", command=self._refresh_firmwares).pack(
            side=tk.LEFT, padx=4)

        # Start button
        self._start_btn = ttk.Button(tab, text="▶  Start Provisioning",
                                     command=self._start_provisioning, state="disabled")
        self._start_btn.pack(pady=8)

        # Progress bar
        self._progress = ttk.Progressbar(tab, mode="indeterminate")
        self._progress.pack(fill=tk.X, pady=2)

        # Log
        ttk.Label(tab, text="Log:").pack(anchor="w")
        self._log_area = scrolledtext.ScrolledText(tab, height=12, state="disabled",
                                                   font=("Courier", 9))
        self._log_area.pack(fill=tk.BOTH, expand=True)

        # Bind port selection to board update
        self._port_combo.bind("<<ComboboxSelected>>", self._on_port_selected)

    def _build_history_tab(self) -> None:
        tab = self._history_tab

        self._refresh_hist_btn = ttk.Button(tab, text="Refresh History",
                                            command=self._refresh_history)
        self._refresh_hist_btn.pack(anchor="w", pady=(0, 4))

        cols = ("job_id", "device", "firmware", "operator", "result", "started")
        self._hist_tree = ttk.Treeview(tab, columns=cols, show="headings", height=16)
        for col in cols:
            self._hist_tree.heading(col, text=col.replace("_", " ").title())
            self._hist_tree.column(col, width=120, anchor=tk.W)
        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL,
                                  command=self._hist_tree.yview)
        self._hist_tree.configure(yscrollcommand=scrollbar.set)
        self._hist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect_backend(self) -> None:
        url = self._backend_url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Backend URL is required.")
            return
        self._client = BackendClient(url)
        try:
            self._client.list_devices()
            self._status_var.set("✓ Connected")
            self._start_btn.config(state="normal")
            self._log("Connected to backend: " + url)
            self._refresh_ports()
            self._refresh_firmwares()
        except Exception as e:
            self._status_var.set("✗ Connection failed")
            self._log(f"Backend connection error: {e}")
            messagebox.showerror("Connection Error", str(e))

    def _refresh_ports(self) -> None:
        try:
            self._detected_ports = list_ports()
        except RuntimeError as e:
            self._log(str(e))
            return
        values = [f"{d.port} ({d.board_model})" for d in self._detected_ports]
        self._port_combo["values"] = values
        if values:
            self._port_combo.current(0)
            self._on_port_selected()
        self._log(f"Detected {len(self._detected_ports)} device(s).")

    def _on_port_selected(self, *_) -> None:
        idx = self._port_combo.current()
        if idx >= 0 and idx < len(self._detected_ports):
            dev = self._detected_ports[idx]
            self._board_var.set(dev.board_model)
            if not self._device_id_var.get():
                self._device_id_var.set(f"{dev.board_model}-{dev.port.replace('/', '_')}")

    def _refresh_firmwares(self) -> None:
        if self._client is None:
            return
        try:
            self._firmwares = self._client.list_firmwares()
        except Exception as e:
            self._log(f"Failed to fetch firmwares: {e}")
            return
        values = [
            f"{fw['version']} – {fw['boardModel']} [{fw.get('releaseChannel', '')}]  id:{fw['id']}"
            for fw in self._firmwares
        ]
        self._firmware_combo["values"] = values
        if values:
            self._firmware_combo.current(0)
        self._log(f"Loaded {len(self._firmwares)} firmware(s).")

    def _start_provisioning(self) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return

        port_idx = self._port_combo.current()
        fw_idx = self._firmware_combo.current()
        device_id = self._device_id_var.get().strip()
        operator = self._operator_var.get().strip()
        site = self._site_var.get().strip()

        if port_idx < 0:
            messagebox.showerror("Error", "No port selected.")
            return
        if fw_idx < 0:
            messagebox.showerror("Error", "No firmware selected.")
            return
        if not device_id:
            messagebox.showerror("Error", "Device ID is required.")
            return
        if not operator:
            messagebox.showerror("Error", "Operator name is required.")
            return

        detected = self._detected_ports[port_idx]
        firmware = self._firmwares[fw_idx]

        self._start_btn.config(state="disabled")
        self._progress.start(10)
        self._log("─" * 50)
        self._log(f"Starting provisioning for device: {device_id}")

        def _run() -> None:
            logs: list[str] = []
            config_hash: Optional[str] = None
            job_id: Optional[str] = None
            success = False

            try:
                # 1. Register device
                self._log("→ Registering device with backend…")
                device_resp = self._client.register_device(
                    device_id=device_id,
                    model=detected.board_model,
                    site=site or None,
                )
                device_db_id = device_resp["id"]
                logs.append(f"Device registered: {device_db_id}")
                self._log(f"  Device DB ID: {device_db_id}")

                # 2. Start provisioning job
                self._log("→ Creating provisioning job…")
                job_resp = self._client.start_job(
                    device_id=device_id,
                    firmware_id=firmware["id"],
                    operator=operator,
                    station_hostname=socket.gethostname(),
                )
                job_id = job_resp["id"]
                logs.append(f"Job created: {job_id}")
                self._log(f"  Job ID: {job_id}")

                # 3. Fetch config
                self._log("→ Fetching device configuration…")
                config_data = self._client.get_device_config(device_db_id)
                config = DeviceConfig(
                    device_id=config_data.get("deviceId", device_id),
                    wifi_ssid=config_data.get("wifiSsid", ""),
                    wifi_password=config_data.get("wifiPassword", ""),
                    server_endpoint=config_data.get("serverEndpoint", ""),
                )
                logs.append("Config fetched from backend.")

                # 4. Download firmware
                self._log("→ Downloading firmware artifact…")
                suffix = ".bin" if detected.board_model == "ESP32" else ".hex"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    self._client.download_firmware(firmware["id"], tmp_path)
                    logs.append(f"Firmware downloaded to {tmp_path}")
                    self._log(f"  Firmware saved to: {tmp_path}")

                    # 5. Flash firmware
                    self._log("→ Flashing firmware…")
                    flash_result = flash_firmware(
                        port=detected.port,
                        fqbn=detected.fqbn,
                        firmware_path=tmp_path,
                        expected_sha256=firmware.get("sha256Hash"),
                    )
                    logs.append(flash_result.logs)
                    if not flash_result.success:
                        raise RuntimeError(f"Flash failed:\n{flash_result.logs}")
                    self._log("  Flash successful.")

                    # 6. Inject config
                    self._log("→ Injecting configuration…")
                    config_hash = inject_config(detected.port, config)
                    logs.append(f"Config injected. Hash: {config_hash}")
                    self._log(f"  Config injected. SHA-256: {config_hash}")

                    success = True

                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            except Exception as exc:
                logs.append(f"ERROR: {exc}")
                self._log(f"✗ Error: {exc}")

            finally:
                # 7. Report result to backend
                if job_id:
                    try:
                        self._client.report_job(
                            job_id=job_id,
                            result="SUCCESS" if success else "FAILED",
                            logs="\n".join(logs),
                            config_hash=config_hash,
                        )
                    except Exception as e:
                        self._log(f"  Warning: failed to report job: {e}")

                self.after(0, self._provisioning_done, success)

        threading.Thread(target=_run, daemon=True).start()

    def _provisioning_done(self, success: bool) -> None:
        self._progress.stop()
        self._start_btn.config(state="normal")
        if success:
            self._log("✓ Provisioning completed successfully.")
            messagebox.showinfo("Success", "Device provisioned successfully!")
        else:
            self._log("✗ Provisioning failed. Check the log above.")
            messagebox.showerror("Failed", "Provisioning failed. See log for details.")

    def _refresh_history(self) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        try:
            jobs = self._client.list_jobs()
        except Exception as e:
            self._log(f"Failed to load history: {e}")
            return

        for row in self._hist_tree.get_children():
            self._hist_tree.delete(row)

        for job in jobs:
            device_id = (job.get("device") or {}).get("deviceId", "")
            fw_version = (job.get("firmware") or {}).get("version", "")
            self._hist_tree.insert("", tk.END, values=(
                job.get("id", "")[:8] + "…",
                device_id,
                fw_version,
                job.get("operator", ""),
                job.get("result", ""),
                (job.get("startedAt") or "")[:19],
            ))

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _log(self, message: str) -> None:
        """Append *message* to the log area (thread-safe)."""
        def _append() -> None:
            self._log_area.config(state="normal")
            self._log_area.insert(tk.END, message + "\n")
            self._log_area.see(tk.END)
            self._log_area.config(state="disabled")
        self.after(0, _append)
