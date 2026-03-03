"""Tests for BackendClient (HTTP mocked with responses/unittest.mock)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from station.backend_client import BackendClient


@pytest.fixture
def client():
    return BackendClient("http://localhost:8080")


class TestRegisterDevice:
    def test_register_sends_correct_payload(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "id": "db-uuid-1",
            "deviceId": "ESP32-001",
            "model": "ESP32",
            "status": "PROVISIONING_PENDING",
        }
        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.register_device("ESP32-001", "ESP32", site="school-1")
            payload = mock_post.call_args.kwargs["json"]
            assert payload["deviceId"] == "ESP32-001"
            assert payload["model"] == "ESP32"
            assert payload["site"] == "school-1"
            assert result["status"] == "PROVISIONING_PENDING"

    def test_register_raises_on_http_error(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("400 Bad Request")
        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                client.register_device("ID", "ESP32")


class TestListFirmwares:
    def test_list_all(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [{"id": "fw1", "version": "1.0.0"}]
        with patch.object(client._session, "get", return_value=mock_resp):
            result = client.list_firmwares()
            assert len(result) == 1

    def test_list_by_board_passes_param(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []
        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            client.list_firmwares(board="ESP32")
            assert mock_get.call_args.kwargs["params"]["board"] == "ESP32"


class TestStartJob:
    def test_start_job_sends_all_fields(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "job-1", "result": "PENDING"}
        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.start_job("DEV-001", "FW-001", "alice", "station-01")
            payload = mock_post.call_args.kwargs["json"]
            assert payload["deviceId"] == "DEV-001"
            assert payload["firmwareId"] == "FW-001"
            assert payload["operator"] == "alice"
            assert payload["stationHostname"] == "station-01"
            assert result["result"] == "PENDING"


class TestReportJob:
    def test_report_success(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "job-1", "result": "SUCCESS"}
        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.report_job("job-1", "SUCCESS", "all ok", "abc123")
            payload = mock_post.call_args.kwargs["json"]
            assert payload["result"] == "SUCCESS"
            assert payload["configHash"] == "abc123"
            assert result["result"] == "SUCCESS"

    def test_report_without_config_hash(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"id": "job-1", "result": "FAILED"}
        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.report_job("job-1", "FAILED", "error msg")
            payload = mock_post.call_args.kwargs["json"]
            assert "configHash" not in payload
