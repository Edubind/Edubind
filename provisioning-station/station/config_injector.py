"""
config_injector.py – Build and inject a configuration blob into an Arduino/ESP32 device.

The config is serialised as a fixed-size binary record and written into the device's
EEPROM/flash via the serial port *after* the firmware has been flashed.

Extended Binary layout (512 bytes, null-padded):
    Offset  Length  Field
    0       4       Magic header: 0xED 0xB1 0x1D 0x01
    4       64      WiFi SSID      (UTF-8, null-terminated)
    68      64      WiFi Password  (UTF-8, null-terminated)
    132     64      CoAP Server endpoint (IP:port, UTF-8, null-terminated)
    196     24      MAC Address    (UTF-8, null-terminated)
    220     32      PSK Key (hex)  (UTF-8, null-terminated)
    252     64      OTA Server endpoint (NEW, UTF-8, null-terminated)
    316      4      OTA Server Port (NEW, big-endian uint32)
    320      8      Firmware Version Label (NEW, UTF-8, null-terminated)
    328     16      Reserved
    344      4      Secondary magic: 0xED 0xB1 0x1D 0x02 (NEW, validation)
    348     32      Board / Classroom name (NEW, UTF-8, null-terminated)
    380    132      Reserved
    Total   512 bytes

The firmware listens for the sequence:
    1. Station sends marker:   b'\\xCF\\xFA\\xCE\\x01'  (CONFIG_START_MARKER)
    2. Station sends 512 bytes (the config blob)
    3. Firmware writes blob to EEPROM
    4. Firmware replies:       b'\\xCF\\xFA\\xCE\\x02'  (CONFIG_ACK)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

MAGIC = bytes([0xED, 0xB1, 0x1D, 0x01])
MAGIC2 = bytes([0xED, 0xB1, 0x1D, 0x02])
CONFIG_START_MARKER = bytes([0xCF, 0xFA, 0xCE, 0x01])
CONFIG_ACK = bytes([0xCF, 0xFA, 0xCE, 0x02])
CONFIG_BLOB_SIZE = 512

# Extended blob field offsets and sizes
FIELD_SSID_OFFSET = 4
FIELD_SSID_LEN = 64
FIELD_PASS_OFFSET = 68
FIELD_PASS_LEN = 64
FIELD_ENDPOINT_OFFSET = 132
FIELD_ENDPOINT_LEN = 64
FIELD_MAC_OFFSET = 196
FIELD_MAC_LEN = 24
FIELD_PSK_OFFSET = 220
FIELD_PSK_LEN = 32
FIELD_OTA_SERVER_OFFSET = 252
FIELD_OTA_SERVER_LEN = 64
FIELD_OTA_PORT_OFFSET = 316
FIELD_OTA_PORT_LEN = 4
FIELD_FW_VERSION_OFFSET = 320
FIELD_FW_VERSION_LEN = 8
FIELD_MAGIC2_OFFSET = 344
FIELD_BOARD_NAME_OFFSET = 348
FIELD_BOARD_NAME_LEN = 32


@dataclass
class DeviceConfig:
    mac_address: str
    wifi_ssid: str
    wifi_password: str
    server_endpoint: str
    psk_key: str = ""
    ota_server_endpoint: str = ""  # NEW: for HTTP firmware updates
    firmware_version: str = ""  # NEW: for version tracking
    board_name: str = ""  # NEW: classroom / board identifier


def build_config_blob(config: DeviceConfig) -> bytes:
    """Serialise *config* into the 512-byte binary blob."""
    blob = bytearray(CONFIG_BLOB_SIZE)

    # Primary magic header
    blob[0:4] = MAGIC

    # Secondary magic at offset 344
    blob[FIELD_MAGIC2_OFFSET:FIELD_MAGIC2_OFFSET+4] = MAGIC2

    # Helper: encode string field, filling up to max_len. 
    # If the string is exactly max_len bytes, it will not be null-terminated on the wire,
    # but the C++ firmware safely adds a null-terminator upon reading.
    def _write(offset: int, max_len: int, value: str) -> None:
        if not value:
            return
        encoded = value.encode("utf-8")[:max_len]
        blob[offset:offset + len(encoded)] = encoded

    _write(FIELD_SSID_OFFSET, FIELD_SSID_LEN, config.wifi_ssid)
    _write(FIELD_PASS_OFFSET, FIELD_PASS_LEN, config.wifi_password)
    _write(FIELD_ENDPOINT_OFFSET, FIELD_ENDPOINT_LEN, config.server_endpoint)
    _write(FIELD_MAC_OFFSET, FIELD_MAC_LEN, config.mac_address)
    _write(FIELD_PSK_OFFSET, FIELD_PSK_LEN, config.psk_key)
    _write(FIELD_OTA_SERVER_OFFSET, FIELD_OTA_SERVER_LEN, config.ota_server_endpoint)
    _write(FIELD_FW_VERSION_OFFSET, FIELD_FW_VERSION_LEN, config.firmware_version)
    _write(FIELD_BOARD_NAME_OFFSET, FIELD_BOARD_NAME_LEN, config.board_name)

    return bytes(blob)


def compute_sha256(blob: bytes) -> str:
    """Return the hex-encoded SHA-256 of *blob*."""
    return hashlib.sha256(blob).hexdigest()


def inject_config(port: str, config: DeviceConfig,
                  baud_rate: int = 115200,
                  timeout: float = 10.0,
                  log_fn=None) -> str:
    """
    Send the config blob to the device over *port*.
    Returns the SHA-256 hash of the config blob on success.
    Raises RuntimeError on failure.

    Requires pyserial.
    """
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyserial is not installed. Run: pip install pyserial") from exc

    blob = build_config_blob(config)
    config_hash = compute_sha256(blob)

    # Let the port open normally (which usually resets the board via DTR/RTS).
    with serial.Serial(port, baud_rate, timeout=0.1) as ser:
        response = bytearray()

        _log(f"  [INJ] Port opened: {port} @ {baud_rate} baud")

        # Wait 2 seconds for the board to reboot and print it's "READY" message.
        time.sleep(2.0)
        ser.reset_input_buffer()

        # Retry marker+blob throughout the timeout window.
        # The provisioning helper sketch (mac_reporter) is already running
        # and actively draining serial in its loop(), so there is no
        # 64-byte RX buffer overflow risk.
        deadline = time.monotonic() + timeout
        resend_interval = 1.0
        next_send_at = time.monotonic()  # Send immediately now that boot time passed
        attempt = 0

        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_send_at:
                attempt += 1
                _log(f"  [INJ] Attempt {attempt}: sending 4-byte marker + {len(blob)}-byte blob…")
                ser.write(CONFIG_START_MARKER)
                ser.write(blob)
                ser.flush()
                next_send_at = now + resend_interval

            chunk = ser.read(ser.in_waiting or 1)
            if chunk:
                text_part = chunk.decode("utf-8", errors="ignore").strip()
                if text_part:
                    for line in text_part.splitlines():
                        line = line.strip()
                        if line:
                            _log(f"  [INJ] ← {line}")
                response.extend(chunk)
                if bytes(CONFIG_ACK) in response:
                    _log("  [INJ] ✓ CONFIG_ACK received!")
                    return config_hash
            time.sleep(0.05)

    raise RuntimeError(
        f"No CONFIG_ACK received from device on {port} "
        f"within {timeout}s. Response buffer: {response!r}"
    )
