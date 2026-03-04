"""
test_config_manager.py – Unit tests for ConfigManager.
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from station.config_manager import ConfigManager


class TestConfigManager:
    @pytest.fixture
    def temp_config_path(self) -> Path:
        """Create temporary config file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        temp_path.unlink(missing_ok=True)

    def test_init_default(self) -> None:
        """Test ConfigManager initialization with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            mgr = ConfigManager(config_path)
            assert mgr.get_backend_url() == ConfigManager.DEFAULT_SETTINGS["backend_url"]
            assert mgr.get_jwt_token() is None
            assert mgr.is_token_expired()

    def test_save_load(self, temp_config_path: Path) -> None:
        """Test saving and loading configuration."""
        mgr = ConfigManager(temp_config_path)
        mgr.set("test_key", "test_value")
        mgr.save()
        
        mgr2 = ConfigManager(temp_config_path)
        assert mgr2.get("test_key") == "test_value"

    def test_backend_url_persistence(self, temp_config_path: Path) -> None:
        """Test backend URL persistence."""
        mgr = ConfigManager(temp_config_path)
        mgr.set_backend_url("http://example.com:9000")
        
        mgr2 = ConfigManager(temp_config_path)
        assert mgr2.get_backend_url() == "http://example.com:9000"

    def test_operator_name_persistence(self, temp_config_path: Path) -> None:
        """Test operator name persistence."""
        mgr = ConfigManager(temp_config_path)
        mgr.set_operator_name("john_doe")
        
        mgr2 = ConfigManager(temp_config_path)
        assert mgr2.get_operator_name() == "john_doe"

    def test_jwt_token_storage(self, temp_config_path: Path) -> None:
        """Test JWT token storage and retrieval."""
        mgr = ConfigManager(temp_config_path)
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.sig"
        mgr.set_jwt_token(token, expires_in_seconds=3600)
        
        stored_token = mgr.get_jwt_token()
        assert stored_token == token

    def test_token_expiry_check(self, temp_config_path: Path) -> None:
        """Test token expiry detection."""
        mgr = ConfigManager(temp_config_path)
        token = "test_token"
        
        # Token should be expired immediately (expires_in=1 second)
        mgr.set_jwt_token(token, expires_in_seconds=1)
        import time
        time.sleep(1)
        assert mgr.is_token_expired(buffer_seconds=0)

    def test_token_not_expired_if_valid(self, temp_config_path: Path) -> None:
        """Test token not expired if still valid."""
        mgr = ConfigManager(temp_config_path)
        token = "test_token"
        mgr.set_jwt_token(token, expires_in_seconds=3600)
        
        assert not mgr.is_token_expired(buffer_seconds=0)

    def test_clear_token(self, temp_config_path: Path) -> None:
        """Test clearing token."""
        mgr = ConfigManager(temp_config_path)
        mgr.set_jwt_token("token", expires_in_seconds=3600)
        assert mgr.get_jwt_token() is not None
        
        mgr.clear_token()
        assert mgr.get_jwt_token() is None

    def test_to_dict_excludes_tokens(self, temp_config_path: Path) -> None:
        """Test that to_dict() excludes sensitive token data."""
        mgr = ConfigManager(temp_config_path)
        mgr.set_jwt_token("secret_token", expires_in_seconds=3600)
        mgr.set("other_key", "other_value")
        
        d = mgr.to_dict()
        assert "jwt_token" not in d or d["jwt_token"] is None
        assert "other_key" in d
