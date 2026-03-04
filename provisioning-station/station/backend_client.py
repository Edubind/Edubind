"""
backend_client.py – HTTP client for the Edubind provisioning backend (edubind-serv).

All methods raise requests.HTTPError on non-2xx responses.
Supports JWT Bearer authentication via AuthManager.
"""

from __future__ import annotations

from typing import Any, Optional, Callable

import requests

if False:  # TYPE_CHECKING
    from station.auth_manager import AuthManager


class BackendClient:
    def __init__(self, base_url: str, auth_manager: Optional[AuthManager] = None,
                 timeout: int = 30) -> None:
        """
        Parameters
        ----------
        base_url: Base URL of edubind-serv, e.g. "http://localhost:8080"
        auth_manager: AuthManager for JWT token injection (optional)
        timeout:  HTTP timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self.auth_manager = auth_manager

    def _make_request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        """
        Make an HTTP request with automatic Bearer token injection and 401 retry.

        Parameters
        ----------
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint (without base_url)
        **kwargs: Additional arguments for requests

        Returns
        -------
        requests.Response
        """
        url = f"{self.base_url}{endpoint}"
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        # First attempt with current token
        headers = kwargs.get("headers", {})
        if self.auth_manager:
            headers.update(self.auth_manager.get_auth_headers())
        kwargs["headers"] = headers

        resp = self._session.request(method, url, **kwargs)

        # If 401, try to refresh token and retry
        if resp.status_code == 401 and self.auth_manager:
            success, _ = self.auth_manager.refresh_token()
            if success:
                headers = kwargs.get("headers", {})
                headers.update(self.auth_manager.get_auth_headers())
                kwargs["headers"] = headers
                resp = self._session.request(method, url, **kwargs)

        return resp

    # ------------------------------------------------------------------ #
    # Devices                                                              #
    # ------------------------------------------------------------------ #

    def register_device(self, mac_address: str, room_id: int) -> dict[str, Any]:
        """Enrol a new device in the backend."""
        payload: dict[str, Any] = {
            "macAddress": mac_address,
            "roomId": room_id,
        }
        resp = self._make_request("POST", "/api/devices/register", json=payload)
        resp.raise_for_status()
        return resp.json()

    def list_devices(self) -> list[dict[str, Any]]:
        resp = self._make_request("GET", "/api/devices")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Firmwares                                                            #
    # ------------------------------------------------------------------ #

    def list_firmwares(self) -> list[dict[str, Any]]:
        """List available firmware versions."""
        resp = self._make_request("GET", "/api/ota/firmwares")
        resp.raise_for_status()
        return resp.json()

    def download_firmware(self, version: str, dest_path: str) -> None:
        """Download firmware artifact to *dest_path*."""
        resp = self._make_request(
            "GET", f"/api/ota/firmware/{version}",
            stream=True,
        )
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)

    def upload_firmware(self, version: str, file_path: str) -> dict[str, Any]:
        """Upload a firmware binary file to the server."""
        with open(file_path, "rb") as f:
            files = {"file": f}
            resp = self._make_request(
                "POST", "/api/ota/upload",
                params={"version": version},
                files=files
            )
        resp.raise_for_status()
        return resp.json()
    def delete_firmware(self, version: str) -> dict[str, Any]:
        """Delete a firmware version from the server."""
        resp = self._make_request("DELETE", f"/api/ota/firmwares/{version}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Rooms                                                                #
    # ------------------------------------------------------------------ #

    def list_rooms(self) -> list[dict[str, Any]]:
        """List all rooms."""
        resp = self._make_request("GET", "/api/rooms")
        resp.raise_for_status()
        return resp.json()

    def get_room(self, room_id: int) -> dict[str, Any]:
        """Get details of a specific room."""
        resp = self._make_request("GET", f"/api/rooms/{room_id}")
        resp.raise_for_status()
        return resp.json()

    def create_room(self, name: str) -> dict[str, Any]:
        """Create a new room."""
        payload = {"name": name}
        resp = self._make_request("POST", "/api/rooms", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete_room(self, room_id: int) -> None:
        """Delete a room."""
        resp = self._make_request("DELETE", f"/api/rooms/{room_id}")
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Device Management                                                    #
    # ------------------------------------------------------------------ #

    def get_device(self, device_id: int) -> dict[str, Any]:
        """Get details of a specific device."""
        resp = self._make_request("GET", f"/api/devices/{device_id}")
        resp.raise_for_status()
        return resp.json()

    def update_device_room(self, device_id: int, room_id: int) -> dict[str, Any]:
        """Update the room assignment for a device."""
        payload = {"roomId": room_id}
        resp = self._make_request("PUT", f"/api/devices/{device_id}/room", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete_device(self, device_id: int) -> None:
        """Delete a device."""
        resp = self._make_request("DELETE", f"/api/devices/{device_id}")
        resp.raise_for_status()

    def get_device_psk(self, device_id: int) -> dict[str, Any]:
        """Get the PSK key for a device."""
        resp = self._make_request("GET", f"/api/devices/{device_id}/psk")
        resp.raise_for_status()
        return resp.json()

    def get_device_by_mac(self, mac_address: str) -> Optional[dict[str, Any]]:
        """
        Find a device by its MAC address.
        
        Returns the device record if found, None otherwise.
        """
        try:
            devices = self.list_devices()
            for device in devices:
                if device.get("macAddress", "").upper() == mac_address.upper():
                    return device
        except Exception:
            pass
        return None