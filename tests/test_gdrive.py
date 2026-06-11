"""Tests for Google Drive integration module."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock


# =============================================================================
# Auth Module Tests
# =============================================================================


class TestAuthHelpers:
    """Tests for authentication helper functions."""

    def test_get_bundled_credentials_from_env(self):
        """Test getting bundled credentials from environment."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_CLIENT_SECRET": "test-client-secret",
            },
        ):
            from vectrola.gdrive.auth import _get_bundled_credentials

            client_id, client_secret = _get_bundled_credentials()
            assert client_id == "test-client-id"
            assert client_secret == "test-client-secret"

    def test_get_bundled_credentials_empty_when_not_set(self):
        """Test getting bundled credentials when not set."""
        with patch.dict("os.environ", {}, clear=True):
            from vectrola.gdrive.auth import _get_bundled_credentials

            client_id, client_secret = _get_bundled_credentials()
            assert client_id == ""
            assert client_secret == ""


class TestGetClientConfig:
    """Tests for _get_client_config function."""

    def test_get_client_config_from_custom_creds(self, tmp_path):
        """Test loading client config from custom credentials file."""
        from vectrola.gdrive import auth

        # Save original path
        original_path = auth.CUSTOM_CREDS_PATH

        try:
            # Create temp credentials file
            creds_file = tmp_path / "custom_creds.json"
            creds_file.write_text(
                json.dumps(
                    {
                        "client_id": "custom-client-id",
                        "client_secret": "custom-client-secret",
                    }
                )
            )

            # Patch the path
            auth.CUSTOM_CREDS_PATH = creds_file

            config = auth._get_client_config()
            assert config["installed"]["client_id"] == "custom-client-id"
            assert config["installed"]["client_secret"] == "custom-client-secret"
            assert "auth_uri" in config["installed"]
            assert "token_uri" in config["installed"]
        finally:
            auth.CUSTOM_CREDS_PATH = original_path

    def test_get_client_config_from_env(self, tmp_path):
        """Test loading client config from environment variables."""
        from vectrola.gdrive import auth

        # Save original path
        original_path = auth.CUSTOM_CREDS_PATH

        try:
            # Point to non-existent file
            auth.CUSTOM_CREDS_PATH = tmp_path / "nonexistent.json"

            with patch.dict(
                "os.environ",
                {
                    "GOOGLE_CLIENT_ID": "env-client-id",
                    "GOOGLE_CLIENT_SECRET": "env-client-secret",
                },
            ):
                config = auth._get_client_config()
                assert config["installed"]["client_id"] == "env-client-id"
                assert config["installed"]["client_secret"] == "env-client-secret"
        finally:
            auth.CUSTOM_CREDS_PATH = original_path

    def test_get_client_config_raises_when_no_credentials(self, tmp_path):
        """Test that _get_client_config raises error when no credentials."""
        from vectrola.gdrive import auth

        # Save original path
        original_path = auth.CUSTOM_CREDS_PATH

        try:
            auth.CUSTOM_CREDS_PATH = tmp_path / "nonexistent.json"

            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(RuntimeError, match="credentials not configured"):
                    auth._get_client_config()
        finally:
            auth.CUSTOM_CREDS_PATH = original_path


class TestSetupCustomCredentials:
    """Tests for setup_custom_credentials function."""

    def test_setup_custom_credentials_creates_file(self, tmp_path):
        """Test that setup_custom_credentials creates credentials file."""
        from vectrola.gdrive import auth

        # Save original paths
        original_token_dir = auth.TOKEN_DIR
        original_creds_path = auth.CUSTOM_CREDS_PATH
        original_token_path = auth.TOKEN_PATH

        try:
            auth.TOKEN_DIR = tmp_path
            auth.CUSTOM_CREDS_PATH = tmp_path / "custom_creds.json"
            auth.TOKEN_PATH = tmp_path / "token.json"

            auth.setup_custom_credentials("my-client-id", "my-client-secret")

            assert auth.CUSTOM_CREDS_PATH.exists()
            creds = json.loads(auth.CUSTOM_CREDS_PATH.read_text())
            assert creds["client_id"] == "my-client-id"
            assert creds["client_secret"] == "my-client-secret"
        finally:
            auth.TOKEN_DIR = original_token_dir
            auth.CUSTOM_CREDS_PATH = original_creds_path
            auth.TOKEN_PATH = original_token_path

    def test_setup_custom_credentials_removes_existing_token(self, tmp_path):
        """Test that setup_custom_credentials removes existing token."""
        from vectrola.gdrive import auth

        # Save original paths
        original_token_dir = auth.TOKEN_DIR
        original_creds_path = auth.CUSTOM_CREDS_PATH
        original_token_path = auth.TOKEN_PATH

        try:
            auth.TOKEN_DIR = tmp_path
            auth.CUSTOM_CREDS_PATH = tmp_path / "custom_creds.json"
            auth.TOKEN_PATH = tmp_path / "token.json"

            # Create existing token
            auth.TOKEN_PATH.write_text('{"token": "old"}')
            assert auth.TOKEN_PATH.exists()

            auth.setup_custom_credentials("my-client-id", "my-client-secret")

            # Token should be removed
            assert not auth.TOKEN_PATH.exists()
        finally:
            auth.TOKEN_DIR = original_token_dir
            auth.CUSTOM_CREDS_PATH = original_creds_path
            auth.TOKEN_PATH = original_token_path


