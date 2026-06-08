"""
Vectrola MCP Server - Claude Code integration for music knowledge graph.

Exposes semantic search, similarity finding, and library statistics
to Claude Code via the Model Context Protocol.

Usage:
    # Run directly
    python -m vectrola.mcp.server

    # Or via mcp CLI
    mcp run vectrola/mcp/server.py
"""

from collections import Counter
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    "vectrola",
    instructions="Vectrola is a multimodal music knowledge graph. Use search_music to find songs by vibe/mood/description, find_similar to discover related tracks, and library_stats for overview.",
)


@mcp.tool()
def search_music(
    query: str,
    limit: int = 5,
    mode: str = "hybrid",
) -> str:
    """
    Search the music library by vibe, mood, or description.

    Use this to find songs matching a feeling, theme, or description.
    Supports hybrid search (lyrics + audio), lyrics-only, or audio-only modes.

    Args:
        query: Natural language search query.
               Examples: "melancholic songs about heartbreak",
                        "upbeat Hindi party songs",
                        "romantic Bollywood duets"
        limit: Maximum number of results to return (default: 5, max: 20)
        mode: Search mode - "hybrid" (default, best results),
              "lyrics" (text/semantic only), or "audio" (acoustic only)

    Returns:
        Formatted search results with track info, moods, themes, and scores.
    """
    # Validate inputs
    limit = min(max(1, limit), 20)
    if mode not in ("hybrid", "lyrics", "audio"):
        mode = "hybrid"

    try:
        from vectrola.search.semantic import SemanticSearch

        searcher = SemanticSearch()
        results = searcher.search(query, limit=limit, mode=mode)
    except Exception as e:
        return f"Error searching: {e}\n\nMake sure Qdrant is running (docker run -d -p 6333:6333 qdrant/qdrant)"

    if not results:
        return f"No tracks found matching: '{query}'"

    output = [f"Search results for: '{query}' (mode: {mode})\n"]

    for i, r in enumerate(results, 1):
        artists = ", ".join(r.artists) if r.artists else "Unknown Artist"
        output.append(f"{i}. {artists} - {r.title}")
        output.append(f"   Score: {r.score:.3f}")

        if r.movie and r.movie != r.album:
            output.append(f"   Movie: {r.movie}")

        if r.moods:
            output.append(f"   Moods: {', '.join(r.moods)}")

        if r.themes:
            output.append(f"   Themes: {', '.join(r.themes)}")

        if r.narrative:
            # Truncate long narratives
            narrative = r.narrative[:150] + "..." if len(r.narrative) > 150 else r.narrative
            output.append(f"   Narrative: {narrative}")

        output.append("")  # Blank line between results

    return "\n".join(output)


@mcp.tool()
def find_similar(
    track_name: str,
    limit: int = 5,
    mode: str = "audio",
) -> str:
    """
    Find tracks similar to a given track.

    Use this to discover songs that sound similar (audio mode) or
    have similar themes/lyrics (lyrics mode).

    Args:
        track_name: Name or partial name of the track to find similar tracks for.
                   Case-insensitive partial matching is used.
        limit: Maximum number of similar tracks to return (default: 5, max: 20)
        mode: Similarity mode - "audio" (acoustic similarity, default) or
              "lyrics" (thematic/lyrical similarity)

    Returns:
        List of similar tracks with similarity scores.
    """
    limit = min(max(1, limit), 20)
    if mode not in ("audio", "lyrics"):
        mode = "audio"

    try:
        from vectrola.search.semantic import SemanticSearch
        from vectrola.storage.qdrant import get_db

        db = get_db()
        tracks = db.list_all(limit=500)
    except Exception as e:
        return f"Error connecting to database: {e}"

    # Find matching track by name (case-insensitive partial match)
    matching_path = None
    matching_title = None

    for t in tracks:
        title = t.payload.get("title", "")
        if track_name.lower() in title.lower():
            matching_path = t.payload.get("file_path")
            matching_title = title
            break

    if not matching_path:
        # List some available tracks as suggestions
        available = [t.payload.get("title", "Unknown") for t in tracks[:10]]
        return f"Track not found: '{track_name}'\n\nAvailable tracks include:\n" + "\n".join(f"  - {t}" for t in available)

    searcher = SemanticSearch()
    results = searcher.find_similar(matching_path, limit=limit, mode=mode)

    if not results:
        msg = "No similar tracks found."
        if mode == "audio":
            msg += "\n\nTip: Make sure tracks have audio embeddings. Run: python scripts/add_audio_embeddings.py"
        return msg

    mode_label = "acoustically" if mode == "audio" else "lyrically"
    output = [f"Tracks {mode_label} similar to: {matching_title}\n"]

    for i, r in enumerate(results, 1):
        artists = ", ".join(r.artists) if r.artists else "Unknown Artist"
        output.append(f"{i}. {artists} - {r.title}")
        output.append(f"   Similarity: {r.score:.3f}")

        if r.moods:
            output.append(f"   Moods: {', '.join(r.moods)}")

        output.append("")

    return "\n".join(output)


