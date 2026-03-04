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
    @patch("time.sleep", return_value=None)
    def test_performs_reset_before_upload(self, mock_sleep, mock_run):
        # ensure the 1200bps toggle is attempted when reset_before=True
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        fake_serial = MagicMock()
        with patch.dict("sys.modules", {"serial": fake_serial}):
            # import inside context to ensure our fake is used
            import serial  # type: ignore
            path = _make_temp_firmware()
            try:
                flash_firmware(
                    port="/dev/ttyUSB0",
                    fqbn="esp32:esp32:esp32",
                    firmware_path=path,
                    reset_before=True,
                )
                serial.Serial.assert_called_with("/dev/ttyUSB0", baudrate=1200, timeout=0.1)
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

    @patch("station.flasher.subprocess.run")
    def test_port_variant_retry(self, mock_run):
        # First call (original port) fails; second call (variant) succeeds
        flop = MagicMock(returncode=1, stdout="", stderr="No such file or directory")
        win = MagicMock(returncode=0, stdout="Done", stderr="")
        mock_run.side_effect = [flop, win]
        path = _make_temp_firmware()
        try:
            result = flash_firmware(
                port="/dev/cu.usbmodem1234",
                fqbn="arduino:renesas_uno:unor4wifi",
                firmware_path=path,
            )
            assert result.success is True
            # verify we indeed tried two different ports
            called_ports = [call[0][0][3] for call in mock_run.call_args_list]
            assert "/dev/cu.usbmodem1234" in called_ports
            assert "/dev/tty.usbmodem1234" in called_ports
            # logs should contain debug markers
            assert "[flash]" in result.logs
        finally:
            os.unlink(path)

    @patch("station.flasher.subprocess.run")
    def test_renesas_normalizes_non_bin_upload_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        fd, path = tempfile.mkstemp(suffix=".hex")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(b"BINARY")

            result = flash_firmware(
                port="/dev/cu.usbmodem1234",
                fqbn="arduino:renesas_uno:unor4wifi",
                firmware_path=path,
            )
            assert result.success is True

            cmd = mock_run.call_args[0][0]
            upload_file = cmd[cmd.index("--input-file") + 1]
            assert upload_file.endswith(".bin")
            assert "normalized artifact path" in result.logs
        finally:
            os.unlink(path)
