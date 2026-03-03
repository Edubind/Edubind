"""
config_injector.py – Build and inject a configuration blob into an Arduino/ESP32 device.

The config is serialised as a fixed-size binary record and written into the device's
EEPROM/flash via the serial port *after* the firmware has been flashed.

Binary layout (256 bytes, null-padded):
    Offset  Length  Field
    0       4       Magic header: 0xED 0xB1 0x1D 0x01
    4       64      WiFi SSID      (UTF-8, null-terminated)
    68      64      WiFi Password  (UTF-8, null-terminated)
    132     80      Server endpoint URL (UTF-8, null-terminated)
    212     32      Device ID      (UTF-8, null-terminated)
    244     12      Reserved (zeros)
    Total   256 bytes

The firmware listens for the sequence:
    1. Station sends marker:   b'\\xCF\\xFA\\xCE\\x01'  (CONFIG_START_MARKER)
    2. Station sends 256 bytes (the config blob)
    3. Firmware writes blob to EEPROM/Preferences partition
    4. Firmware replies:       b'\\xCF\\xFA\\xCE\\x02'  (CONFIG_ACK)
"""

from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import dataclass
from typing import Optional

MAGIC = bytes([0xED, 0xB1, 0x1D, 0x01])
CONFIG_START_MARKER = bytes([0xCF, 0xFA, 0xCE, 0x01])
CONFIG_ACK = bytes([0xCF, 0xFA, 0xCE, 0x02])
CONFIG_BLOB_SIZE = 256

FIELD_SSID_OFFSET = 4
FIELD_SSID_LEN = 64
FIELD_PASS_OFFSET = 68
FIELD_PASS_LEN = 64
FIELD_ENDPOINT_OFFSET = 132
FIELD_ENDPOINT_LEN = 80
FIELD_DEVICE_ID_OFFSET = 212
FIELD_DEVICE_ID_LEN = 32


@dataclass
class DeviceConfig:
    device_id: str
    wifi_ssid: str
    wifi_password: str
    server_endpoint: str


def build_config_blob(config: DeviceConfig) -> bytes:
    """Serialise *config* into the 256-byte binary blob."""
    blob = bytearray(CONFIG_BLOB_SIZE)

    # Magic header
    blob[0:4] = MAGIC

    # Helper: encode and null-pad a string field
    def _write(offset: int, max_len: int, value: str) -> None:
        encoded = value.encode("utf-8")[:max_len - 1]
        blob[offset:offset + len(encoded)] = encoded
        # remaining bytes are already 0 (null-terminated)

    _write(FIELD_SSID_OFFSET, FIELD_SSID_LEN, config.wifi_ssid)
    _write(FIELD_PASS_OFFSET, FIELD_PASS_LEN, config.wifi_password)
    _write(FIELD_ENDPOINT_OFFSET, FIELD_ENDPOINT_LEN, config.server_endpoint)
    _write(FIELD_DEVICE_ID_OFFSET, FIELD_DEVICE_ID_LEN, config.device_id)

    return bytes(blob)


def compute_sha256(blob: bytes) -> str:
    """Return the hex-encoded SHA-256 of *blob*."""
    return hashlib.sha256(blob).hexdigest()


def inject_config(port: str, config: DeviceConfig,
                  baud_rate: int = 115200,
                  timeout: float = 10.0) -> str:
    """
    Send the config blob to the device over *port*.
    Returns the SHA-256 hash of the config blob on success.
    Raises RuntimeError on failure.

    Requires pyserial.
    """
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyserial is not installed. Run: pip install pyserial") from exc

    blob = build_config_blob(config)
    config_hash = compute_sha256(blob)

    with serial.Serial(port, baud_rate, timeout=timeout) as ser:
        # Allow the device to reset if it just got flashed
        time.sleep(2)
        ser.reset_input_buffer()

        # Send start marker
        ser.write(CONFIG_START_MARKER)
        ser.flush()

        # Send blob
        ser.write(blob)
        ser.flush()

        # Wait for ACK (up to *timeout* seconds)
        deadline = time.monotonic() + timeout
        response = bytearray()
        while time.monotonic() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            response.extend(chunk)
            if bytes(CONFIG_ACK) in response:
                return config_hash
            time.sleep(0.05)

    raise RuntimeError(
        f"No CONFIG_ACK received from device on {port} "
        f"within {timeout}s. Response buffer: {response!r}"
    )
