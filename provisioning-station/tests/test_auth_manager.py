"""
test_auth_manager.py – Unit tests for AuthManager.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from station.auth_manager import AuthManager
from station.config_manager import ConfigManager


class TestAuthManager:
    @pytest.fixture
    def config_mgr(self) -> ConfigManager:
        """Create temporary ConfigManager for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            yield ConfigManager(config_path)

    @pytest.fixture
    def auth_mgr(self, config_mgr: ConfigManager) -> AuthManager:
        """Create AuthManager with mocked ConfigManager."""
        return AuthManager(config_mgr)

    def test_init(self, auth_mgr: AuthManager, config_mgr: ConfigManager) -> None:
        """Test AuthManager initialization."""
        assert auth_mgr.config == config_mgr
        assert auth_mgr._base_url == config_mgr.get_backend_url()

    def test_is_authenticated_false_without_token(self, auth_mgr: AuthManager) -> None:
        """Test is_authenticated returns False without token."""
        assert not auth_mgr.is_authenticated()

    def test_is_authenticated_true_with_token(self, auth_mgr: AuthManager) -> None:
        """Test is_authenticated returns True with valid token."""
        auth_mgr.config.set_jwt_token("test_token", expires_in_seconds=3600)
        assert auth_mgr.is_authenticated()

    def test_get_auth_headers_empty_without_token(self, auth_mgr: AuthManager) -> None:
        """Test get_auth_headers returns empty dict without token."""
        headers = auth_mgr.get_auth_headers()
        assert headers == {}

    def test_get_auth_headers_with_token(self, auth_mgr: AuthManager) -> None:
        """Test get_auth_headers returns Bearer token."""
        token = "test_jwt_token_123"
        auth_mgr.config.set_jwt_token(token, expires_in_seconds=3600)
        
        headers = auth_mgr.get_auth_headers()
        assert headers == {"Authorization": f"Bearer {token}"}

    @patch("requests.post")
    def test_login_success(self, mock_post: Mock, auth_mgr: AuthManager) -> None:
        """Test successful login."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "new_token", "expires_in": 3600}
        mock_post.return_value = mock_response
        
        success, msg = auth_mgr.login("user", "pass")
        
        assert success
        assert "successful" in msg.lower()
        assert auth_mgr.config.get_jwt_token() == "new_token"

    @patch("requests.post")
    def test_login_invalid_credentials(self, mock_post: Mock, auth_mgr: AuthManager) -> None:
        """Test login with invalid credentials."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        success, msg = auth_mgr.login("user", "wrong_pass")
        
        assert not success
        assert "invalid" in msg.lower()

    @patch("requests.post")
    def test_login_connection_error(self, mock_post: Mock, auth_mgr: AuthManager) -> None:
        """Test login with connection error."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()
        
        success, msg = auth_mgr.login("user", "pass")
        
        assert not success
        assert "connection" in msg.lower()

    @patch("requests.post")
    def test_refresh_token_success(self, mock_post: Mock, auth_mgr: AuthManager) -> None:
        """Test successful token refresh."""
        old_token = "old_token"
        auth_mgr.config.set_jwt_token(old_token, expires_in_seconds=3600)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "new_token", "expires_in": 3600}
        mock_post.return_value = mock_response
        
        success, msg = auth_mgr.refresh_token()
        
        assert success
        assert auth_mgr.config.get_jwt_token() == "new_token"

    @patch("requests.post")
    def test_refresh_token_401_clears_token(self, mock_post: Mock, auth_mgr: AuthManager) -> None:
        """Test token refresh with 401 clears token."""
        auth_mgr.config.set_jwt_token("old_token", expires_in_seconds=3600)
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        success, msg = auth_mgr.refresh_token()
        
        assert not success
        assert auth_mgr.config.get_jwt_token() is None

    def test_is_token_expiring_soon_threshold(self, auth_mgr: AuthManager) -> None:
        """Test token expiry threshold detection."""
        # Token expires in 10 minutes
        auth_mgr.config.set_jwt_token("token", expires_in_seconds=600)
        
        # Should be expiring soon (default threshold 15 minutes)
        assert auth_mgr.is_token_expiring_soon(threshold_seconds=900)
        
        # Should not be expiring soon if threshold is lower
        assert not auth_mgr.is_token_expiring_soon(threshold_seconds=300)

    def test_logout(self, auth_mgr: AuthManager) -> None:
        """Test logout clears token."""
        auth_mgr.config.set_jwt_token("token", expires_in_seconds=3600)
        assert auth_mgr.is_authenticated()
        
        auth_mgr.logout()
        
        assert not auth_mgr.is_authenticated()