class TestIsAuthenticated:
    """Tests for is_authenticated function."""

    def test_is_authenticated_returns_false_when_no_token(self, tmp_path):
        """Test is_authenticated returns False when no token exists."""
        from vectrola.gdrive import auth

        original_token_path = auth.TOKEN_PATH

        try:
            auth.TOKEN_PATH = tmp_path / "nonexistent.json"
            assert auth.is_authenticated() is False
        finally:
            auth.TOKEN_PATH = original_token_path

    def test_is_authenticated_returns_true_for_valid_credentials(self):
        """Test is_authenticated returns True for valid credentials."""
        from vectrola.gdrive import auth

        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch.object(auth, "get_credentials", return_value=mock_creds):
            assert auth.is_authenticated() is True

    def test_is_authenticated_returns_false_for_invalid_credentials(self):
        """Test is_authenticated returns False for invalid credentials."""
        from vectrola.gdrive import auth

        mock_creds = MagicMock()
        mock_creds.valid = False

        with patch.object(auth, "get_credentials", return_value=mock_creds):
            assert auth.is_authenticated() is False

    def test_is_authenticated_handles_exceptions(self):
        """Test is_authenticated returns False on exceptions."""
        from vectrola.gdrive import auth

        with patch.object(auth, "get_credentials", side_effect=Exception("Error")):
            assert auth.is_authenticated() is False


class TestGetCredentials:
    """Tests for get_credentials function."""

    def test_get_credentials_returns_none_when_no_token(self, tmp_path):
        """Test get_credentials returns None when token file doesn't exist."""
        from vectrola.gdrive import auth

        original_token_path = auth.TOKEN_PATH

        try:
            auth.TOKEN_PATH = tmp_path / "nonexistent.json"
            assert auth.get_credentials() is None
        finally:
            auth.TOKEN_PATH = original_token_path

    def test_get_credentials_loads_and_refreshes(self, tmp_path):
        """Test get_credentials loads credentials and refreshes if expired."""
        from vectrola.gdrive import auth

        original_token_path = auth.TOKEN_PATH

        try:
            # Create a token file
            token_file = tmp_path / "token.json"
            token_file.write_text('{"token": "test"}')
            auth.TOKEN_PATH = token_file

            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_creds.expired = False

            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ):
                creds = auth.get_credentials()
                assert creds == mock_creds
        finally:
            auth.TOKEN_PATH = original_token_path

    def test_get_credentials_refreshes_expired_token(self, tmp_path):
        """Test get_credentials refreshes expired token."""
        from vectrola.gdrive import auth

        original_token_path = auth.TOKEN_PATH

        try:
            token_file = tmp_path / "token.json"
            token_file.write_text('{"token": "test"}')
            auth.TOKEN_PATH = token_file

            mock_creds = MagicMock()
            mock_creds.expired = True
            mock_creds.refresh_token = "refresh_token"
            mock_creds.valid = True

            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=mock_creds,
            ):
                with patch("google.auth.transport.requests.Request"):
                    creds = auth.get_credentials()
                    mock_creds.refresh.assert_called_once()
        finally:
            auth.TOKEN_PATH = original_token_path


