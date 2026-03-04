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
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
from typing import Optional
from urllib.parse import urlparse

import requests

from station.arduino_cli_installer import auto_install_arduino_cli, is_arduino_cli_installed
from station.auth_manager import AuthManager
from station.audit_logger import AuditLogger
from station.backend_client import BackendClient
from station.config_injector import DeviceConfig, inject_config
from station.config_manager import ConfigManager
from station.device_communicator import DeviceCommunicator
from station.device_detector import DetectedDevice, list_ports
from station.flasher import flash_firmware


class ProvisioningApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Edubind Provisioning Station")
        self.geometry("900x600")
        self.resizable(True, True)

        # Initialize configuration management
        self.config_mgr = ConfigManager()
        self.auth_mgr = AuthManager(self.config_mgr)
        self.audit_logger = AuditLogger()
        
        self._client: Optional[BackendClient] = None
        self._detected_ports: list[DetectedDevice] = []
        self._firmwares: list[dict] = []
        self._current_job_id: Optional[str] = None

        # Check if we need to login first
        if not self.auth_mgr.is_authenticated():
            self._show_login_window()
        else:
            self._build_ui()
            self._auto_connect_backend()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _show_login_window(self) -> None:
        """Display login dialog before showing main UI."""
        login_window = tk.Toplevel(self)
        login_window.title("Edubind Login")
        login_window.geometry("350x200")
        login_window.transient(self)
        login_window.grab_set()

        ttk.Label(login_window, text="Login to Edubind Backend", font=("Helvetica", 12, "bold")).pack(pady=10)
        
        ttk.Label(login_window, text="Backend URL:").pack(anchor="w", padx=20)
        backend_url_var = tk.StringVar(value=self.config_mgr.get_backend_url())
        ttk.Entry(login_window, textvariable=backend_url_var, width=30).pack(fill=tk.X, padx=20, pady=4)

        ttk.Label(login_window, text="Username:").pack(anchor="w", padx=20, pady=(10, 0))
        username_var = tk.StringVar()
        ttk.Entry(login_window, textvariable=username_var, width=30).pack(fill=tk.X, padx=20, pady=4)

        ttk.Label(login_window, text="Password:").pack(anchor="w", padx=20)
        password_var = tk.StringVar()
        ttk.Entry(login_window, textvariable=password_var, width=30, show="*").pack(fill=tk.X, padx=20, pady=4)

        status_var = tk.StringVar(value="")
        ttk.Label(login_window, textvariable=status_var, foreground="red").pack(pady=4)

        def _on_login() -> None:
            backend_url = backend_url_var.get().strip()
            username = username_var.get().strip()
            password = password_var.get().strip()

            if not backend_url or not username or not password:
                status_var.set("All fields required.")
                return

            self.config_mgr.set_backend_url(backend_url)
            self.auth_mgr._base_url = backend_url
            
            success, message = self.auth_mgr.login(username, password)
            if success:
                login_window.destroy()
                self._build_ui()
                self._auto_connect_backend()
            else:
                status_var.set(message)

        ttk.Button(login_window, text="Login", command=_on_login).pack(pady=10)

    def _auto_connect_backend(self) -> None:
        """Automatically connect to backend with stored token."""
        try:
            url = self.config_mgr.get_backend_url()
            self._client = BackendClient(url, auth_manager=self.auth_mgr)
            # Test connection by listing devices
            devices = self._client.list_devices()
            self._status_var.set("✓ Connected")
            self._start_btn.config(state="normal")
            self._log("Connected to backend: " + url)
            
            # Refresh ports and firmwares in background to avoid blocking UI
            self.after(100, self._refresh_ports)
            self.after(200, self._refresh_firmwares)
            self.after(300, self._refresh_room_list)
            self.after(400, self._refresh_firmware_list)
            self.after(500, self._refresh_device_list)
            
            # Check if token expiring soon
            if self.auth_mgr.is_token_expiring_soon():
                remaining = self.config_mgr.get_token_expiry_remaining_seconds()
                self._log(f"⚠ Token expiring in {remaining} seconds. Login again to refresh.")
        except Exception as e:
            self._status_var.set("✗ Connection failed")
            self._log(f"Backend connection error: {e}")
            self._start_btn.config(state="disabled")

    def _build_ui(self) -> None:
        # ---- Left panel (settings) ----
        left = ttk.LabelFrame(self, text="Settings", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        ttk.Label(left, text="Backend URL:").pack(anchor="w")
        self._backend_url_var = tk.StringVar(value=self.config_mgr.get_backend_url())
        ttk.Entry(left, textvariable=self._backend_url_var, width=28).pack(fill=tk.X)

        ttk.Label(left, text="Operator:").pack(anchor="w", pady=(8, 0))
        self._operator_var = tk.StringVar(value=self.config_mgr.get_operator_name())
        ttk.Entry(left, textvariable=self._operator_var, width=28).pack(fill=tk.X)

        ttk.Label(left, text="WiFi SSID:").pack(anchor="w", pady=(8, 0))
        self._wifi_ssid_var = tk.StringVar(value=self.config_mgr.get_wifi_ssid())
        ttk.Entry(left, textvariable=self._wifi_ssid_var, width=28).pack(fill=tk.X)

        ttk.Label(left, text="WiFi Password:").pack(anchor="w", pady=(8, 0))
        self._wifi_pass_var = tk.StringVar(value=self.config_mgr.get_wifi_password())
        ttk.Entry(left, textvariable=self._wifi_pass_var, width=28, show="*").pack(fill=tk.X)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        self._connect_btn = ttk.Button(left, text="Connect to Backend",
                                       command=self._connect_backend)
        self._connect_btn.pack(fill=tk.X)

        self._status_var = tk.StringVar(value="Not connected")
        ttk.Label(left, textvariable=self._status_var,
                  wraplength=180, foreground="red").pack(anchor="w", pady=(4, 0))

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Button(left, text="Logout", command=self._logout).pack(fill=tk.X)

        # ---- Right panel (tabs) ----
        right = ttk.Frame(self, padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(right)
        notebook.pack(fill=tk.BOTH, expand=True)

        self._provision_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self._provision_tab, text="Provision")

        self._history_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self._history_tab, text="History")

        self._admin_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self._admin_tab, text="Admin")

        self._build_provision_tab()
        self._build_history_tab()
        self._build_admin_tab()

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

        # Row: Device MAC (read-only — always read from the board)
        row2 = ttk.Frame(tab)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="MAC Address:", width=14).pack(side=tk.LEFT)
        self._mac_var = tk.StringVar(value="(will be read from board)")
        self._mac_entry = ttk.Entry(row2, textvariable=self._mac_var, width=28,
                                    state="readonly")
        self._mac_entry.pack(side=tk.LEFT, padx=2)

        # Row: Room ID
        row3 = ttk.Frame(tab)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Room ID:", width=14).pack(side=tk.LEFT)
        self._room_var = tk.StringVar(value="1")
        ttk.Entry(row3, textvariable=self._room_var, width=28).pack(side=tk.LEFT)

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

    def _build_admin_tab(self) -> None:
        tab = self._admin_tab
        
        # Room Management
        room_frame = ttk.LabelFrame(tab, text="Room Management", padding=8)
        room_frame.pack(fill=tk.X, padx=4, pady=4)
        
        row_room = ttk.Frame(room_frame)
        row_room.pack(fill=tk.X, pady=2)
        ttk.Label(row_room, text="Room Name:").pack(side=tk.LEFT, padx=4)
        self._room_name_var = tk.StringVar()
        ttk.Entry(row_room, textvariable=self._room_name_var, width=25).pack(side=tk.LEFT, padx=4)
        ttk.Button(row_room, text="Create Room", command=self._create_room).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(room_frame, text="Rooms:").pack(anchor="w", padx=4)
        self._rooms_tree = ttk.Treeview(room_frame, columns=("id", "name", "status"), show="headings", height=5)
        self._rooms_tree.heading("id", text="ID")
        self._rooms_tree.heading("name", text="Name")
        self._rooms_tree.heading("status", text="Status")
        self._rooms_tree.column("id", width=40)
        self._rooms_tree.column("name", width=150)
        self._rooms_tree.column("status", width=80)
        room_scrollbar = ttk.Scrollbar(room_frame, orient=tk.VERTICAL, command=self._rooms_tree.yview)
        self._rooms_tree.configure(yscrollcommand=room_scrollbar.set)
        self._rooms_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=2)
        room_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Button(room_frame, text="Delete Selected", command=self._delete_room).pack(pady=2)
        
        # Firmware Management
        fw_frame = ttk.LabelFrame(tab, text="Firmware Management", padding=8)
        fw_frame.pack(fill=tk.X, padx=4, pady=4)
        
        row_fw = ttk.Frame(fw_frame)
        row_fw.pack(fill=tk.X, pady=2)
        ttk.Button(row_fw, text="Upload Firmware", command=self._upload_firmware_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(row_fw, text="Refresh List", command=self._refresh_firmware_list).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(fw_frame, text="Available Firmwares:").pack(anchor="w", padx=4)
        self._fw_tree = ttk.Treeview(fw_frame, columns=("version", "filename", "size", "uploaded"), show="headings", height=5)
        self._fw_tree.heading("version", text="Version")
        self._fw_tree.heading("filename", text="Filename")
        self._fw_tree.heading("size", text="Size (bytes)")
        self._fw_tree.heading("uploaded", text="Uploaded")
        self._fw_tree.column("version", width=80)
        self._fw_tree.column("filename", width=120)
        self._fw_tree.column("size", width=80)
        self._fw_tree.column("uploaded", width=100)
        fw_scrollbar = ttk.Scrollbar(fw_frame, orient=tk.VERTICAL, command=self._fw_tree.yview)
        self._fw_tree.configure(yscrollcommand=fw_scrollbar.set)
        self._fw_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=2)
        fw_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Button(fw_frame, text="Delete Selected", command=self._delete_firmware).pack(pady=2)
        
        # Device Management
        dev_frame = ttk.LabelFrame(tab, text="Device Management", padding=8)
        dev_frame.pack(fill=tk.X, padx=4, pady=4)
        
        ttk.Button(dev_frame, text="Refresh Devices", command=self._refresh_device_list).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(dev_frame, text="Connected Devices:").pack(anchor="w", padx=4)
        self._dev_tree = ttk.Treeview(dev_frame, columns=("id", "mac", "room", "status"), show="headings", height=5)
        self._dev_tree.heading("id", text="ID")
        self._dev_tree.heading("mac", text="MAC Address")
        self._dev_tree.heading("room", text="Room")
        self._dev_tree.heading("status", text="Status")
        self._dev_tree.column("id", width=60)
        self._dev_tree.column("mac", width=150)
        self._dev_tree.column("room", width=60)
        self._dev_tree.column("status", width=80)
        dev_scrollbar = ttk.Scrollbar(dev_frame, orient=tk.VERTICAL, command=self._dev_tree.yview)
        self._dev_tree.configure(yscrollcommand=dev_scrollbar.set)
        self._dev_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=2)
        dev_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Button(dev_frame, text="Delete Selected", command=self._delete_device).pack(pady=2)

        # OTA Management
        ota_frame = ttk.LabelFrame(tab, text="OTA Updates", padding=8)
        ota_frame.pack(fill=tk.X, padx=4, pady=4)
        
        row_ota = ttk.Frame(ota_frame)
        row_ota.pack(fill=tk.X, pady=2)
        ttk.Button(row_ota, text="Refresh Devices", command=self._refresh_ota_device_list).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(row_ota, text="Firmware Version:").pack(side=tk.LEFT, padx=4)
        self._ota_fw_var = tk.StringVar()
        fw_combo = ttk.Combobox(row_ota, textvariable=self._ota_fw_var, state="readonly", width=20)
        fw_combo.pack(side=tk.LEFT, padx=2)
        self._ota_fw_combo = fw_combo
        
        ttk.Button(row_ota, text="Update Selected", command=self._trigger_ota_update).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(ota_frame, text="Devices for OTA Update:").pack(anchor="w", padx=4)
        self._ota_dev_tree = ttk.Treeview(ota_frame, columns=("id", "mac", "current_version"), show="headings", height=5)
        self._ota_dev_tree.heading("id", text="Device ID")
        self._ota_dev_tree.heading("mac", text="MAC Address")
        self._ota_dev_tree.heading("current_version", text="Current Version")
        self._ota_dev_tree.column("id", width=80)
        self._ota_dev_tree.column("mac", width=150)
        self._ota_dev_tree.column("current_version", width=100)
        ota_scrollbar = ttk.Scrollbar(ota_frame, orient=tk.VERTICAL, command=self._ota_dev_tree.yview)
        self._ota_dev_tree.configure(yscrollcommand=ota_scrollbar.set)
        self._ota_dev_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=2)
        ota_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect_backend(self) -> None:
        url = self._backend_url_var.get().strip()
        operator = self._operator_var.get().strip()
        
        if not url:
            messagebox.showerror("Error", "Backend URL is required.")
            return
        if not operator:
            messagebox.showerror("Error", "Operator name is required.")
            return

        # Save settings
        self.config_mgr.set_backend_url(url)
        self.config_mgr.set_operator_name(operator)

        self._client = BackendClient(url, auth_manager=self.auth_mgr)
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

    def _logout(self) -> None:
        """Logout current user and return to login screen."""
        self.auth_mgr.logout()
        messagebox.showinfo("Logout", "You have been logged out.")
        self.destroy()


    def _refresh_ports(self) -> None:
        try:
            self._detected_ports = list_ports()
            self._log(f"Port detection successful. Found {len(self._detected_ports)} device(s).")
        except RuntimeError as e:
            self._log(f"Port detection error: {e}")
            self._detected_ports = []
            messagebox.showwarning("Device Detection", f"Failed to detect devices:\n{e}")
            return
        except Exception as e:
            self._log(f"Unexpected error during port detection: {e}")
            self._detected_ports = []
            return
        
        values = [f"{d.port} ({d.board_model})" for d in self._detected_ports]
        self._port_combo["values"] = values
        if values:
            self._port_combo.current(0)
            self._on_port_selected()
        else:
            self._board_var.set("—")
            self._log("No devices detected. Check USB connections and drivers.")

    def _on_port_selected(self, *_) -> None:
        idx = self._port_combo.current()
        if idx >= 0 and idx < len(self._detected_ports):
            dev = self._detected_ports[idx]
            self._board_var.set(dev.board_model)
            # We don't auto-fill MAC since it needs to be known/scanned by operator

    def _read_mac_from_device(self) -> None:
        """Read MAC address from the selected serial device."""
        idx = self._port_combo.current()
        if idx < 0 or idx >= len(self._detected_ports):
            messagebox.showerror("Error", "Please select a port first.")
            return
        
        port = self._detected_ports[idx].port
        board_model = self._detected_ports[idx].board_model
        fqbn = self._detected_ports[idx].fqbn

        self._show_busy_popup("Reading MAC address from device…")
        
        def _run() -> None:
            try:
                with DeviceCommunicator(port) as comm:
                    mac = comm.get_mac_address()
                    if mac:
                        self.after(0, self._hide_busy_popup)
                        self.after(0, lambda m=mac: self._mac_var.set(m))
                        self.after(0, lambda m=mac: self._log(f"✓ MAC address read from device: {m}"))
                    else:
                        self.after(0, self._hide_busy_popup)
                        self.after(0, lambda: self._handle_no_mac_response(port, board_model, fqbn))
            except Exception as exc:
                error_msg = str(exc)
                self.after(0, self._hide_busy_popup)
                self.after(0, lambda msg=error_msg: self._handle_mac_read_error(msg, port, board_model, fqbn))
        
        threading.Thread(target=_run, daemon=True).start()

    def _handle_no_mac_response(self, port: str, board_model: str, fqbn: str) -> None:
        """Handle case when device doesn't respond with MAC address."""
        result = messagebox.askyesnocancel(
            "No MAC Response",
            f"Could not read MAC address from {port}.\n"
            f"Device may not support serial communication or is in bootloader mode.\n\n"
            f"Would you like to upload a MAC reporter sketch?\n"
            f"(This will flash {board_model})\n\n"
            f"Yes: Upload MAC reporter\n"
            f"No: Enter MAC manually\n"
            f"Cancel: Do nothing"
        )
        
        if result is True:
            self._upload_mac_reporter(port, board_model, fqbn)
        elif result is False:
            self._log("Please enter MAC address manually.")

    def _handle_mac_read_error(self, error_msg: str, port: str, board_model: str, fqbn: str) -> None:
        """Handle errors when reading MAC address."""
        result = messagebox.askyesnocancel(
            "Read Error",
            f"Failed to read from device:\n{error_msg}\n\n"
            f"Would you like to upload a MAC reporter sketch?\n"
            f"(This will flash {board_model})\n\n"
            f"Yes: Upload MAC reporter\n"
            f"No: Try again\n"
            f"Cancel: Do nothing"
        )
        
        if result is True:
            self._upload_mac_reporter(port, board_model, fqbn)
        elif result is False:
            self._log("Ready to try reading MAC again.")

    def _upload_mac_reporter(self, port: str, board_model: str, fqbn: str) -> None:
        """Upload MAC reporter sketch to device."""
        # Get the path to mac_reporter sketch directory (absolute path)
        sketch_dir = os.path.dirname(os.path.abspath(__file__))
        sketch_dir = os.path.dirname(sketch_dir)  # Go up to station/
        sketch_dir = os.path.join(sketch_dir, "src", "mac_reporter")  # station/src/mac_reporter/
        sketch_dir = os.path.abspath(sketch_dir)  # Ensure absolute path
        
        if not os.path.exists(sketch_dir):
            messagebox.showerror("Error", f"MAC reporter sketch directory not found at:\n{sketch_dir}")
            return
        
        self._log(f"→ Uploading MAC reporter to {board_model} on {port}...")
        self._log(f"  Sketch directory: {sketch_dir}")
        self._start_btn.config(state="disabled")
        
        def _run() -> None:
            try:
                # Wait for serial port to be fully released from previous operations
                self.after(0, lambda: self._log("→ Waiting for port to be released..."))
                import time
                time.sleep(1.5)
                
                # Check if arduino-cli is installed, auto-install if not
                if not is_arduino_cli_installed():
                    self.after(0, lambda: self._log("→ arduino-cli not found. Auto-installing..."))
                    success, message = auto_install_arduino_cli()
                    if not success:
                        self.after(0, lambda msg=message: messagebox.showerror(
                            "Installation Failed",
                            f"Could not install arduino-cli:\n{msg}\n\n"
                            "Please install manually from:\nhttps://arduino.github.io/arduino-cli/"
                        ))
                        self.after(0, lambda: self._log(f"✗ arduino-cli installation failed"))
                        return
                    self.after(0, lambda msg=message: self._log(f"✓ {msg}"))
                
                # First, compile the sketch to ensure binary is available
                self.after(0, lambda: self._log("→ Compiling sketch..."))
                compile_result = subprocess.run(
                    [
                        "arduino-cli", "compile",
                        "--fqbn", fqbn,
                        sketch_dir
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if compile_result.returncode != 0:
                    error_output = compile_result.stdout + compile_result.stderr
                    self.after(0, lambda: messagebox.showerror(
                        "Compile Failed",
                        f"Failed to compile MAC reporter:\n{error_output}"
                    ))
                    self.after(0, lambda: self._log(f"✗ Compile failed: {error_output}"))
                    return
                
                self.after(0, lambda: self._log("✓ Sketch compiled. Uploading..."))
                import time
                
                # Try to reset/release the serial port before upload
                # Arduino R4 WiFi needs a toggle to 1200bps to enter bootloader
                if "R4" in board_model:
                    self.after(0, lambda: self._log("→ Resetting Arduino R4 into bootloader mode (1200bps)..."))
                    try:
                        import serial
                        port_obj = serial.Serial()
                        port_obj.port = port
                        port_obj.baudrate = 1200
                        port_obj.open()
                        port_obj.close()
                        # Allow more time for the OS to re-enumerate the device in bootloader mode
                        time.sleep(2.5) 
                    except Exception as e:
                        self.after(0, lambda msg=str(e): self._log(f"  (Reset note: {msg})"))
                else:
                    try:
                        import serial
                        port_obj = serial.Serial()
                        port_obj.port = port
                        port_obj.baudrate = 1200
                        port_obj.timeout = 0.1
                        port_obj.open()
                        time.sleep(0.2)
                        port_obj.close()
                        time.sleep(0.5)
                    except Exception:
                        pass  # Port reset is optional
                
                def _run_upload(upload_port: str) -> subprocess.CompletedProcess[str]:
                    return subprocess.run(
                        [
                            "arduino-cli", "upload",
                            "--port", upload_port,
                            "--fqbn", fqbn,
                            sketch_dir
                        ],
                        capture_output=True,
                        text=True,
                        timeout=120
                    )

                def _discover_upload_ports() -> list[str]:
                    candidates: list[str] = []
                    port_token = port.rsplit(".", 1)[-1] if "." in port else port

                    def _add_candidate(candidate: str) -> None:
                        if candidate and candidate not in candidates:
                            candidates.append(candidate)

                    _add_candidate(port)
                    if port.startswith("/dev/cu."):
                        _add_candidate(port.replace("/dev/cu.", "/dev/tty.", 1))
                    elif port.startswith("/dev/tty."):
                        _add_candidate(port.replace("/dev/tty.", "/dev/cu.", 1))

                    # Add ports from arduino-cli board list, restricted to matching fqbn
                    # and/or matching hardware token, to avoid unrelated Bluetooth ports.
                    try:
                        import json
                        board_list = subprocess.run(
                            ["arduino-cli", "board", "list", "--format", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if board_list.returncode == 0 and board_list.stdout.strip():
                            payload = json.loads(board_list.stdout)
                            detected_ports = payload.get("detected_ports", [])

                            for entry in detected_ports:
                                board_matches = entry.get("matching_boards", [])
                                port_data = entry.get("port", {})
                                address = port_data.get("address", "")
                                properties = port_data.get("properties", {})
                                serial_number = properties.get("serialNumber", "")
                                hardware_id = port_data.get("hardware_id", "")
                                is_usb_serial = address.startswith("/dev/cu.usb") or address.startswith("/dev/tty.usb")
                                fqbn_match = any(match.get("fqbn") == fqbn for match in board_matches)
                                token_match = (
                                    (port_token and port_token in address)
                                    or (serial_number and serial_number in address)
                                    or (hardware_id and hardware_id in address)
                                )
                        if is_usb_serial and (fqbn_match or token_match):
                                    # Prefer /dev/cu.* on macOS for uploading to Arduino R4
                                    if address.startswith("/dev/tty."):
                                        cu_address = address.replace("/dev/tty.", "/dev/cu.", 1)
                                        _add_candidate(cu_address)
                                    _add_candidate(address)
                    except Exception:
                        pass

                    # Add redetected supported-device ports as fallback (already filtered by VID/PID).
                    try:
                        for device in list_ports():
                            if device.board_model == board_model:
                                _add_candidate(device.port)
                    except Exception:
                        pass

                    return candidates

                result: Optional[subprocess.CompletedProcess[str]] = None
                error_output = ""
                tried_ports: set[str] = set()

                # Try multiple times because bootloader reset may move the serial port for a short window.
                for attempt in range(1, 7):
                    ports_to_try = [p for p in _discover_upload_ports() if p not in tried_ports]
                    if not ports_to_try:
                        time.sleep(1.0)
                        continue

                    if attempt > 1:
                        self.after(0, lambda n=attempt: self._log(f"→ Upload retry {n}/6: probing current serial ports..."))

                    for candidate_port in ports_to_try:
                        tried_ports.add(candidate_port)
                        if candidate_port != port or attempt > 1:
                            self.after(0, lambda p=candidate_port: self._log(f"→ Trying upload on {p}..."))

                        result = _run_upload(candidate_port)
                        error_output = result.stdout + result.stderr
                        if result.returncode == 0:
                            self.after(0, lambda p=candidate_port: self._log(f"✓ Uploaded successfully on {p}!"))
                            break
                        else:
                            # If it failed, log it so the user knows we tried
                            short_err = error_output.splitlines()[-1] if error_output.strip() else "Error"
                            self.after(0, lambda p=candidate_port, e=short_err: self._log(f"  (Failed on {p}: {e})"))

                    if result and result.returncode == 0:
                        break

                    time.sleep(1.0)

                if result is None:
                    raise RuntimeError("Upload did not run: no candidate serial ports were found")
                
                if result.returncode == 0:
                    self.after(0, lambda: self._log("✓ MAC reporter uploaded successfully!"))
                    self.after(0, self._prompt_reset_then_read_mac)
                else:
                    self.after(0, lambda: messagebox.showerror(
                        "Upload Failed",
                        f"Failed to upload MAC reporter:\n{error_output}"
                    ))
                    self.after(0, lambda: self._log(f"✗ Upload failed: {error_output}"))
            except subprocess.TimeoutExpired:
                self.after(0, lambda: messagebox.showerror(
                    "Timeout",
                    "Upload took too long (>120s). Device may be disconnected."
                ))
            except Exception as exc:
                error_msg = str(exc)
                self.after(0, lambda msg=error_msg: messagebox.showerror("Error", f"Upload failed:\n{msg}"))
            finally:
                self.after(0, lambda: self._start_btn.config(state="normal"))
        
        threading.Thread(target=_run, daemon=True).start()

    def _refresh_firmwares(self) -> None:
        if self._client is None:
            self._log("Client not initialized. Cannot refresh firmwares.")
            return
        try:
            self._firmwares = self._client.list_firmwares()
        except Exception as e:
            self._log(f"Failed to fetch firmwares: {e}")
            return
        values = [
            f"{fw['version']} ({fw['filename']}) – {fw['sizeBytes']} bytes"
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
        room_id_str = self._room_var.get().strip()
        operator = self._operator_var.get().strip()
        
        wifi_ssid = self._wifi_ssid_var.get().strip()
        wifi_pass = self._wifi_pass_var.get().strip()

        if port_idx < 0:
            messagebox.showerror("Error", "No port selected.")
            return
        if fw_idx < 0:
            messagebox.showerror("Error", "No firmware selected.")
            return
        if not room_id_str.isdigit():
            messagebox.showerror("Error", "Room ID must be a number.")
            return
        if not operator:
            messagebox.showerror("Error", "Operator name is required.")
            return
        if not wifi_ssid:
            messagebox.showerror("Error", "WiFi SSID is required in Settings.")
            return

        detected = self._detected_ports[port_idx]
        firmware = self._firmwares[fw_idx]

        self.config_mgr.set_wifi_ssid(wifi_ssid)
        self.config_mgr.set_wifi_password(wifi_pass)

        # Prompt for OTA server endpoint
        parsed_url = urlparse(self.config_mgr.get_backend_url())
        default_ota_host = parsed_url.hostname or "192.168.1.10"
        default_ota_endpoint = f"{default_ota_host}:8080"
        
        ota_endpoint_input = simpledialog.askstring(
            "OTA Server Configuration",
            f"Enter OTA HTTP server endpoint\n(format: host:port)\n(leave empty for default: {default_ota_endpoint}):",
            initialvalue=default_ota_endpoint
        )
        
        if ota_endpoint_input is None:  # User pressed Cancel
            return
        
        ota_server_endpoint = ota_endpoint_input.strip() or default_ota_endpoint

        self._start_btn.config(state="disabled")
        self._progress.start(10)
        self._log("─" * 50)
        self._log(f"Starting provisioning in Room: {room_id_str}")
        self._log(f"OTA Server: {ota_server_endpoint}")

        import time
        start_time = time.time()

        def _run() -> None:
            logs: list[str] = []
            config_hash: Optional[str] = None
            firmware_sha256: Optional[str] = None
            mac_addr: Optional[str] = None
            success = False
            error_reason: Optional[str] = None

            try:
                # ── Step 1: Upload provisioning helper sketch ──────────────
                self._log("→ Step 1/5: Uploading provisioning helper sketch…")
                self.after(0, lambda: self._show_busy_popup(
                    "Uploading provisioning helper sketch…\nPlease wait."))
                resolved_fqbn = self._flash_helper_sketch(
                    detected.port, detected.board_model, detected.fqbn)
                if resolved_fqbn:
                    detected.fqbn = resolved_fqbn
                logs.append("Provisioning helper sketch uploaded.")
                self._log("  ✓ Helper sketch uploaded.")

                # Ask the operator to press RESET so the helper sketch starts running.
                # We use a threading.Event to block this worker thread until the
                # messagebox (running on the main thread) is dismissed.
                reset_event = threading.Event()
                def _ask_reset() -> None:
                    self._hide_busy_popup()
                    messagebox.showinfo(
                        "Press RESET on the Board",
                        "The provisioning helper sketch has been uploaded.\n\n"
                        "Please press the RESET button on the Arduino board,\n"
                        "then click OK to continue.",
                    )
                    reset_event.set()
                self.after(0, _ask_reset)
                reset_event.wait()   # blocks worker until operator clicks OK

                # Give the board time to boot into the helper sketch.
                self._log("→ Waiting for helper sketch to boot…")
                self.after(0, lambda: self._show_busy_popup(
                    "Waiting for helper sketch to boot…"))
                time.sleep(2.5)

                # ── Step 2: Read MAC address from helper sketch ────────────
                self._log("→ Step 2/5: Reading MAC address from device…")
                self.after(0, lambda: self._update_busy_message(
                    "Reading MAC address from device…"))
                mac_addr = self._read_mac_blocking(detected.port)
                if not mac_addr:
                    raise RuntimeError(
                        "Could not read MAC address from provisioning helper. "
                        "Try pressing RESET on the board and re-running.")
                self._log(f"  ✓ MAC: {mac_addr}")
                self.after(0, lambda m=mac_addr: self._mac_var.set(m))
                logs.append(f"MAC address: {mac_addr}")

                # ── Step 3: Register device with backend ───────────────────
                self._log("→ Step 3/5: Registering device with backend…")
                self.after(0, lambda: self._update_busy_message(
                    "Registering device with backend…"))
                device_db_id = None
                psk_key = None
                
                try:
                    device_resp = self._client.register_device(
                        mac_address=mac_addr,
                        room_id=int(room_id_str),
                    )
                    device_db_id = device_resp.get("id") or device_resp.get("deviceId")
                    psk_key = device_resp.get("pskKey")
                    logs.append(f"Device registered: ID={device_db_id}")
                    self._log(f"  Device registered (ID: {device_db_id})")
                except requests.HTTPError as e:
                    if e.response.status_code == 409:
                        self._log("  Device already registered. Updating…")
                        existing_device = self._client.get_device_by_mac(mac_addr)
                        if existing_device:
                            device_db_id = existing_device.get("id") or existing_device.get("deviceId")
                            if existing_device.get("roomId") != int(room_id_str):
                                self._client.update_device_room(device_db_id, int(room_id_str))
                                self._log(f"  Room updated to {room_id_str}")
                            psk_resp = self._client.get_device_psk(device_db_id)
                            psk_key = psk_resp.get("pskKey")
                            logs.append(f"Device already exists: ID={device_db_id}")
                            self._log(f"  Device ID: {device_db_id} (existing)")
                        else:
                            raise ValueError("Device not found by MAC after 409 conflict")
                    else:
                        raise

                if not psk_key:
                    raise ValueError("Backend did not return a PSK key!")
                self._log("  ✓ PSK obtained")

                # Fetch room name for board name
                board_name = ""
                try:
                    room_info = self._client.get_room(int(room_id_str))
                    board_name = room_info.get("name", "")
                    self._log(f"  Room name: {board_name}")
                except Exception as e:
                    self._log(f"  ⚠ Could not fetch room name: {e}")
                    board_name = f"Room-{room_id_str}"

                # Build configuration
                self._log("→ Creating device configuration…")
                coap_host = parsed_url.hostname or "192.168.1.10"
                coap_port = parsed_url.port or 5683

                config = DeviceConfig(
                    mac_address=mac_addr,
                    wifi_ssid=wifi_ssid,
                    wifi_password=wifi_pass,
                    server_endpoint=f"{coap_host}:{coap_port}",
                    psk_key=psk_key,
                    ota_server_endpoint=ota_server_endpoint,
                    firmware_version=firmware.get("version", "unknown"),
                    board_name=board_name,
                )

                # ── Step 4: Inject config blob via helper sketch ───────────
                self._log("→ Step 4/5: Injecting configuration (WiFi + PSK + OTA)…")
                self.after(0, lambda: self._update_busy_message(
                    "Injecting configuration into EEPROM…\nPlease wait."))
                config_hash = inject_config(
                    detected.port, config, timeout=20.0, log_fn=self._log)
                logs.append(f"Config injected. Hash: {config_hash}")
                self._log(f"  ✓ Config injected. SHA-256: {config_hash}")

                # ── Step 5: Flash production firmware ──────────────────────
                self._log("→ Step 5/5: Downloading & flashing production firmware…")
                self.after(0, lambda: self._update_busy_message(
                    "Flashing production firmware…\nPlease wait."))
                suffix = ".bin"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    self._client.download_firmware(firmware["version"], tmp_path)
                    self._log(f"  Firmware {firmware['version']} saved to: {tmp_path}")

                    flash_result = flash_firmware(
                        port=detected.port,
                        fqbn=detected.fqbn,
                        firmware_path=tmp_path,
                        expected_sha256=firmware.get("sha256Hash"),
                    )
                    logs.append(flash_result.logs)
                    if not flash_result.success:
                        raise RuntimeError(f"Flash failed:\n{flash_result.logs}")
                    self._log("  ✓ Flash successful.")

                    firmware_sha256 = flash_result.sha256
                    if firmware_sha256:
                        self._log(f"  Firmware SHA-256: {firmware_sha256}")

                    success = True
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            except Exception as exc:
                error_reason = str(exc)
                logs.append(f"ERROR: {exc}")
                self._log(f"✗ Error: {exc}")

            finally:
                # Log audit trail locally (no online job report)
                duration_sec = time.time() - start_time
                audit_info = {
                    "device_id": mac_addr or "UNKNOWN",
                    "firmware_version": firmware.get("version", "unknown"),
                    "firmware_sha256": firmware_sha256,  # NEW: SHA-256 of deployed artifact
                    "ota_server_endpoint": ota_server_endpoint,  # NEW: OTA server endpoint provisioned
                    "operator": operator,
                    "config_hash": config_hash,
                    "result": "SUCCESS" if success else "FAILED",
                    "error_reason": error_reason,
                    "duration_sec": round(duration_sec, 2),
                    "backend_url": self.config_mgr.get_backend_url(),
                    "station_hostname": socket.gethostname(),
                }
                self.audit_logger.log_job(audit_info)

                self.after(0, self._provisioning_done, success)

        threading.Thread(target=_run, daemon=True).start()

    def _provisioning_done(self, success: bool) -> None:
        self._hide_busy_popup()
        self._progress.stop()
        self._start_btn.config(state="normal")
        if success:
            self._log("✓ Provisioning completed successfully.")
            messagebox.showinfo("Success", "Device provisioned successfully!")
        else:
            self._log("✗ Provisioning failed. Check the log above.")
            messagebox.showerror("Failed", "Provisioning failed. See log for details.")

    def _refresh_history(self) -> None:
        try:
            jobs = self.audit_logger.get_recent_jobs(limit=50)
        except Exception as e:
            self._log(f"Failed to load history: {e}")
            return

        for row in self._hist_tree.get_children():
            self._hist_tree.delete(row)

        for job in jobs:
            device_id = job.get("device_id", "")
            fw_version = job.get("firmware_version", "")
            
            # Since local jobs don't have a unique 'id' in current logging, just use timestamp hash
            # or just show the result. Here I'll mock a short job id based on timestamp if missing
            job_id = job.get("id", str(hash(job.get("timestamp", "")))[-8:])

            self._hist_tree.insert("", tk.END, values=(
                job_id,
                device_id,
                fw_version,
                job.get("operator", ""),
                job.get("result", ""),
                (job.get("timestamp", "") or "")[:19].replace("T", " "),
            ))

    # ------------------------------------------------------------------ #
    # Admin Actions                                                        #
    # ------------------------------------------------------------------ #

    def _create_room(self) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        room_name = self._room_name_var.get().strip()
        if not room_name:
            messagebox.showerror("Error", "Room name is required.")
            return
        
        try:
            result = self._client.create_room(room_name)
            messagebox.showinfo("Success", f"Room created: {result.get('name')} (ID: {result.get('id')})")
            self._room_name_var.set("")
            self._refresh_room_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create room: {e}")

    def _delete_room(self) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        selection = self._rooms_tree.selection()
        if not selection:
            messagebox.showerror("Error", "Please select a room to delete.")
            return
        
        item_id = selection[0]
        values = self._rooms_tree.item(item_id, "values")
        room_id = values[0]
        room_name = values[1]
        
        if messagebox.askyesno("Confirm Delete", f"Delete room '{room_name}'?"):
            try:
                self._client.delete_room(int(room_id))
                messagebox.showinfo("Success", "Room deleted.")
                self._refresh_room_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete room: {e}")

    def _refresh_room_list(self) -> None:
        if self._client is None:
            return
        
        try:
            rooms = self._client.list_rooms()
            for row in self._rooms_tree.get_children():
                self._rooms_tree.delete(row)
            
            for room in rooms:
                status = "OCCUPIED" if room.get("currentOccupiedState") else "EMPTY"
                self._rooms_tree.insert("", tk.END, values=(
                    room.get("id"),
                    room.get("name"),
                    status
                ))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load rooms: {e}")

    def _upload_firmware_dialog(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select firmware file",
            filetypes=[("Binary files", "*.bin"), ("Hex files", "*.hex"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        version = tk.simpledialog.askstring("Firmware Version", "Enter version string (e.g. 1.0.1):")
        if not version:
            return
        
        self._upload_firmware(file_path, version)

    def _upload_firmware(self, file_path: str, version: str) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        def _run() -> None:
            try:
                result = self._client.upload_firmware(version, file_path)
                self.after(0, lambda: messagebox.showinfo("Success", f"Firmware {version} uploaded."))
                self.after(0, self._refresh_firmware_list)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Upload failed: {e}"))
        
        threading.Thread(target=_run, daemon=True).start()

    def _delete_firmware(self) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        selection = self._fw_tree.selection()
        if not selection:
            messagebox.showerror("Error", "Please select a firmware to delete.")
            return
        
        item_id = selection[0]
        values = self._fw_tree.item(item_id, "values")
        version = values[0]
        
        if messagebox.askyesno("Confirm Delete", f"Delete firmware version {version}?"):
            try:
                self._client.delete_firmware(version)
                messagebox.showinfo("Success", "Firmware deleted.")
                self._refresh_firmware_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete firmware: {e}")

    def _refresh_firmware_list(self) -> None:
        if self._client is None:
            return
        
        try:
            firmwares = self._client.list_firmwares()
            for row in self._fw_tree.get_children():
                self._fw_tree.delete(row)
            
            for fw in firmwares:
                self._fw_tree.insert("", tk.END, values=(
                    fw.get("version"),
                    fw.get("filename"),
                    fw.get("sizeBytes"),
                    fw.get("uploadedAt", "")[:10]
                ))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load firmwares: {e}")

    def _refresh_device_list(self) -> None:
        if self._client is None:
            return
        
        try:
            devices = self._client.list_devices()
            for row in self._dev_tree.get_children():
                self._dev_tree.delete(row)
            
            for device in devices:
                self._dev_tree.insert("", tk.END, values=(
                    device.get("id"),
                    device.get("macAddress"),
                    device.get("roomId"),
                    device.get("status", "UNKNOWN")
                ))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load devices: {e}")

    def _delete_device(self) -> None:
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        selection = self._dev_tree.selection()
        if not selection:
            messagebox.showerror("Error", "Please select a device to delete.")
            return
        
        item_id = selection[0]
        values = self._dev_tree.item(item_id, "values")
        device_id = values[0]
        mac_addr = values[1]
        
        if messagebox.askyesno("Confirm Delete", f"Delete device {mac_addr}?"):
            try:
                self._client.delete_device(int(device_id))
                messagebox.showinfo("Success", "Device deleted.")
                self._refresh_device_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete device: {e}")

    def _refresh_ota_device_list(self) -> None:
        """Load devices and their current firmware versions for OTA updates."""
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        def _load():
            try:
                devices = self._client.list_devices()
                for row in self._ota_dev_tree.get_children():
                    self._ota_dev_tree.delete(row)
                
                for device in devices:
                    device_id = device.get("id")
                    try:
                        version_info = self._client.get_device_version(device_id)
                        current_version = version_info.get("version", "Unknown")
                    except Exception:
                        current_version = "Unknown"
                    
                    self._ota_dev_tree.insert("", tk.END, values=(
                        device_id,
                        device.get("macAddress"),
                        current_version
                    ))
                
                # Update firmware combo
                try:
                    firmwares = self._client.list_firmwares()
                    versions = [fw.get("version") for fw in firmwares]
                    self._ota_fw_combo['values'] = versions
                    if versions:
                        self._ota_fw_var.set(versions[0])
                except Exception:
                    pass
                
                self._log("OTA device list refreshed.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load OTA devices: {e}")
        
        # Run in background thread
        threading.Thread(target=_load, daemon=True).start()

    def _trigger_ota_update(self) -> None:
        """Trigger OTA update for selected devices."""
        if self._client is None:
            messagebox.showerror("Error", "Not connected to backend.")
            return
        
        selection = self._ota_dev_tree.selection()
        if not selection:
            messagebox.showerror("Error", "Please select at least one device to update.")
            return
        
        version = self._ota_fw_var.get()
        if not version:
            messagebox.showerror("Error", "Please select a firmware version.")
            return
        
        device_ids = []
        for item_id in selection:
            values = self._ota_dev_tree.item(item_id, "values")
            device_id = int(values[0])
            device_ids.append(device_id)
        
        if messagebox.askyesno("Confirm OTA Update", 
                               f"Update {len(device_ids)} device(s) to version {version}?"):
            def _update():
                try:
                    self._log(f"Triggering OTA update for {len(device_ids)} device(s) to version {version}...")
                    result = self._client.trigger_ota_update(device_ids, version)
                    self._log(f"OTA update triggered: {result}")
                    messagebox.showinfo("Success", f"OTA update triggered for {len(device_ids)} device(s).")
                    self._refresh_ota_device_list()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to trigger OTA update: {e}")
            
            # Run in background thread
            threading.Thread(target=_update, daemon=True).start()

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

    # ------------------------------------------------------------------ #
    # Waiting popup                                                        #
    # ------------------------------------------------------------------ #

    def _show_busy_popup(self, message: str = "Please wait…") -> None:
        """Show a non-closeable modal popup with a progress bar. Main-thread only."""
        if hasattr(self, "_busy_win") and self._busy_win and self._busy_win.winfo_exists():
            # Already visible — just update the message
            if hasattr(self, "_busy_msg_var"):
                self._busy_msg_var.set(message)
            return

        self._busy_win = tk.Toplevel(self)
        self._busy_win.title("Please Wait")
        self._busy_win.resizable(False, False)
        self._busy_win.transient(self)
        self._busy_win.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent closing
        self._busy_win.attributes("-topmost", True)

        # Centre over main window
        self._busy_win.update_idletasks()
        w, h = 320, 110
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        self._busy_win.geometry(f"{w}x{h}+{x}+{y}")

        self._busy_msg_var = tk.StringVar(value=message)
        ttk.Label(
            self._busy_win,
            textvariable=self._busy_msg_var,
            wraplength=290,
            justify=tk.CENTER,
        ).pack(pady=(14, 6), padx=12)
        self._busy_pb = ttk.Progressbar(self._busy_win, mode="indeterminate", length=260)
        self._busy_pb.pack(pady=4)
        self._busy_pb.start(12)
        self._busy_win.grab_set()
        self._busy_win.update()

    def _hide_busy_popup(self) -> None:
        """Destroy the waiting popup. Main-thread only."""
        if hasattr(self, "_busy_win") and self._busy_win and self._busy_win.winfo_exists():
            try:
                self._busy_pb.stop()
                self._busy_win.grab_release()
                self._busy_win.destroy()
            except Exception:
                pass
            self._busy_win = None

    def _update_busy_message(self, message: str) -> None:
        """Update the popup message without recreating the window. Main-thread only."""
        if hasattr(self, "_busy_msg_var"):
            self._busy_msg_var.set(message)

    def _prompt_reset_then_read_mac(self) -> None:
        """Ask the operator to press Reset on the board, then trigger MAC reading."""
        messagebox.showinfo(
            "Action Required: Press RESET",
            "The firmware has been flashed successfully.\n\n"
            "Please press the RESET button on the board to start\n"
            "the new firmware, then click OK to read the MAC address.",
        )
        self._log("→ Reading MAC address from device…")
        self._read_mac_from_device()

    # ------------------------------------------------------------------ #
    # Provisioning helper methods (called from worker thread)              #
    # ------------------------------------------------------------------ #

    def _flash_helper_sketch(self, port: str, board_model: str, fqbn: str) -> str:
        """
        Compile and upload the provisioning helper sketch.

        Raises RuntimeError on failure.  Must be called from a worker thread.
        """
        import time as _time

        sketch_dir = os.path.dirname(os.path.abspath(__file__))
        sketch_dir = os.path.dirname(sketch_dir)  # Go up to station/
        sketch_dir = os.path.join(sketch_dir, "src", "mac_reporter")
        sketch_dir = os.path.abspath(sketch_dir)

        if not os.path.exists(sketch_dir):
            raise RuntimeError(
                f"Provisioning helper sketch directory not found at:\n{sketch_dir}")

        # Ensure arduino-cli is present
        if not is_arduino_cli_installed():
            self._log("  → arduino-cli not found. Auto-installing…")
            ok, msg = auto_install_arduino_cli()
            if not ok:
                raise RuntimeError(f"Could not install arduino-cli: {msg}")
            self._log(f"  ✓ {msg}")

        # If the detector reported a generic ESP, try to figure out whether
        # it's actually an ESP8266 or ESP32 by asking arduino-cli.  This
        # handles devices where the USB VID/PID doesn't distinguish the chip.
        if board_model == "GENERIC_ESP":
            try:
                from station.device_detector import detect_board_via_arduino_cli
                cli_fqbn = detect_board_via_arduino_cli(port)
                if cli_fqbn:
                    fqbn = cli_fqbn
                    if "esp8266" in cli_fqbn.lower():
                        board_model = "ESP8266"
                    elif "esp32" in cli_fqbn.lower():
                        board_model = "ESP32"
                    self._log(f"  ✓ Detected board via arduino-cli: {board_model} ({fqbn})")
            except Exception:
                pass

        # Ensure board core is installed
        # Extract package:architecture from FQBN (e.g., "esp32:esp32" from "esp32:esp32:esp32")
        fqbn_parts = fqbn.split(":")
        if len(fqbn_parts) >= 2:
            platform_id = f"{fqbn_parts[0]}:{fqbn_parts[1]}"
            self._log(f"  → Checking platform: {platform_id}…")
            try:
                # refresh the core index first so we have the latest list
                self._log("  → Updating Arduino core index…")
                subprocess.run(["arduino-cli", "core", "update-index"],
                               capture_output=True, text=True, timeout=60)

                # Check if platform is already installed
                list_result = subprocess.run(
                    ["arduino-cli", "core", "list"],
                    capture_output=True, text=True, timeout=30)
                
                if list_result.returncode == 0 and platform_id not in list_result.stdout:
                    # Platform not installed, auto-install it
                    self._log(f"  → Installing platform {platform_id}…")
                    install_result = subprocess.run(
                        ["arduino-cli", "core", "install", platform_id],
                        capture_output=True, text=True, timeout=300)
                    
                    if install_result.returncode != 0:
                        # give more helpful message if platform not found
                        stderr = install_result.stderr.lower()
                        if "not found" in stderr or "not in" in stderr:
                            # attempt automatic addition of common third‑party URLs
                            if platform_id.startswith("esp8266"):
                                self._log("  → Adding ESP8266 board URL and updating index…")
                                subprocess.run([
                                    "arduino-cli", "core", "update-index",
                                    "--additional-urls",
                                    "http://arduino.esp8266.com/stable/package_esp8266com_index.json"
                                ], capture_output=True, text=True, timeout=60)
                                # retry install once
                                retry = subprocess.run(
                                    ["arduino-cli", "core", "install", platform_id],
                                    capture_output=True, text=True, timeout=300)
                                if retry.returncode == 0:
                                    self._log(f"  ✓ Platform {platform_id} installed on retry.")
                                    install_result = retry
                                    stderr = retry.stderr.lower()
                                # fall through to error handling if retry also failed
                            if "not found" in stderr or "not in" in stderr:
                                raise RuntimeError(
                                    f"Platform {platform_id} not found. "
                                    "Try running 'arduino-cli core update-index' or "
                                    "ensure the appropriate additional URLs are configured.\n"
                                    f"{install_result.stdout + install_result.stderr}")
                        else:
                            raise RuntimeError(
                                f"Failed to install platform {platform_id}:\n{install_result.stdout + install_result.stderr}")
                    self._log(f"  ✓ Platform {platform_id} installed.")
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Timeout while installing platform {platform_id}")
            except Exception as e:
                self._log(f"  ⚠ Warning: Could not auto-install platform: {e}")

        # Compile
        self._log("  → Compiling helper sketch…")
        compile_result = subprocess.run(
            ["arduino-cli", "compile", "--fqbn", fqbn, sketch_dir],
            capture_output=True, text=True, timeout=120)
        if compile_result.returncode != 0:
            raise RuntimeError(
                f"Compile failed:\n{compile_result.stdout + compile_result.stderr}")

        # 1200-bps touch to enter bootloader (Arduino R4 WiFi)
        self._log("  → Resetting board into bootloader mode…")
        try:
            import serial as _serial
            _p = _serial.Serial(port, baudrate=1200, dsrdtr=True, rtscts=True)
            _time.sleep(0.1)
            _p.close()
            _time.sleep(3.5) # Increased from 2.5
        except Exception:
            pass

        def _attempt_upload(fqbn_to_use: str) -> tuple[bool, str]:
            """Try uploading the sketch with *fqbn_to_use*; return (success, output)."""
            tried_ports: set[str] = set()
            last_err = ""
            for attempt in range(1, 7):
                candidates = [port]
                if port.startswith("/dev/cu."):
                    candidates.append(port.replace("/dev/cu.", "/dev/tty.", 1))
                # Also re-scan for ports with same board_model (could shift)
                try:
                    for dev in list_ports():
                        if dev.board_model == board_model and dev.port not in candidates:
                            candidates.append(dev.port)
                except Exception:
                    pass

                for cand in candidates:
                    if cand in tried_ports:
                        continue
                    tried_ports.add(cand)
                    result = subprocess.run(
                        ["arduino-cli", "upload", "--port", cand, "--fqbn", fqbn_to_use, sketch_dir],
                        capture_output=True, text=True, timeout=120)
                    last_err = result.stdout + result.stderr
                    if result.returncode == 0:
                        return True, last_err
                _time.sleep(1.0)
            return False, last_err

        self._log("  → Uploading…")
        success, upload_err = _attempt_upload(fqbn)
        if success:
            return fqbn

        # if the upload failed and the error suggests wrong chip, try esp8266
        if "ESP8266" in upload_err and "ESP32" in upload_err or "wrong chip" in upload_err.lower():
            self._log("  ⚠ Detected chip mismatch, retrying with ESP8266 core…")
            alt_fqbn = "esp8266:esp8266:generic"
            try:
                # ensure the alternate core is installed
                pf = alt_fqbn.split(":")
                if len(pf) >= 2:
                    alt_platform = f"{pf[0]}:{pf[1]}"
                    self._log(f"  → Checking platform: {alt_platform}…")
                    esp8266_url = "http://arduino.esp8266.com/stable/package_esp8266com_index.json"
                    self._log("  → Updating Arduino core index for ESP8266…")
                    subprocess.run(
                        ["arduino-cli", "core", "update-index", "--additional-urls", esp8266_url],
                        capture_output=True, text=True, timeout=60)
                    list_result = subprocess.run(
                        ["arduino-cli", "core", "list", "--additional-urls", esp8266_url],
                        capture_output=True, text=True, timeout=30)
                    if alt_platform not in list_result.stdout:
                        self._log(f"  → Installing platform {alt_platform}…")
                        inst_res = subprocess.run(
                            ["arduino-cli", "core", "install", alt_platform, "--additional-urls", esp8266_url],
                            capture_output=True, text=True, timeout=300)
                        if inst_res.returncode != 0:
                            self._log(f"  ⚠ Failed to install platform {alt_platform}, error:\n{inst_res.stdout+inst_res.stderr}")
                self._log("  → Re-compiling helper sketch for ESP8266…")
                compile_result = subprocess.run(
                    ["arduino-cli", "compile", "--fqbn", alt_fqbn, sketch_dir],
                    capture_output=True, text=True, timeout=120)
                if compile_result.returncode != 0:
                    raise RuntimeError(
                        f"Compile failed (ESP8266):\n{compile_result.stdout + compile_result.stderr}")

                # try upload again
                success2, upload_err2 = _attempt_upload(alt_fqbn)
                if success2:
                    return alt_fqbn
                upload_err = upload_err2
            except Exception as e:
                upload_err += f"\n[retry error] {e}"

        raise RuntimeError(f"Upload of helper sketch failed after retries:\n{upload_err}")

    @staticmethod
    def _read_mac_blocking(port: str, timeout: float = 10.0) -> Optional[str]:
        """
        Open *port*, send 'MAC' command, and return the MAC address string.

        Blocking — call from a worker thread only.
        """
        import re
        import time as _time
        try:
            import serial as _serial
        except ImportError:
            return None

        mac_pattern = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")

        with _serial.Serial(port, 115200, timeout=0.5) as ser:
            # Give device a moment, then drain boot output
            _time.sleep(0.5)
            ser.reset_input_buffer()

            deadline = _time.monotonic() + timeout
            while _time.monotonic() < deadline:
                ser.write(b"MAC\n")
                ser.flush()
                _time.sleep(0.4)
                raw = ser.read(ser.in_waiting or 64)
                if raw:
                    text = raw.decode("utf-8", errors="ignore")
                    m = mac_pattern.search(text)
                    if m:
                        return m.group(1).upper()
        return None