@mcp.tool()
def get_track_info(track_name: str) -> str:
    """
    Get detailed information about a specific track.

    Args:
        track_name: Name or partial name of the track (case-insensitive)

    Returns:
        Detailed track information including metadata, moods, themes, and narrative.
    """
    try:
        from vectrola.storage.qdrant import get_db

        db = get_db()
        tracks = db.list_all(limit=500)
    except Exception as e:
        return f"Error connecting to database: {e}"

    # Find matching track
    matching = None
    for t in tracks:
        title = t.payload.get("title", "")
        if track_name.lower() in title.lower():
            matching = t.payload
            break

    if not matching:
        return f"Track not found: '{track_name}'"

    output = [f"Track: {matching.get('title', 'Unknown')}\n"]

    artists = matching.get("artists", [])
    if artists:
        output.append(f"Artist(s): {', '.join(artists)}")

    if matching.get("album"):
        output.append(f"Album: {matching['album']}")

    if matching.get("movie") and matching.get("movie") != matching.get("album"):
        output.append(f"Movie: {matching['movie']}")

    if matching.get("year"):
        output.append(f"Year: {matching['year']}")

    if matching.get("composer"):
        output.append(f"Composer: {matching['composer']}")

    if matching.get("lyricist"):
        output.append(f"Lyricist: {matching['lyricist']}")

    if matching.get("language"):
        output.append(f"Language: {matching['language']}")

    output.append("")

    if matching.get("moods"):
        output.append(f"Moods: {', '.join(matching['moods'])}")

    if matching.get("themes"):
        output.append(f"Themes: {', '.join(matching['themes'])}")

    if matching.get("imagery"):
        output.append(f"Imagery: {', '.join(matching['imagery'])}")

    if matching.get("narrative"):
        output.append(f"\nNarrative: {matching['narrative']}")

    if matching.get("lyrics"):
        lyrics = matching["lyrics"]
        preview = lyrics[:500] + "..." if len(lyrics) > 500 else lyrics
        output.append(f"\nLyrics Preview:\n{preview}")

    return "\n".join(output)


