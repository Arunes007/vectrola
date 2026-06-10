# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-10

### Added

#### Day 1: Core Pipeline
- Initial release with metadata ingestion pipeline
- Spotify metadata fetching (via SpotAPI, no API key needed)
- Lyrics fetching from LRClib and Genius
- MusicBrainz integration for composer/lyricist data
- Whisper transcription fallback
- Ollama LLM synthesis for themes, moods, and narrative
- Audio file tag reading and writing with mutagen
- CLI with `vectrola ingest`, `vectrola analyze`, and `vectrola status` commands

#### Day 2: Vector Search
- Qdrant vector database integration
- Multilingual text embeddings (paraphrase-multilingual-MiniLM-L12-v2)
- Semantic search by mood/theme/lyrics
- `vectrola search` command

#### Day 3: Audio Embeddings
- CLAP audio embeddings (laion/clap-htsat-unfused, 512-dim)
- Hybrid RRF search (lyrics + audio)
- Acoustic similarity search
- `vectrola similar` command

#### Day 4: Obsidian Wiki
- Markdown wiki generation with wikilinks
- Track, Artist, Mood, Theme, and Movie pages
- Graph visualization support
- `vectrola wiki` command

#### Day 5: MCP Integration
- FastMCP server for Claude Code integration
- Five MCP tools: search_music, find_similar, get_track_info, list_tracks, library_stats
- Two resources: vectrola://stats, vectrola://tracks
- `vectrola-mcp` command

#### Day 6: Interactive Player
- Spotify-like player bar in Obsidian wiki
- Play/pause, prev/next, shuffle controls
- Progress bar with seek functionality
- DataviewJS integration for mood/theme pages

### Documentation
- Comprehensive docs for architecture, search, lyrics, MCP, wiki, and more
- Testing guide with pytest markers
- CLI reference

### Infrastructure
- pytest test suite with network/ollama/integration markers
- Ruff linting and formatting configuration
- Optional dependency groups (vectors, audio, mcp, full, dev)

## [Unreleased]

### Coming Soon
- Web UI
- Playlist generation
- Additional embedding models
- Support for more metadata sources

---

[0.1.0]: https://github.com/Arunes007/vectrola/releases/tag/v0.1.0
