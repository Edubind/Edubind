"""
flasher.py – Flash firmware onto an Arduino/ESP32 device using arduino-cli.

Supports:
    - Arduino R4 WiFi  (arduino:renesas_uno:unor4wifi)
    - ESP32            (esp32:esp32:esp32)
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FlashResult:
    success: bool
    logs: str
    return_code: int


def _verify_sha256(file_path: str, expected_hash: str) -> bool:
    """Return True if *file_path* matches *expected_hash* (hex SHA-256)."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected_hash.lower()


def flash_firmware(
    port: str,
    fqbn: str,
    firmware_path: str,
    expected_sha256: Optional[str] = None,
    arduino_cli_path: str = "arduino-cli",
    extra_flags: Optional[list[str]] = None,
) -> FlashResult:
    """
    Flash *firmware_path* onto the device at *port* using arduino-cli.

    Parameters
    ----------
    port:            Serial port (e.g. "/dev/ttyUSB0" or "COM3")
    fqbn:            Full Qualified Board Name (e.g. "esp32:esp32:esp32")
    firmware_path:   Absolute path to the .bin/.hex artifact
    expected_sha256: If provided, the artifact is verified before flashing
    arduino_cli_path: Path to the arduino-cli binary (default: "arduino-cli")
    extra_flags:     Additional flags passed to arduino-cli upload

    Returns
    -------
    FlashResult with success flag, combined stdout/stderr logs, and return code.
    """
    if not os.path.isfile(firmware_path):
        return FlashResult(
            success=False,
            logs=f"Firmware file not found: {firmware_path}",
            return_code=-1,
        )

    if expected_sha256:
        if not _verify_sha256(firmware_path, expected_sha256):
            return FlashResult(
                success=False,
                logs=f"SHA-256 mismatch for {firmware_path}. "
                     f"Expected: {expected_sha256}",
                return_code=-2,
            )

    cmd = [
        arduino_cli_path,
        "upload",
        "--port", port,
        "--fqbn", fqbn,
        "--input-file", firmware_path,
        "--verify",
    ]
    if extra_flags:
        cmd.extend(extra_flags)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        logs = result.stdout + result.stderr
        return FlashResult(
            success=result.returncode == 0,
            logs=logs,
            return_code=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return FlashResult(
            success=False,
            logs="arduino-cli timed out after 120s",
            return_code=-3,
        )
    except FileNotFoundError:
        return FlashResult(
            success=False,
            logs=f"arduino-cli not found at: {arduino_cli_path}. "
                 "Install it from https://arduino.github.io/arduino-cli/",
            return_code=-4,
        )