class TestAuthenticate:
    """Tests for authenticate function."""

    def test_authenticate_returns_existing_credentials(self):
        """Test authenticate returns existing valid credentials."""
        from vectrola.gdrive import auth

        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch.object(auth, "get_credentials", return_value=mock_creds):
            result = auth.authenticate(force=False)
            assert result == mock_creds

    def test_authenticate_force_reauth(self):
        """Test authenticate with force=True runs OAuth flow."""
        from vectrola.gdrive import auth

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "new"}'

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        with patch.object(auth, "_get_client_config", return_value={"installed": {}}):
            with patch(
                "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
                return_value=mock_flow,
            ):
                with patch.object(auth, "_save_credentials"):
                    result = auth.authenticate(force=True)
                    assert result == mock_creds
                    mock_flow.run_local_server.assert_called_once()


class TestLogout:
    """Tests for logout function."""

    def test_logout_removes_token_file(self, tmp_path):
        """Test logout removes the token file."""
        from vectrola.gdrive import auth

        original_token_path = auth.TOKEN_PATH

        try:
            token_file = tmp_path / "token.json"
            token_file.write_text('{"token": "test"}')
            auth.TOKEN_PATH = token_file

            result = auth.logout()

            assert result is True
            assert not token_file.exists()
        finally:
            auth.TOKEN_PATH = original_token_path

    def test_logout_returns_false_when_no_token(self, tmp_path):
        """Test logout returns False when no token exists."""
        from vectrola.gdrive import auth

        original_token_path = auth.TOKEN_PATH

        try:
            auth.TOKEN_PATH = tmp_path / "nonexistent.json"
            result = auth.logout()
            assert result is False
        finally:
            auth.TOKEN_PATH = original_token_path


# =============================================================================
# Allowed Folders Tests
# =============================================================================


class TestAllowedFolders:
    """Tests for allowed folders management."""

    @pytest.fixture
    def temp_folders_path(self, tmp_path):
        """Set up temporary allowed folders path."""
        from vectrola.gdrive import auth

        original_path = auth.ALLOWED_FOLDERS_PATH
        original_token_dir = auth.TOKEN_DIR

        auth.ALLOWED_FOLDERS_PATH = tmp_path / "allowed_folders.json"
        auth.TOKEN_DIR = tmp_path

        yield auth.ALLOWED_FOLDERS_PATH

        auth.ALLOWED_FOLDERS_PATH = original_path
        auth.TOKEN_DIR = original_token_dir

    def test_get_allowed_folders_empty_when_no_file(self, temp_folders_path):
        """Test get_allowed_folders returns empty dict when no file."""
        from vectrola.gdrive.auth import get_allowed_folders

        folders = get_allowed_folders()
        assert folders == {}

    def test_get_allowed_folders_returns_saved_folders(self, temp_folders_path):
        """Test get_allowed_folders returns saved folders."""
        from vectrola.gdrive.auth import get_allowed_folders

        temp_folders_path.write_text(json.dumps({"folder1": "/Music", "folder2": "/Songs"}))

        folders = get_allowed_folders()
        assert folders == {"folder1": "/Music", "folder2": "/Songs"}

    def test_get_allowed_folders_handles_invalid_json(self, temp_folders_path):
        """Test get_allowed_folders handles invalid JSON gracefully."""
        from vectrola.gdrive.auth import get_allowed_folders

        temp_folders_path.write_text("invalid json")

        folders = get_allowed_folders()
        assert folders == {}

    def test_add_allowed_folder(self, temp_folders_path):
        """Test add_allowed_folder adds folder to list."""
        from vectrola.gdrive.auth import add_allowed_folder, get_allowed_folders

        add_allowed_folder("abc123", "/Music")
        add_allowed_folder("def456", "/Songs")

        folders = get_allowed_folders()
        assert folders == {"abc123": "/Music", "def456": "/Songs"}

    def test_add_allowed_folder_updates_existing(self, temp_folders_path):
        """Test add_allowed_folder updates existing folder path."""
        from vectrola.gdrive.auth import add_allowed_folder, get_allowed_folders

        add_allowed_folder("abc123", "/Music")
        add_allowed_folder("abc123", "/Music/Bollywood")

        folders = get_allowed_folders()
        assert folders == {"abc123": "/Music/Bollywood"}

    def test_remove_allowed_folder(self, temp_folders_path):
        """Test remove_allowed_folder removes folder from list."""
        from vectrola.gdrive.auth import (
            add_allowed_folder,
            remove_allowed_folder,
            get_allowed_folders,
        )

        add_allowed_folder("abc123", "/Music")
        add_allowed_folder("def456", "/Songs")

        result = remove_allowed_folder("abc123")

        assert result is True
        folders = get_allowed_folders()
        assert folders == {"def456": "/Songs"}

    def test_remove_allowed_folder_returns_false_if_not_found(self, temp_folders_path):
        """Test remove_allowed_folder returns False if folder not in list."""
        from vectrola.gdrive.auth import add_allowed_folder, remove_allowed_folder

        add_allowed_folder("abc123", "/Music")

        result = remove_allowed_folder("nonexistent")

        assert result is False

    def test_clear_allowed_folders(self, temp_folders_path):
        """Test clear_allowed_folders removes all folders."""
        from vectrola.gdrive.auth import (
            add_allowed_folder,
            clear_allowed_folders,
            get_allowed_folders,
        )

        add_allowed_folder("abc123", "/Music")
        add_allowed_folder("def456", "/Songs")

        count = clear_allowed_folders()

        assert count == 2
        folders = get_allowed_folders()
        assert folders == {}

    def test_clear_allowed_folders_returns_zero_when_empty(self, temp_folders_path):
        """Test clear_allowed_folders returns 0 when no folders."""
        from vectrola.gdrive.auth import clear_allowed_folders

        count = clear_allowed_folders()
        assert count == 0


