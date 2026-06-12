"""Tests for authentication and user management."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from vectrola.config import get_current_user


class TestGetCurrentUser:
    """Tests for get_current_user() function."""

    def test_returns_tuple(self, tmp_path):
        """Should return (user_id, is_logged_in) tuple."""
        with patch.dict('os.environ', {'VECTROLA_USER_ID': 'test_user'}, clear=False):
            result = get_current_user()
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert isinstance(result[0], str)
            assert isinstance(result[1], bool)

    def test_env_var_takes_priority(self, tmp_path):
        """VECTROLA_USER_ID env var should take highest priority."""
        with patch.dict('os.environ', {'VECTROLA_USER_ID': 'env_user'}, clear=False):
            user_id, is_logged_in = get_current_user()
            assert user_id == 'env_user'
            assert is_logged_in is True

    def test_session_file_used_when_logged_in(self, tmp_path, monkeypatch):
        """Should use session.json when user is logged in."""
        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)

        session_path = config_dir / "session.json"
        session_path.write_text(json.dumps({
            "user_id": "logged_in_user@example.com",
            "logged_in_at": "2026-06-12T12:00:00Z"
        }))

        # Mock Path.home() to return tmp_path
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        # Clear env var
        with patch.dict('os.environ', {}, clear=True):
            user_id, is_logged_in = get_current_user()
            assert user_id == "logged_in_user@example.com"
            assert is_logged_in is True

    def test_anon_id_used_when_not_logged_in(self, tmp_path, monkeypatch):
        """Should use anon_id file when not logged in."""
        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)

        anon_path = config_dir / "anon_id"
        anon_path.write_text("anon_existing123")

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            user_id, is_logged_in = get_current_user()
            assert user_id == "anon_existing123"
            assert is_logged_in is False

    def test_generates_anon_id_on_first_run(self, tmp_path, monkeypatch):
        """Should generate new anon_id on first run."""
        config_dir = tmp_path / ".config" / "vectrola"
        # Don't create config_dir - simulate first run

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            user_id, is_logged_in = get_current_user()

            # Should generate anon ID
            assert user_id.startswith("anon_")
            assert len(user_id) == 17  # "anon_" + 12 hex chars
            assert is_logged_in is False

            # Should persist anon_id
            anon_path = config_dir / "anon_id"
            assert anon_path.exists()
            assert anon_path.read_text() == user_id

    def test_session_takes_priority_over_anon(self, tmp_path, monkeypatch):
        """Session should take priority over anon_id."""
        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)

        # Create both files
        session_path = config_dir / "session.json"
        session_path.write_text(json.dumps({"user_id": "session_user"}))

        anon_path = config_dir / "anon_id"
        anon_path.write_text("anon_ignored")

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            user_id, is_logged_in = get_current_user()
            assert user_id == "session_user"
            assert is_logged_in is True

    def test_handles_invalid_session_json(self, tmp_path, monkeypatch):
        """Should fall back to anon if session.json is corrupted."""
        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)

        session_path = config_dir / "session.json"
        session_path.write_text("not valid json{{{")

        anon_path = config_dir / "anon_id"
        anon_path.write_text("anon_fallback")

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            user_id, is_logged_in = get_current_user()
            assert user_id == "anon_fallback"
            assert is_logged_in is False

    def test_handles_empty_session_user_id(self, tmp_path, monkeypatch):
        """Should fall back to anon if session has empty user_id."""
        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)

        session_path = config_dir / "session.json"
        session_path.write_text(json.dumps({"user_id": ""}))

        anon_path = config_dir / "anon_id"
        anon_path.write_text("anon_fallback")

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            user_id, is_logged_in = get_current_user()
            assert user_id == "anon_fallback"
            assert is_logged_in is False


class TestGetOrCreateUserId:
    """Tests for backwards-compatible get_or_create_user_id() function."""

    def test_returns_string(self, tmp_path, monkeypatch):
        """Should return just the user_id string (not tuple)."""
        from vectrola.config import get_or_create_user_id

        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)
        (config_dir / "anon_id").write_text("anon_test123")

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            result = get_or_create_user_id()
            assert isinstance(result, str)
            assert result == "anon_test123"

    def test_backwards_compatible(self, tmp_path, monkeypatch):
        """Should work the same way as get_current_user()[0]."""
        from vectrola.config import get_or_create_user_id, get_current_user

        config_dir = tmp_path / ".config" / "vectrola"
        config_dir.mkdir(parents=True)
        (config_dir / "anon_id").write_text("anon_compat")

        monkeypatch.setattr(Path, 'home', lambda: tmp_path)

        with patch.dict('os.environ', {}, clear=True):
            old_result = get_or_create_user_id()
            new_result, _ = get_current_user()
            assert old_result == new_result