@mcp.tool()
def list_tracks(
    limit: int = 20,
    filter_mood: Optional[str] = None,
    filter_theme: Optional[str] = None,
) -> str:
    """
    List tracks in the music library with optional filtering.

    Args:
        limit: Maximum number of tracks to list (default: 20, max: 100)
        filter_mood: Optional mood to filter by (e.g., "melancholic", "romantic")
        filter_theme: Optional theme to filter by (e.g., "love", "separation")

    Returns:
        List of tracks with basic info.
    """
    limit = min(max(1, limit), 100)

    try:
        from vectrola.storage.qdrant import get_db

        db = get_db()
        tracks = db.list_all(limit=500)  # Get more than needed for filtering
    except Exception as e:
        return f"Error connecting to database: {e}"

    if not tracks:
        return "No tracks indexed yet. Run 'vectrola ingest /path/to/music' first."

    # Apply filters
    filtered = []
    for t in tracks:
        payload = t.payload

        if filter_mood:
            moods = [m.lower() for m in payload.get("moods", [])]
            if filter_mood.lower() not in moods:
                continue

        if filter_theme:
            themes = [th.lower() for th in payload.get("themes", [])]
            if filter_theme.lower() not in themes:
                continue

        filtered.append(payload)

        if len(filtered) >= limit:
            break

    if not filtered:
        filters_used = []
        if filter_mood:
            filters_used.append(f"mood='{filter_mood}'")
        if filter_theme:
            filters_used.append(f"theme='{filter_theme}'")
        return f"No tracks found with filters: {', '.join(filters_used)}"

    output = []
    filter_desc = ""
    if filter_mood or filter_theme:
        filters = []
        if filter_mood:
            filters.append(f"mood: {filter_mood}")
        if filter_theme:
            filters.append(f"theme: {filter_theme}")
        filter_desc = f" (filtered by {', '.join(filters)})"

    output.append(f"Library: {len(filtered)} tracks{filter_desc}\n")

    for i, t in enumerate(filtered, 1):
        artists = ", ".join(t.get("artists", [])) or "Unknown"
        title = t.get("title", "Unknown")
        moods = ", ".join(t.get("moods", [])[:2]) if t.get("moods") else ""

        line = f"{i}. {artists} - {title}"
        if moods:
            line += f" [{moods}]"
        output.append(line)

    return "\n".join(output)


@mcp.tool()
def library_stats() -> str:
    """
    Get statistics about the indexed music library.

    Returns comprehensive stats including:
    - Total track count
    - Top moods and their frequencies
    - Top themes and their frequencies
    - Language distribution
    - Presence of audio embeddings

    Returns:
        Formatted library statistics.
    """
    try:
        from vectrola.storage.qdrant import get_db

        db = get_db()

        if not db.is_connected():
            return "Error: Cannot connect to Qdrant.\nStart it with: docker run -d -p 6333:6333 qdrant/qdrant"

        tracks = db.list_all(limit=1000)
    except Exception as e:
        return f"Error connecting to database: {e}"

    if not tracks:
        return "No tracks indexed yet.\n\nTo get started:\n1. Start Qdrant: docker run -d -p 6333:6333 qdrant/qdrant\n2. Run: vectrola ingest /path/to/music"

    mood_counter: Counter = Counter()
    theme_counter: Counter = Counter()
    language_counter: Counter = Counter()
    has_audio_embedding = 0

    for t in tracks:
        payload = t.payload

        for mood in payload.get("moods", []):
            mood_counter[mood] += 1

        for theme in payload.get("themes", []):
            theme_counter[theme] += 1

        lang = payload.get("language", "Unknown")
        language_counter[lang] += 1

        # Check for audio embedding via vectors
        if hasattr(t, "vector") and t.vector and "acoustic_clap" in (t.vector or {}):
            has_audio_embedding += 1

    output = [
        "═" * 40,
        "        VECTROLA LIBRARY STATISTICS",
        "═" * 40,
        "",
        f"Total Tracks: {len(tracks)}",
        f"With Audio Embeddings: {has_audio_embedding}",
        "",
        "─" * 40,
        "TOP MOODS",
        "─" * 40,
    ]

    for mood, count in mood_counter.most_common(8):
        bar = "█" * min(count, 20)
        output.append(f"  {mood:20} {bar} ({count})")

    output.extend([
        "",
        "─" * 40,
        "TOP THEMES",
        "─" * 40,
    ])

    for theme, count in theme_counter.most_common(8):
        bar = "█" * min(count, 20)
        output.append(f"  {theme:20} {bar} ({count})")

    output.extend([
        "",
        "─" * 40,
        "LANGUAGES",
        "─" * 40,
    ])

    for lang, count in language_counter.most_common(5):
        output.append(f"  {lang}: {count}")

    output.append("")
    output.append("═" * 40)

    return "\n".join(output)


# Resources - expose library data as read-only resources

@mcp.resource("vectrola://stats")
def stats_resource() -> str:
    """Current library statistics."""
    return library_stats()


@mcp.resource("vectrola://tracks")
def tracks_resource() -> str:
    """List of all indexed tracks."""
    return list_tracks(limit=100)


# Entry point
def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