class TestIsFolderAllowed:
    """Tests for is_folder_allowed function."""

    @pytest.fixture
    def temp_folders_path(self, tmp_path):
        """Set up temporary allowed folders path."""
        from vectrola.gdrive import auth

        original_path = auth.ALLOWED_FOLDERS_PATH
        original_token_dir = auth.TOKEN_DIR

        auth.ALLOWED_FOLDERS_PATH = tmp_path / "allowed_folders.json"
        auth.TOKEN_DIR = tmp_path

        yield auth.ALLOWED_FOLDERS_PATH

        auth.ALLOWED_FOLDERS_PATH = original_path
        auth.TOKEN_DIR = original_token_dir

    def test_is_folder_allowed_returns_true_when_no_restrictions(self, temp_folders_path):
        """Test is_folder_allowed returns True when no folders configured."""
        from vectrola.gdrive.auth import is_folder_allowed

        assert is_folder_allowed("any-folder-id") is True

    def test_is_folder_allowed_returns_true_for_allowed_folder(self, temp_folders_path):
        """Test is_folder_allowed returns True for allowed folder."""
        from vectrola.gdrive.auth import add_allowed_folder, is_folder_allowed

        add_allowed_folder("abc123", "/Music")

        assert is_folder_allowed("abc123") is True

    def test_is_folder_allowed_returns_false_for_disallowed_folder(self, temp_folders_path):
        """Test is_folder_allowed returns False for disallowed folder."""
        from vectrola.gdrive.auth import add_allowed_folder, is_folder_allowed

        add_allowed_folder("abc123", "/Music")

        assert is_folder_allowed("other-folder") is False


class TestIsPathAllowed:
    """Tests for is_path_allowed function."""

    @pytest.fixture
    def temp_folders_path(self, tmp_path):
        """Set up temporary allowed folders path."""
        from vectrola.gdrive import auth

        original_path = auth.ALLOWED_FOLDERS_PATH
        original_token_dir = auth.TOKEN_DIR

        auth.ALLOWED_FOLDERS_PATH = tmp_path / "allowed_folders.json"
        auth.TOKEN_DIR = tmp_path

        yield auth.ALLOWED_FOLDERS_PATH

        auth.ALLOWED_FOLDERS_PATH = original_path
        auth.TOKEN_DIR = original_token_dir

    def test_is_path_allowed_returns_true_when_no_restrictions(self, temp_folders_path):
        """Test is_path_allowed returns True when no folders configured."""
        from vectrola.gdrive.auth import is_path_allowed

        assert is_path_allowed("/any/path", lambda p: "id") is True

    def test_is_path_allowed_returns_true_for_allowed_path(self, temp_folders_path):
        """Test is_path_allowed returns True for path under allowed folder."""
        from vectrola.gdrive.auth import add_allowed_folder, is_path_allowed

        add_allowed_folder("abc123", "/Music")

        assert is_path_allowed("/Music/Bollywood", lambda p: "abc123") is True
        assert is_path_allowed("/Music", lambda p: "abc123") is True

    def test_is_path_allowed_returns_false_for_disallowed_path(self, temp_folders_path):
        """Test is_path_allowed returns False for disallowed path."""
        from vectrola.gdrive.auth import add_allowed_folder, is_path_allowed

        add_allowed_folder("abc123", "/Music")

        assert is_path_allowed("/Documents", lambda p: "other") is False
        assert is_path_allowed("/Other/Folder", lambda p: "other") is False

    def test_is_path_allowed_normalizes_paths(self, temp_folders_path):
        """Test is_path_allowed normalizes path separators."""
        from vectrola.gdrive.auth import add_allowed_folder, is_path_allowed

        add_allowed_folder("abc123", "Music")

        # Should work with or without leading slash
        assert is_path_allowed("Music/Bollywood", lambda p: "abc123") is True
        assert is_path_allowed("/Music/Bollywood/", lambda p: "abc123") is True


