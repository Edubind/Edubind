"""Tests for flasher module (no hardware required)."""

import os
import tempfile
import hashlib
from unittest.mock import patch, MagicMock

import pytest

from station.flasher import flash_firmware, FlashResult, _verify_sha256


def _make_temp_firmware(content: bytes = b"FAKE_FIRMWARE_BINARY") -> str:
    fd, path = tempfile.mkstemp(suffix=".bin")
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


class TestVerifySha256:
    def test_correct_hash_returns_true(self):
        content = b"test content"
        path = _make_temp_firmware(content)
        try:
            expected = hashlib.sha256(content).hexdigest()
            assert _verify_sha256(path, expected) is True
        finally:
            os.unlink(path)

    def test_wrong_hash_returns_false(self):
        path = _make_temp_firmware(b"data")
        try:
            assert _verify_sha256(path, "000000") is False
        finally:
            os.unlink(path)


class TestFlashFirmware:
    def test_returns_failure_when_file_missing(self):
        result = flash_firmware(
            port="/dev/ttyUSB0",
            fqbn="esp32:esp32:esp32",
            firmware_path="/nonexistent/firmware.bin",
        )
        assert result.success is False
        assert "not found" in result.logs.lower()

    def test_returns_failure_when_sha256_mismatch(self):
        path = _make_temp_firmware(b"real content")
        try:
            result = flash_firmware(
                port="/dev/ttyUSB0",
                fqbn="esp32:esp32:esp32",
                firmware_path=path,
                expected_sha256="badhash",
            )
            assert result.success is False
            assert "mismatch" in result.logs.lower()
        finally:
            os.unlink(path)

    @patch("station.flasher.subprocess.run")
    def test_successful_flash(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Upload done.\n",
            stderr="",
        )
        path = _make_temp_firmware()
        try:
            result = flash_firmware(
                port="/dev/ttyACM0",
                fqbn="arduino:renesas_uno:unor4wifi",
                firmware_path=path,
            )
            assert result.success is True
            assert result.return_code == 0
        finally:
            os.unlink(path)

    @patch("station.flasher.subprocess.run")
    def test_failed_flash_returns_logs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="avrdude: ser_open(): can't open device\n",
        )
        path = _make_temp_firmware()
        try:
            result = flash_firmware(
                port="/dev/ttyACM0",
                fqbn="arduino:renesas_uno:unor4wifi",
                firmware_path=path,
            )
            assert result.success is False
            assert "avrdude" in result.logs
        finally:
            os.unlink(path)

    @patch("station.flasher.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_failure_when_arduino_cli_missing(self, _):
        path = _make_temp_firmware()
        try:
            result = flash_firmware(
                port="/dev/ttyACM0",
                fqbn="esp32:esp32:esp32",
                firmware_path=path,
            )
            assert result.success is False
            assert "arduino-cli" in result.logs
        finally:
            os.unlink(path)

    @patch("station.flasher.subprocess.run")
    def test_skips_sha256_check_when_not_provided(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        path = _make_temp_firmware()
        try:
            result = flash_firmware(
                port="/dev/ttyACM0",
                fqbn="esp32:esp32:esp32",
                firmware_path=path,
                expected_sha256=None,
            )
            assert result.success is True
        finally:
            os.unlink(path)

    @patch("station.flasher.subprocess.run")
    def test_passes_extra_flags_to_cli(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        path = _make_temp_firmware()
        try:
            flash_firmware(
                port="/dev/ttyACM0",
                fqbn="esp32:esp32:esp32",
                firmware_path=path,
                extra_flags=["--verbose"],
            )
            call_args = mock_run.call_args[0][0]
            assert "--verbose" in call_args
        finally:
            os.unlink(path)
