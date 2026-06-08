"""Tests for the MCP server."""

import pytest


class TestMCPServer:
    """Test MCP server tools."""

    def test_server_import(self):
        """Test that the MCP server can be imported."""
        from vectrola.mcp.server import mcp

        assert mcp.name == "vectrola"

    def test_tools_registered(self):
        """Test that all expected tools are registered."""
        from vectrola.mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]

        assert "search_music" in tool_names
        assert "find_similar" in tool_names
        assert "get_track_info" in tool_names
        assert "list_tracks" in tool_names
        assert "library_stats" in tool_names

    @pytest.mark.network
    def test_library_stats_returns_string(self):
        """Test that library_stats returns a string."""
        from vectrola.mcp.server import library_stats

        result = library_stats()
        assert isinstance(result, str)
        # Should contain either stats or an error message
        assert "VECTROLA" in result or "Error" in result or "No tracks" in result

    @pytest.mark.network
    def test_search_music_returns_string(self):
        """Test that search_music returns a string."""
        from vectrola.mcp.server import search_music

        result = search_music("test query", limit=1)
        assert isinstance(result, str)

    @pytest.mark.network
    def test_list_tracks_returns_string(self):
        """Test that list_tracks returns a string."""
        from vectrola.mcp.server import list_tracks

        result = list_tracks(limit=5)
        assert isinstance(result, str)

    def test_search_music_validates_limit(self):
        """Test that search_music validates limit parameter."""
        from vectrola.mcp.server import search_music

        # This shouldn't crash even with extreme values
        # (validation happens inside the function)
        try:
            search_music("test", limit=-1)
            search_music("test", limit=1000)
        except Exception as e:
            # Network errors are OK, validation errors are not
            assert "limit" not in str(e).lower()

    def test_search_music_validates_mode(self):
        """Test that search_music handles invalid mode gracefully."""
        from vectrola.mcp.server import search_music

        # Invalid mode should default to "hybrid", not crash
        try:
            search_music("test", mode="invalid_mode")
        except Exception as e:
            # Network errors are OK
            assert "mode" not in str(e).lower()