# =============================================================================
# DriveFile Tests
# =============================================================================


class TestDriveFile:
    """Tests for DriveFile dataclass."""

    def test_drive_file_creation(self):
        """Test DriveFile creation with basic attributes."""
        from vectrola.gdrive.client import DriveFile

        file = DriveFile(
            id="file123",
            name="song.mp3",
            mime_type="audio/mpeg",
            size_bytes=5242880,
            parent_path="/Music",
            modified_time="2024-01-01T00:00:00Z",
        )

        assert file.id == "file123"
        assert file.name == "song.mp3"
        assert file.mime_type == "audio/mpeg"
        assert file.size_bytes == 5242880
        assert file.parent_path == "/Music"
        assert file.modified_time == "2024-01-01T00:00:00Z"

    def test_drive_file_extension(self):
        """Test DriveFile extension property."""
        from vectrola.gdrive.client import DriveFile

        test_cases = [
            ("audio/mpeg", ".mp3"),
            ("audio/flac", ".flac"),
            ("audio/x-flac", ".flac"),
            ("audio/wav", ".wav"),
            ("audio/x-wav", ".wav"),
            ("audio/mp4", ".m4a"),
            ("audio/x-m4a", ".m4a"),
            ("audio/ogg", ".ogg"),
            ("audio/webm", ".webm"),
            ("video/webm", ".webm"),
            ("application/octet-stream", ""),  # Unknown type
        ]

        for mime_type, expected_ext in test_cases:
            file = DriveFile(
                id="test",
                name="test",
                mime_type=mime_type,
                size_bytes=0,
                parent_path="/",
            )
            assert file.extension == expected_ext, f"Failed for {mime_type}"

    def test_drive_file_size_mb(self):
        """Test DriveFile size_mb property."""
        from vectrola.gdrive.client import DriveFile

        file = DriveFile(
            id="test",
            name="test.mp3",
            mime_type="audio/mpeg",
            size_bytes=10485760,  # 10 MB
            parent_path="/",
        )

        assert file.size_mb == 10.0

    def test_drive_file_is_folder(self):
        """Test DriveFile is_folder property."""
        from vectrola.gdrive.client import DriveFile

        folder = DriveFile(
            id="folder123",
            name="Music",
            mime_type="application/vnd.google-apps.folder",
            size_bytes=0,
            parent_path="/",
        )
        file = DriveFile(
            id="file123",
            name="song.mp3",
            mime_type="audio/mpeg",
            size_bytes=1000,
            parent_path="/Music",
        )

        assert folder.is_folder is True
        assert file.is_folder is False


# =============================================================================
# DriveClient Tests
# =============================================================================


