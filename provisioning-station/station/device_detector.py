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
    (0x10C4, 0xEA60): "ESP32",   # CP2102/CP2104 (common ESP32 devboards)
    (0x1A86, 0x7523): "ESP32",   # CH340 (common ESP32 devboards)
    (0x1A86, 0x55D4): "ESP32",   # CH9102 (newer ESP32 devboards)
}

# arduino-cli FQBN mapping for each board model
BOARD_FQBN: dict[str, str] = {
    "ARDUINO_R4_WIFI": "arduino:renesas_uno:unor4wifi",
    "ESP32": "esp32:esp32:esp32",
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
    """Return a list of connected Arduino/ESP32 devices."""
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
    Use arduino-cli board list to detect the board model on a given port.
    Returns the FQBN string or None if not detected.
    Requires arduino-cli to be installed and on PATH.
    """
    try:
        result = subprocess.run(
            ["arduino-cli", "board", "list", "--format", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        detected_ports = data.get("detected_ports", [])
        for entry in detected_ports:
            matching_boards = entry.get("matching_boards", [])
            port_address = entry.get("port", {}).get("address", "")
            if port_address == port and matching_boards:
                return matching_boards[0].get("fqbn")
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None
