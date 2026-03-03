"""Tests for config_injector module (no hardware required)."""

import struct

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
    FIELD_DEVICE_ID_OFFSET,
    FIELD_DEVICE_ID_LEN,
    MAGIC,
)


def _make_config(**kwargs) -> DeviceConfig:
    defaults = dict(
        device_id="ESP32-TEST-001",
        wifi_ssid="SchoolWiFi",
        wifi_password="secret123",
        server_endpoint="http://edubind-serv:8080",
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

    def test_device_id_encoded(self):
        config = _make_config(device_id="ESP32-UNIT-007")
        blob = build_config_blob(config)
        field = blob[FIELD_DEVICE_ID_OFFSET:FIELD_DEVICE_ID_OFFSET + FIELD_DEVICE_ID_LEN]
        assert field.rstrip(b"\x00") == b"ESP32-UNIT-007"

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
                              server_endpoint="", device_id="")
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
