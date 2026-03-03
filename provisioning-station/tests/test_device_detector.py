"""Tests for device_detector module (no hardware required)."""

from unittest.mock import MagicMock, patch

import pytest

from station.device_detector import (
    BOARD_FQBN,
    DetectedDevice,
    list_ports,
    detect_board_via_arduino_cli,
)


def _make_port_info(device: str, vid: int, pid: int, description: str = "") -> MagicMock:
    m = MagicMock()
    m.device = device
    m.vid = vid
    m.pid = pid
    m.description = description
    return m


class TestListPorts:
    @patch("station.device_detector._SERIAL_AVAILABLE", True)
    @patch("station.device_detector._list_ports.comports")
    def test_detects_arduino_r4_wifi(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info("/dev/ttyACM0", 0x2341, 0x0069, "Arduino UNO R4 WiFi")
        ]
        result = list_ports()
        assert len(result) == 1
        assert result[0].board_model == "ARDUINO_R4_WIFI"
        assert result[0].port == "/dev/ttyACM0"
        assert result[0].fqbn == BOARD_FQBN["ARDUINO_R4_WIFI"]

    @patch("station.device_detector._SERIAL_AVAILABLE", True)
    @patch("station.device_detector._list_ports.comports")
    def test_detects_esp32_cp2102(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info("/dev/ttyUSB0", 0x10C4, 0xEA60, "CP2102 USB to UART")
        ]
        result = list_ports()
        assert len(result) == 1
        assert result[0].board_model == "ESP32"

    @patch("station.device_detector._SERIAL_AVAILABLE", True)
    @patch("station.device_detector._list_ports.comports")
    def test_ignores_unknown_devices(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info("/dev/ttyUSB1", 0x1234, 0x5678, "Unknown device")
        ]
        result = list_ports()
        assert result == []

    @patch("station.device_detector._SERIAL_AVAILABLE", True)
    @patch("station.device_detector._list_ports.comports")
    def test_ignores_ports_without_vid_pid(self, mock_comports):
        port = _make_port_info("/dev/ttyS0", 0, 0)
        port.vid = None
        port.pid = None
        mock_comports.return_value = [port]
        result = list_ports()
        assert result == []

    @patch("station.device_detector._SERIAL_AVAILABLE", False)
    def test_raises_when_serial_not_available(self):
        with pytest.raises(RuntimeError, match="pyserial"):
            list_ports()

    @patch("station.device_detector._SERIAL_AVAILABLE", True)
    @patch("station.device_detector._list_ports.comports")
    def test_multiple_devices(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info("/dev/ttyACM0", 0x2341, 0x0069),
            _make_port_info("/dev/ttyUSB0", 0x10C4, 0xEA60),
        ]
        result = list_ports()
        assert len(result) == 2
        models = {d.board_model for d in result}
        assert models == {"ARDUINO_R4_WIFI", "ESP32"}


class TestDetectBoardViaArduinoCli:
    @patch("station.device_detector.subprocess.run")
    def test_returns_fqbn_when_found(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""{
                "detected_ports": [
                    {
                        "port": {"address": "/dev/ttyACM0"},
                        "matching_boards": [{"fqbn": "arduino:renesas_uno:unor4wifi"}]
                    }
                ]
            }"""
        )
        fqbn = detect_board_via_arduino_cli("/dev/ttyACM0")
        assert fqbn == "arduino:renesas_uno:unor4wifi"

    @patch("station.device_detector.subprocess.run")
    def test_returns_none_when_port_not_found(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"detected_ports": []}'
        )
        fqbn = detect_board_via_arduino_cli("/dev/ttyUSB99")
        assert fqbn is None

    @patch("station.device_detector.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_none_when_cli_not_installed(self, _):
        fqbn = detect_board_via_arduino_cli("/dev/ttyACM0")
        assert fqbn is None
