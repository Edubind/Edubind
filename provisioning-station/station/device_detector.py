"""
device_detector.py – Detect and identify Arduino boards connected via USB/serial.

Supported boards:
    - Arduino R4 WiFi  (USB VID:PID 0x2341:0x0069 or 0x2341:0x0268)
    - ESP32            (Silicon Labs CP2102/CP2104: 0x10C4:0xEA60, or CH340: 0x1A86:0x7523)
"""

from __future__ import annotations

import subprocess
import json
from dataclasses import dataclass
from typing import Optional

try:
    import serial.tools.list_ports as _list_ports
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

# Known USB VID:PID for supported boards
_BOARD_IDENTIFIERS: dict[tuple[int, int], str] = {
    (0x2341, 0x0069): "ARDUINO_R4_WIFI",
    (0x2341, 0x0268): "ARDUINO_R4_WIFI",
    (0x2341, 0x1002): "ARDUINO_R4_WIFI",   # CMSIS-DAP mode
    (0x10C4, 0xEA60): "GENERIC_ESP",   # CP2102/CP2104 (could be ESP32 or ESP8266)
    (0x1A86, 0x7523): "GENERIC_ESP",   # CH340 (could be ESP32 or ESP8266)
    (0x1A86, 0x55D4): "GENERIC_ESP",   # CH9102 (could be ESP32 or ESP8266)
}

# arduino-cli FQBN mapping for each board model
BOARD_FQBN: dict[str, str] = {
    "ARDUINO_R4_WIFI": "arduino:renesas_uno:unor4wifi",
    "ESP32": "esp32:esp32:esp32",
    "ESP8266": "esp8266:esp8266:generic",
    "GENERIC_ESP": "esp32:esp32:esp32",  # Default; will be overridden by arduino-cli detection
}


@dataclass
class DetectedDevice:
    port: str
    board_model: str        # e.g. "ARDUINO_R4_WIFI"
    fqbn: str               # Full Qualified Board Name for arduino-cli
    description: str        # Human-readable port description
    vid: Optional[int] = None
    pid: Optional[int] = None


def list_ports() -> list[DetectedDevice]:
    """Return a list of connected Arduino/ESP32/ESP8266 devices."""
    if not _SERIAL_AVAILABLE:
        raise RuntimeError(
            "pyserial is not installed. Run: pip install pyserial"
        )

    detected: list[DetectedDevice] = []
    for port_info in _list_ports.comports():
        vid = port_info.vid
        pid = port_info.pid
        if vid is None or pid is None:
            continue
        board_model = _BOARD_IDENTIFIERS.get((vid, pid))
        if board_model is None:
            continue
        
        fqbn = BOARD_FQBN.get(board_model, "")
        
        # For generic ESP boards (CH340/CP2102), use arduino-cli to detect actual chip
        if board_model == "GENERIC_ESP":
            cli_fqbn = detect_board_via_arduino_cli(port_info.device)
            if cli_fqbn:
                fqbn = cli_fqbn
                # Extract board model from FQBN (e.g., "esp8266:esp8266:generic" -> "ESP8266")
                if "esp8266" in cli_fqbn.lower():
                    board_model = "ESP8266"
                elif "esp32" in cli_fqbn.lower():
                    board_model = "ESP32"
        
        detected.append(DetectedDevice(
            port=port_info.device,
            board_model=board_model,
            fqbn=fqbn,
            description=port_info.description or "",
            vid=vid,
            pid=pid,
        ))
    return detected


def detect_board_via_arduino_cli(port: str) -> Optional[str]:
    """
    Use `arduino-cli board list` to detect the board model on *port*.

    Returns the detected FQBN string (e.g. "esp8266:esp8266:generic") or
    None if detection failed.  Requires arduino-cli to be installed and on PATH.

    We pass ``--port`` to narrow the scan; older versions of CLI returned
    incomplete data otherwise, which caused misclassification of ESP8266 as
    ESP32 when only the default platform was installed.
    """
    try:
        result = subprocess.run(
            ["arduino-cli", "board", "list", "--format", "json", "--port", port],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        detected_ports = data.get("detected_ports", [])
        for entry in detected_ports:
            matching_boards = entry.get("matching_boards", [])
            if matching_boards:
                return matching_boards[0].get("fqbn")
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None
