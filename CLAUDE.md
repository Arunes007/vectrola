# Vectrola - AI Assistant Context

## What is this project?

Vectrola is a multimodal music knowledge graph that enables semantic search over music libraries using audio embeddings and LLM-synthesized metadata. It follows the Karpathy LLMWiki pattern - an agent-maintained compounding knowledge base.

## Tech Stack

- **Python 3.10+** with Typer CLI
- **faster-whisper**: Audio transcription (fallback)
- **SpotAPI**: Spotify metadata (no API key needed)
- **LRClib + Genius**: Lyrics sources
- **MusicBrainz**: Composer/lyricist fallback
- **Ollama**: Local LLM for semantic extraction (llama3.2:1b)
- **mutagen**: Read/write audio file tags
- **Qdrant**: Vector database for semantic search
- **sentence-transformers**: Multilingual text embeddings
- **CLAP**: Audio embeddings (Day 3)
- **FastMCP**: Claude Code integration (Day 5)

## Project Structure

```
vectrola/
├── vectrola/
│   ├── cli.py              # Typer CLI entry point
│   ├── config.py           # Settings
│   ├── ingest/
│   │   ├── transcribe.py   # Whisper (fallback)
│   │   ├── synthesis.py    # Ollama LLM
│   │   ├── lyrics.py       # LRClib + Genius
│   │   ├── spotify.py      # Spotify metadata (SpotAPI)
│   │   ├── metadata.py     # MusicBrainz
│   │   ├── embeddings.py   # Text embeddings
│   │   └── pipeline.py     # Orchestration
│   ├── storage/
│   │   ├── tags.py         # Audio file tags
│   │   ├── qdrant.py       # Vector database
│   │   └── wiki.py         # Obsidian wiki generator
│   ├── search/
│   │   └── semantic.py     # Semantic search
│   └── mcp/
│       └── server.py       # MCP server for Claude Code
├── docs/                   # Documentation
├── tests/                  # Test suite
└── wiki/                   # Generated Obsidian vault
```

## Key Commands

```bash
# Activate environment
conda activate nlp

# Check system status
vectrola status

# Ingest music files
vectrola ingest /path/to/music
vectrola ingest /path/to/song.mp3

# Search by vibe/mood
vectrola search "melancholic sad song"
vectrola search "romantic love duet"
vectrola search "upbeat party music"
```

## Current Status

- Day 1 ✅: Complete metadata pipeline
  - Spotify → LRClib → Genius → MusicBrainz → Whisper
  - Ollama synthesis (themes, moods, narrative)
  - Tag writing/reading
- Day 2 ✅: Vector search
  - Qdrant vector database
  - Multilingual embeddings (Hindi + English)
  - Semantic search by mood/theme
- Day 3 ✅: CLAP audio embeddings
  - CLAP audio embeddings (512-dim)
  - Hybrid RRF search (lyrics + audio)
  - Acoustic similarity search
  - `vectrola similar` command
- Day 4 ✅: Obsidian wiki generation
  - Markdown pages with wikilinks
  - Track, Artist, Mood, Theme, Movie pages
  - Graph visualization support
  - `vectrola wiki` command
- Day 5 ✅: MCP server for Claude Code
  - FastMCP server with 5 tools
  - search_music, find_similar, get_track_info
  - list_tracks, library_stats
  - Resources: vectrola://stats, vectrola://tracks
- Day 6 ✅: Interactive audio player
  - Spotify-like player bar in Obsidian wiki
  - Play/pause, prev/next, shuffle, progress bar
  - DataviewJS integration
  - Mood and theme pages with playback
- Day 7 ⏳: Feature completion & polish

## Day 2 Pipeline Flow

```
1. Read file tags (mutagen)
   ↓
2. Fetch metadata from Spotify (artist, album, year)
   ↓
3. Fetch lyrics (LRClib → Genius fallback)
   ↓
4. Fetch composer/lyricist (MusicBrainz)
   ↓
5. Whisper transcription (if no lyrics found)
   ↓
6. LLM synthesis (Ollama) → themes, moods, narrative
   ↓
7. Generate embedding (lyrics + moods + themes)
   ↓
8. Store in Qdrant
   ↓
9. Write tags to file
```

## Day 3 Pipeline Flow (Additional)

```
1-9. Same as Day 2
   ↓
10. Generate CLAP audio embedding (512-dim)
   ↓
11. Store in Qdrant with named vectors (lyrics_dense + acoustic_clap)
```

## Search Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Search Query   │────▶│   Embedders     │────▶│    Qdrant       │
│  "sad song"     │     │  Text + CLAP    │     │  (RRF Search)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │ │                       │
                    ┌─────────┘ └────────┐              │
                    ▼                    ▼              │
              Lyrics Vector         Audio Vector        │
              (384-dim)             (512-dim)           │
                    │                    │              │
                    └─────────┬──────────┘              │
                              ▼                         │
                    Reciprocal Rank Fusion ◀────────────┘
                              │
                              ▼
                         Top K Results
```

**Embedding Models:**
- **Text**: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim)
- **Audio**: `laion/clap-htsat-unfused` (512-dim)
- **Search**: Qdrant named vectors with RRF fusion

**Search Modes:**
- `lyrics` - Text embeddings only
- `audio` - CLAP embeddings only  
- `hybrid` - RRF fusion (default)

## Testing

```bash
# Unit tests only (fast)
pytest -m "not network and not ollama and not integration"

# All tests
pytest

# Specific module
pytest tests/test_search.py -v
```

## Requirements

### Qdrant (Vector Database)
```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

### Ollama (LLM)
```bash
ollama serve
ollama pull llama3.2:1b
```

## Documentation

See `docs/` folder:
- `architecture.md` - System design
- `search.md` - Semantic search guide
- `qdrant.md` - Vector database setup
- `lyrics.md` - Lyrics fetching
- `cli.md` - CLI reference
- `testing.md` - Test suite guide
- `mcp.md` - MCP server for Claude Code
- `wiki.md` - Obsidian wiki with audio player

## Known Issues

### Model Loading Slow (~12s)
First search loads the embedding model. Subsequent searches are fast (~100ms).

### All Songs Tagged "Melancholic"
The small `llama3.2:1b` model has mood bias. Consider using `llama3.2:3b` for better variety.

### LRClib Timeouts
Genius is used as automatic fallback when LRClib times out.