class TestDriveClient:
    """Tests for DriveClient class."""

    def test_drive_client_initialization(self):
        """Test DriveClient initialization."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        assert client._credentials == mock_creds
        assert client._service is None  # Lazy loaded

    def test_drive_client_service_lazy_loading(self):
        """Test DriveClient lazily loads service."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        mock_service = MagicMock()

        with patch("googleapiclient.discovery.build", return_value=mock_service):
            client = DriveClient(credentials=mock_creds)

            # Service not built yet
            assert client._service is None

            # Access service property
            service = client.service

            assert service == mock_service
            assert client._service == mock_service

    def test_drive_client_service_loads_credentials_if_none(self):
        """Test DriveClient loads credentials if none provided."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        mock_service = MagicMock()

        with patch("googleapiclient.discovery.build", return_value=mock_service):
            with patch(
                "vectrola.gdrive.auth.get_credentials", return_value=mock_creds
            ) as mock_get_creds:
                client = DriveClient(credentials=None)
                _ = client.service

                mock_get_creds.assert_called_once()
                assert client._credentials == mock_creds

    def test_drive_client_raises_when_not_authenticated(self):
        """Test DriveClient raises error when not authenticated."""
        from vectrola.gdrive.client import DriveClient

        with patch("vectrola.gdrive.auth.get_credentials", return_value=None):
            client = DriveClient(credentials=None)

            with pytest.raises(RuntimeError, match="Not authenticated"):
                _ = client.service


class TestDriveClientResolvePath:
    """Tests for DriveClient.resolve_path method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked DriveClient."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        # Mock the service
        mock_service = MagicMock()
        client._service = mock_service

        return client

    def test_resolve_path_root(self, mock_client):
        """Test resolve_path returns 'root' for root paths."""
        assert mock_client.resolve_path("/") == "root"
        assert mock_client.resolve_path("") == "root"
        assert mock_client.resolve_path("root") == "root"

    def test_resolve_path_single_folder(self, mock_client):
        """Test resolve_path for single folder."""
        mock_response = {"files": [{"id": "folder123", "mimeType": "folder"}]}
        mock_client._service.files().list().execute.return_value = mock_response

        result = mock_client.resolve_path("/Music")

        assert result == "folder123"

    def test_resolve_path_nested_folders(self, mock_client):
        """Test resolve_path for nested folders."""
        # First call returns Music folder, second returns Bollywood folder
        mock_client._service.files().list().execute.side_effect = [
            {"files": [{"id": "music123", "mimeType": "folder"}]},
            {"files": [{"id": "bollywood456", "mimeType": "folder"}]},
        ]

        result = mock_client.resolve_path("/Music/Bollywood")

        assert result == "bollywood456"

    def test_resolve_path_not_found(self, mock_client):
        """Test resolve_path returns None when path not found."""
        mock_client._service.files().list().execute.return_value = {"files": []}

        result = mock_client.resolve_path("/NonExistent")

        assert result is None


