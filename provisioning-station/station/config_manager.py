"""
config_manager.py – Configuration persistence for the Provisioning Station.

Manages backend URL, operator name, JWT tokens, and other settings.
Stored in ~/.edubind/provisioning.json for persistence across sessions.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class ConfigManager:
    """Manages persistent configuration and JWT token storage."""

    DEFAULT_CONFIG_DIR = Path.home() / ".edubind"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "provisioning.json"

    DEFAULT_SETTINGS = {
        "backend_url": "http://10.191.14.110:8080",
        "operator_name": os.environ.get("USER", "operator"),
        "wifi_ssid": "",
        "wifi_password": "",
        "jwt_token": None,
        "jwt_expires_at": None,
    }

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """
        Parameters
        ----------
        config_path: Path to config file. Defaults to ~/.edubind/provisioning.json
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_FILE
        self._settings: dict[str, Any] = self.DEFAULT_SETTINGS.copy()
        self.load()

    def load(self) -> None:
        """Load settings from disk, or use defaults if file doesn't exist."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                    self._settings.update(loaded)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not load config {self.config_path}: {e}. Using defaults.")
        else:
            self.save()

    def save(self) -> None:
        """Save current settings to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._settings, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value (does not persist until save() is called)."""
        self._settings[key] = value

    def get_backend_url(self) -> str:
        """Get the backend URL."""
        return self.get("backend_url", self.DEFAULT_SETTINGS["backend_url"])

    def set_backend_url(self, url: str) -> None:
        """Set and persist the backend URL."""
        self.set("backend_url", url)
        self.save()

    def get_operator_name(self) -> str:
        """Get the operator name."""
        return self.get("operator_name", self.DEFAULT_SETTINGS["operator_name"])

    def set_operator_name(self, name: str) -> None:
        """Set and persist the operator name."""
        self.set("operator_name", name)
        self.save()

    def get_wifi_ssid(self) -> str:
        """Get the provisioned WiFi SSID."""
        return self.get("wifi_ssid", self.DEFAULT_SETTINGS["wifi_ssid"])

    def set_wifi_ssid(self, ssid: str) -> None:
        """Set and persist WiFi SSID."""
        self.set("wifi_ssid", ssid)
        self.save()

    def get_wifi_password(self) -> str:
        """Get the provisioned WiFi password."""
        return self.get("wifi_password", self.DEFAULT_SETTINGS["wifi_password"])

    def set_wifi_password(self, password: str) -> None:
        """Set and persist WiFi password."""
        self.set("wifi_password", password)
        self.save()

    def get_jwt_token(self) -> Optional[str]:
        """Get the stored JWT token if still valid."""
        if self.is_token_expired():
            return None
        return self.get("jwt_token")

    def set_jwt_token(self, token: str, expires_in_seconds: int = 3600) -> None:
        """
        Store JWT token with expiry.

        Parameters
        ----------
        token: JWT token string
        expires_in_seconds: Time until token expires (default 1 hour)
        """
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in_seconds)).isoformat()
        self.set("jwt_token", token)
        self.set("jwt_expires_at", expires_at)
        self.save()

    def is_token_expired(self, buffer_seconds: int = 60) -> bool:
        """
        Check if JWT token is expired.

        Parameters
        ----------
        buffer_seconds: Add buffer before actual expiry (default 60 seconds)
        """
        expires_at_str = self.get("jwt_expires_at")
        if not expires_at_str or not self.get("jwt_token"):
            return True
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            return datetime.utcnow() >= (expires_at - timedelta(seconds=buffer_seconds))
        except (ValueError, TypeError):
            return True

    def get_token_expiry_remaining_seconds(self) -> int:
        """Get remaining seconds until token expires, or -1 if already expired."""
        expires_at_str = self.get("jwt_expires_at")
        if not expires_at_str:
            return -1
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            remaining = (expires_at - datetime.utcnow()).total_seconds()
            return max(0, int(remaining))
        except (ValueError, TypeError):
            return -1

    def clear_token(self) -> None:
        """Clear the stored JWT token."""
        self.set("jwt_token", None)
        self.set("jwt_expires_at", None)
        self.save()

    def to_dict(self) -> dict[str, Any]:
        """Return a copy of all settings (excluding sensitive tokens)."""
        return {k: v for k, v in self._settings.items() if "token" not in k.lower()}
