"""Tests for config_injector module (no hardware required)."""

import types
from unittest.mock import patch

import pytest

from station.config_injector import (
    CONFIG_BLOB_SIZE,
    CONFIG_ACK,
    CONFIG_START_MARKER,
    DeviceConfig,
    build_config_blob,
    compute_sha256,
    FIELD_SSID_OFFSET,
    FIELD_SSID_LEN,
    FIELD_PASS_OFFSET,
    FIELD_PASS_LEN,
    FIELD_ENDPOINT_OFFSET,
    FIELD_ENDPOINT_LEN,
    FIELD_MAC_OFFSET,
    FIELD_MAC_LEN,
    FIELD_PSK_OFFSET,
    FIELD_PSK_LEN,
    MAGIC,
    inject_config,
)


def _make_config(**kwargs) -> DeviceConfig:
    defaults = dict(
        mac_address="AA:BB:CC:DD:EE:FF",
        wifi_ssid="SchoolWiFi",
        wifi_password="secret123",
        server_endpoint="http://edubind-serv:8080",
        psk_key="",
    )
    defaults.update(kwargs)
    return DeviceConfig(**defaults)


class TestBuildConfigBlob:
    def test_blob_is_correct_size(self):
        blob = build_config_blob(_make_config())
        assert len(blob) == CONFIG_BLOB_SIZE

    def test_magic_header(self):
        blob = build_config_blob(_make_config())
        assert blob[:4] == MAGIC

    def test_ssid_encoded(self):
        config = _make_config(wifi_ssid="TestSSID")
        blob = build_config_blob(config)
        field = blob[FIELD_SSID_OFFSET:FIELD_SSID_OFFSET + FIELD_SSID_LEN]
        assert field.rstrip(b"\x00") == b"TestSSID"

    def test_password_encoded(self):
        config = _make_config(wifi_password="MyPass!")
        blob = build_config_blob(config)
        field = blob[FIELD_PASS_OFFSET:FIELD_PASS_OFFSET + FIELD_PASS_LEN]
        assert field.rstrip(b"\x00") == b"MyPass!"

    def test_endpoint_encoded(self):
        config = _make_config(server_endpoint="http://192.168.1.10:8080")
        blob = build_config_blob(config)
        field = blob[FIELD_ENDPOINT_OFFSET:FIELD_ENDPOINT_OFFSET + FIELD_ENDPOINT_LEN]
        assert field.rstrip(b"\x00") == b"http://192.168.1.10:8080"

    def test_mac_encoded(self):
        config = _make_config(mac_address="AA:11:BB:22:CC:33")
        blob = build_config_blob(config)
        field = blob[FIELD_MAC_OFFSET:FIELD_MAC_OFFSET + FIELD_MAC_LEN]
        assert field.rstrip(b"\x00") == b"AA:11:BB:22:CC:33"

    def test_psk_encoded(self):
        config = _make_config(psk_key="deadbeef")
        blob = build_config_blob(config)
        field = blob[FIELD_PSK_OFFSET:FIELD_PSK_OFFSET + FIELD_PSK_LEN]
        assert field.rstrip(b"\x00") == b"deadbeef"

    def test_long_ssid_truncated(self):
        long_ssid = "A" * 100
        config = _make_config(wifi_ssid=long_ssid)
        blob = build_config_blob(config)
        # Must fit in field without overflow into next field
        assert len(blob) == CONFIG_BLOB_SIZE
        field = blob[FIELD_SSID_OFFSET:FIELD_PASS_OFFSET]
        # Last byte of field must be null terminator
        assert field[-1] == 0

    def test_empty_fields(self):
        config = _make_config(wifi_ssid="", wifi_password="",
                              server_endpoint="", mac_address="", psk_key="")
        blob = build_config_blob(config)
        assert len(blob) == CONFIG_BLOB_SIZE

    def test_deterministic(self):
        config = _make_config()
        assert build_config_blob(config) == build_config_blob(config)


class TestComputeSha256:
    def test_sha256_is_64_hex_chars(self):
        blob = build_config_blob(_make_config())
        h = compute_sha256(blob)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_configs_have_different_hashes(self):
        blob1 = build_config_blob(_make_config(wifi_ssid="Net1"))
        blob2 = build_config_blob(_make_config(wifi_ssid="Net2"))
        assert compute_sha256(blob1) != compute_sha256(blob2)


class _FakeSerial:
    ack_after_attempt = 2
    marker = CONFIG_START_MARKER

    def __init__(self, *_, **__):
        self.timeout = 0.1
        self.in_waiting = 0
        self._reads: list[bytes] = []
        self._write_buf = bytearray()
        self._attempts = 0
        self.dtr = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def reset_input_buffer(self):
        self._reads.clear()
        self.in_waiting = 0

    def write(self, data: bytes):
        self._write_buf.extend(data)
        if self.marker in self._write_buf:
            self._attempts += 1
            self._write_buf.clear()
            if self._attempts >= self.ack_after_attempt:
                self._reads.append(CONFIG_ACK)
                self.in_waiting = len(CONFIG_ACK)

    def flush(self):
        return None

    def read(self, n: int):
        if not self._reads:
            self.in_waiting = 0
            return b""
        payload = self._reads.pop(0)
        self.in_waiting = 0
        return payload[:n]


class _NoAckSerial(_FakeSerial):
    ack_after_attempt = 9999


class TestInjectConfig:
    @patch("time.sleep", return_value=None)
    def test_retries_until_ack(self, _):
        fake_serial_module = types.SimpleNamespace(Serial=_FakeSerial)
        with patch.dict("sys.modules", {"serial": fake_serial_module}):
            config = _make_config()
            config_hash = inject_config("/dev/ttyUSB0", config, timeout=3.0)
            assert len(config_hash) == 64

    @patch("time.sleep", return_value=None)
    def test_timeout_contains_response_buffer(self, _):
        fake_serial_module = types.SimpleNamespace(Serial=_NoAckSerial)
        with patch.dict("sys.modules", {"serial": fake_serial_module}):
            config = _make_config()
            with pytest.raises(RuntimeError) as exc:
                inject_config("/dev/ttyUSB0", config, timeout=0.5)
            assert "No CONFIG_ACK received" in str(exc.value)