class TestDriveClientListContents:
    """Tests for DriveClient.list_contents method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked DriveClient."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        mock_service = MagicMock()
        client._service = mock_service

        return client

    def test_list_contents_empty_folder(self, mock_client):
        """Test list_contents on empty folder."""
        with patch.object(mock_client, "resolve_path", return_value="folder123"):
            mock_client._service.files().list().execute.return_value = {
                "files": [],
                "nextPageToken": None,
            }

            results = list(mock_client.list_contents("/Music"))

            assert results == []

    def test_list_contents_with_files_and_folders(self, mock_client):
        """Test list_contents returns folders first, then files."""
        from vectrola.gdrive.client import DriveFile

        mock_response = {
            "files": [
                {
                    "id": "file1",
                    "name": "song.mp3",
                    "mimeType": "audio/mpeg",
                    "size": "1000",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                },
                {
                    "id": "folder1",
                    "name": "Subfolder",
                    "mimeType": "application/vnd.google-apps.folder",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                },
            ],
        }

        with patch.object(mock_client, "resolve_path", return_value="folder123"):
            mock_client._service.files().list().execute.return_value = mock_response

            results = list(mock_client.list_contents("/Music"))

            assert len(results) == 2
            # Folders should come first
            assert results[0].name == "Subfolder"
            assert results[0].is_folder is True
            # Then files
            assert results[1].name == "song.mp3"
            assert results[1].is_folder is False

    def test_list_contents_filters_non_audio_files(self, mock_client):
        """Test list_contents filters out non-audio files."""
        mock_response = {
            "files": [
                {
                    "id": "file1",
                    "name": "song.mp3",
                    "mimeType": "audio/mpeg",
                    "size": "1000",
                },
                {
                    "id": "file2",
                    "name": "document.pdf",
                    "mimeType": "application/pdf",
                    "size": "2000",
                },
                {
                    "id": "file3",
                    "name": "image.jpg",
                    "mimeType": "image/jpeg",
                    "size": "3000",
                },
            ],
        }

        with patch.object(mock_client, "resolve_path", return_value="folder123"):
            mock_client._service.files().list().execute.return_value = mock_response

            results = list(mock_client.list_contents("/Music"))

            assert len(results) == 1
            assert results[0].name == "song.mp3"

    def test_list_contents_raises_for_invalid_path(self, mock_client):
        """Test list_contents raises error for invalid path."""
        with patch.object(mock_client, "resolve_path", return_value=None):
            with pytest.raises(FileNotFoundError, match="Drive path not found"):
                list(mock_client.list_contents("/NonExistent"))


class TestDriveClientListFiles:
    """Tests for DriveClient.list_files method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked DriveClient."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        mock_service = MagicMock()
        client._service = mock_service

        return client

    def test_list_files_non_recursive(self, mock_client):
        """Test list_files without recursion."""
        mock_response = {
            "files": [
                {
                    "id": "file1",
                    "name": "song.mp3",
                    "mimeType": "audio/mpeg",
                    "size": "1000",
                },
                {
                    "id": "folder1",
                    "name": "Subfolder",
                    "mimeType": "application/vnd.google-apps.folder",
                },
            ],
        }

        with patch.object(mock_client, "resolve_path", return_value="folder123"):
            mock_client._service.files().list().execute.return_value = mock_response

            results = list(mock_client.list_files("/Music", recursive=False))

            # Should only return the audio file, not recurse into subfolder
            assert len(results) == 1
            assert results[0].name == "song.mp3"

    def test_list_files_recursive(self, mock_client):
        """Test list_files with recursion."""
        # First call: root folder with one file and one subfolder
        # Second call: subfolder with one file
        mock_client._service.files().list().execute.side_effect = [
            {
                "files": [
                    {"id": "file1", "name": "song1.mp3", "mimeType": "audio/mpeg", "size": "1000"},
                    {"id": "folder1", "name": "Subfolder", "mimeType": "application/vnd.google-apps.folder"},
                ],
            },
            {
                "files": [
                    {"id": "file2", "name": "song2.mp3", "mimeType": "audio/mpeg", "size": "2000"},
                ],
            },
        ]

        with patch.object(mock_client, "resolve_path", return_value="folder123"):
            results = list(mock_client.list_files("/Music", recursive=True))

            assert len(results) == 2
            names = [r.name for r in results]
            assert "song1.mp3" in names
            assert "song2.mp3" in names

    def test_list_files_raises_for_invalid_path(self, mock_client):
        """Test list_files raises error for invalid path."""
        with patch.object(mock_client, "resolve_path", return_value=None):
            with pytest.raises(FileNotFoundError, match="Drive path not found"):
                list(mock_client.list_files("/NonExistent"))


class TestDriveClientDownloadFile:
    """Tests for DriveClient.download_file method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked DriveClient."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        mock_service = MagicMock()
        client._service = mock_service

        return client

    def test_download_file_creates_dest_dir(self, mock_client, tmp_path):
        """Test download_file creates destination directory."""
        from vectrola.gdrive.client import DriveFile

        dest_dir = tmp_path / "downloads" / "music"
        assert not dest_dir.exists()

        file = DriveFile(
            id="file123",
            name="song.mp3",
            mime_type="audio/mpeg",
            size_bytes=1000,
            parent_path="/Music",
        )

        # Mock the downloader
        mock_downloader = MagicMock()
        mock_downloader.next_chunk.return_value = (None, True)

        with patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader):
            result = mock_client.download_file(file, dest_dir)

            assert dest_dir.exists()
            assert result == dest_dir / "song.mp3"

    def test_download_file_with_progress_callback(self, mock_client, tmp_path):
        """Test download_file calls progress callback."""
        from vectrola.gdrive.client import DriveFile

        file = DriveFile(
            id="file123",
            name="song.mp3",
            mime_type="audio/mpeg",
            size_bytes=1000,
            parent_path="/Music",
        )

        mock_status = MagicMock()
        mock_status.progress.return_value = 0.5

        mock_downloader = MagicMock()
        mock_downloader.next_chunk.side_effect = [
            (mock_status, False),
            (None, True),
        ]

        progress_values = []

        def progress_callback(progress):
            progress_values.append(progress)

        with patch("googleapiclient.http.MediaIoBaseDownload", return_value=mock_downloader):
            mock_client.download_file(file, tmp_path, progress_callback=progress_callback)

            assert 0.5 in progress_values


class TestDriveClientGetQuota:
    """Tests for DriveClient.get_quota method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked DriveClient."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        mock_service = MagicMock()
        client._service = mock_service

        return client

    def test_get_quota_returns_storage_info(self, mock_client):
        """Test get_quota returns storage quota information."""
        mock_quota = {
            "limit": "15000000000",
            "usage": "5000000000",
            "usageInDrive": "3000000000",
        }
        mock_client._service.about().get().execute.return_value = {"storageQuota": mock_quota}

        result = mock_client.get_quota()

        assert result == mock_quota


