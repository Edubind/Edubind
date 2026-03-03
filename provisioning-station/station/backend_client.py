"""
backend_client.py – HTTP client for the Edubind provisioning backend (edubind-serv).

All methods raise requests.HTTPError on non-2xx responses.
"""

from __future__ import annotations

from typing import Any, Optional

import requests


class BackendClient:
    def __init__(self, base_url: str, timeout: int = 30) -> None:
        """
        Parameters
        ----------
        base_url: Base URL of edubind-serv, e.g. "http://localhost:8080"
        timeout:  HTTP timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    # Devices                                                              #
    # ------------------------------------------------------------------ #

    def register_device(self, device_id: str, model: str,
                        hardware_revision: Optional[str] = None,
                        site: Optional[str] = None,
                        group: Optional[str] = None) -> dict[str, Any]:
        """Enrol a new device in the backend."""
        payload: dict[str, Any] = {
            "deviceId": device_id,
            "model": model,
        }
        if hardware_revision:
            payload["hardwareRevision"] = hardware_revision
        if site:
            payload["site"] = site
        if group:
            payload["group"] = group
        resp = self._session.post(f"{self.base_url}/api/devices",
                                  json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_device_config(self, device_db_id: str) -> dict[str, Any]:
        """Fetch the config blob (wifi/endpoint) for a registered device."""
        resp = self._session.get(f"{self.base_url}/api/devices/{device_db_id}/config",
                                 timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def list_devices(self) -> list[dict[str, Any]]:
        resp = self._session.get(f"{self.base_url}/api/devices", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Firmwares                                                            #
    # ------------------------------------------------------------------ #

    def list_firmwares(self, board: Optional[str] = None) -> list[dict[str, Any]]:
        """List available firmware versions, optionally filtered by board model."""
        params = {}
        if board:
            params["board"] = board
        resp = self._session.get(f"{self.base_url}/api/firmwares",
                                 params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def download_firmware(self, firmware_id: str, dest_path: str) -> None:
        """Download firmware artifact to *dest_path*."""
        resp = self._session.get(
            f"{self.base_url}/api/firmwares/{firmware_id}/download",
            stream=True, timeout=self.timeout,
        )
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)

    # ------------------------------------------------------------------ #
    # Provisioning jobs                                                    #
    # ------------------------------------------------------------------ #

    def start_job(self, device_id: str, firmware_id: str,
                  operator: str, station_hostname: str) -> dict[str, Any]:
        """Create a new provisioning job (PENDING state)."""
        payload = {
            "deviceId": device_id,
            "firmwareId": firmware_id,
            "operator": operator,
            "stationHostname": station_hostname,
        }
        resp = self._session.post(f"{self.base_url}/api/provisioning/jobs",
                                  json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def report_job(self, job_id: str, result: str,
                   logs: str, config_hash: Optional[str] = None) -> dict[str, Any]:
        """Report the final result of a provisioning job."""
        payload: dict[str, Any] = {
            "result": result,
            "logs": logs,
        }
        if config_hash:
            payload["configHash"] = config_hash
        resp = self._session.post(
            f"{self.base_url}/api/provisioning/jobs/{job_id}/report",
            json=payload, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def list_jobs(self, device_id: Optional[str] = None) -> list[dict[str, Any]]:
        params = {}
        if device_id:
            params["deviceId"] = device_id
        resp = self._session.get(f"{self.base_url}/api/provisioning/jobs",
                                 params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
