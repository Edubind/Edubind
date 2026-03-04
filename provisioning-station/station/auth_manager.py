"""
auth_manager.py – JWT authentication manager for the Provisioning Station.

Handles login, token refresh, and Bearer token injection into HTTP requests.
Works with ConfigManager for persistent token storage.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

from station.config_manager import ConfigManager


class AuthManager:
    """Manages JWT authentication with the Edubind backend."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Parameters
        ----------
        config_manager: ConfigManager instance for persistent token storage
        """
        self.config = config_manager
        self._base_url = config_manager.get_backend_url()

    def login(self, username: str, password: str, timeout: int = 10) -> tuple[bool, str]:
        """
        Authenticate with backend and store JWT token.

        Parameters
        ----------
        username: Operator username
        password: Operator password
        timeout: HTTP request timeout in seconds

        Returns
        -------
        (success: bool, message: str)
        """
        try:
            self._base_url = self.config.get_backend_url()
            resp = requests.post(
                f"{self._base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=timeout,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                token = data.get("token") or data.get("access_token")
                expires_in = data.get("expiresIn", 86400)
                if token:
                    self.config.set_jwt_token(token, expires_in)
                    return True, "Login successful."
                else:
                    return False, "No token in response."
            elif resp.status_code == 401:
                return False, "Invalid username or password."
            else:
                return False, f"Login failed: HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Connection error. Check backend URL and network."
        except requests.exceptions.Timeout:
            return False, "Request timeout. Backend may be unreachable."
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def refresh_token(self, timeout: int = 10) -> tuple[bool, str]:
        """
        Refresh JWT token with backend.

        Parameters
        ----------
        timeout: HTTP request timeout in seconds

        Returns
        -------
        (success: bool, message: str)
        """
        old_token = self.config.get_jwt_token()
        if not old_token:
            return False, "No token to refresh."

        try:
            self._base_url = self.config.get_backend_url()
            resp = requests.post(
                f"{self._base_url}/api/auth/refresh",
                headers={"Authorization": f"Bearer {old_token}"},
                timeout=timeout,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                token = data.get("token") or data.get("access_token")
                expires_in = data.get("expiresIn", 86400)
                if token:
                    self.config.set_jwt_token(token, expires_in)
                    return True, "Token refreshed."
                else:
                    return False, "No token in refresh response."
            elif resp.status_code == 401:
                self.config.clear_token()
                return False, "Token expired. Please login again."
            else:
                return False, f"Refresh failed: HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Connection error during token refresh."
        except requests.exceptions.Timeout:
            return False, "Token refresh timeout."
        except Exception as e:
            return False, f"Unexpected error during refresh: {e}"

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get headers dict with Bearer token for authenticated requests.

        Returns
        -------
        dict with 'Authorization' header if token available, else empty dict
        """
        token = self.config.get_jwt_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def is_authenticated(self) -> bool:
        """Check if a valid token is currently available."""
        return self.config.get_jwt_token() is not None

    def is_token_expiring_soon(self, threshold_seconds: int = 900) -> bool:
        """
        Check if token will expire within threshold (default 15 minutes).

        Parameters
        ----------
        threshold_seconds: Check if expiry is within this many seconds
        """
        remaining = self.config.get_token_expiry_remaining_seconds()
        return 0 <= remaining < threshold_seconds

    def logout(self) -> None:
        """Clear the stored JWT token."""
        self.config.clear_token()