class TestDriveClientGetUserInfo:
    """Tests for DriveClient.get_user_info method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked DriveClient."""
        from vectrola.gdrive.client import DriveClient

        mock_creds = MagicMock()
        client = DriveClient(credentials=mock_creds)

        mock_service = MagicMock()
        client._service = mock_service

        return client

    def test_get_user_info_returns_user_data(self, mock_client):
        """Test get_user_info returns user information."""
        mock_user = {
            "displayName": "Test User",
            "emailAddress": "test@example.com",
        }
        mock_client._service.about().get().execute.return_value = {"user": mock_user}

        result = mock_client.get_user_info()

        assert result == mock_user


# =============================================================================
# Picker Module Tests
# =============================================================================


class TestPickerHandler:
    """Tests for PickerHandler HTTP handler."""

    def test_picker_handler_class_attributes(self):
        """Test PickerHandler has expected class attributes."""
        from vectrola.gdrive.picker import PickerHandler

        assert PickerHandler.selected_folders is None
        assert PickerHandler.access_token is None
        assert PickerHandler.server_should_stop is False

    def test_picker_handler_reset_state(self):
        """Test PickerHandler state can be reset."""
        from vectrola.gdrive.picker import PickerHandler

        # Set some state
        PickerHandler.selected_folders = [{"id": "1", "name": "Test"}]
        PickerHandler.access_token = "token123"
        PickerHandler.server_should_stop = True

        # Reset state
        PickerHandler.selected_folders = None
        PickerHandler.access_token = None
        PickerHandler.server_should_stop = False

        assert PickerHandler.selected_folders is None
        assert PickerHandler.access_token is None
        assert PickerHandler.server_should_stop is False


class TestOpenFolderPicker:
    """Tests for open_folder_picker function."""

    def test_open_folder_picker_raises_on_no_port(self):
        """Test open_folder_picker raises error when no port available."""
        from vectrola.gdrive.picker import open_folder_picker

        with patch("vectrola.gdrive.picker.StoppableServer", side_effect=OSError("Port in use")):
            with pytest.raises(RuntimeError, match="Could not start server"):
                open_folder_picker("client-id", "api-key")

    def test_open_folder_picker_raises_on_cancelled(self):
        """Test open_folder_picker raises error when selection cancelled."""
        from vectrola.gdrive.picker import open_folder_picker, PickerHandler

        mock_server = MagicMock()

        def reset_and_serve():
            PickerHandler.selected_folders = None

        mock_server.serve_until_stopped = reset_and_serve

        with patch("vectrola.gdrive.picker.StoppableServer", return_value=mock_server):
            with patch("webbrowser.open"):
                with pytest.raises(RuntimeError, match="cancelled or failed"):
                    open_folder_picker("client-id", "api-key")


# =============================================================================
# Integration Tests (marked to skip by default)
# =============================================================================


@pytest.mark.network
class TestDriveClientIntegration:
    """Integration tests for DriveClient requiring network access."""

    @pytest.fixture
    def client(self):
        """Create an authenticated DriveClient."""
        from vectrola.gdrive.auth import is_authenticated
        from vectrola.gdrive.client import DriveClient

        if not is_authenticated():
            pytest.skip("Not authenticated with Google Drive")

        return DriveClient()

    def test_get_user_info(self, client):
        """Test getting user info from real API."""
        user = client.get_user_info()

        assert "displayName" in user or "emailAddress" in user

    def test_get_quota(self, client):
        """Test getting storage quota from real API."""
        quota = client.get_quota()

        assert "limit" in quota or "usage" in quota

    def test_list_root_contents(self, client):
        """Test listing root folder contents."""
        results = list(client.list_contents("/"))

        # Root folder should exist and have some contents
        assert isinstance(results, list)

    def test_resolve_nonexistent_path(self, client):
        """Test resolving a path that doesn't exist."""
        result = client.resolve_path("/This/Path/Does/Not/Exist/12345")

        assert result is None
