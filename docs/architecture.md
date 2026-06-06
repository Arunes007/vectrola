# Architecture Overview

## System Design

Vectrola processes audio files through a multi-stage pipeline that extracts both acoustic and semantic information.

## Day 1 Architecture (Complete ✅)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Audio File    │────▶│   File Tags     │────▶│    LRClib       │
│   (MP3/FLAC)    │     │   (mutagen)     │     │  (Lyrics API)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
        ┌───────────────────────────────────────────────┤
        │                                               │
        ▼                                               ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  MusicBrainz    │     │    Whisper      │     │     Ollama      │
│ (Composer etc)  │     │  (Fallback)     │     │  (LLM Synthesis)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        └───────────────────────┴───────────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │   TrackAnalysis │
                        │   - title       │
                        │   - artists     │
                        │   - album/movie │
                        │   - composer    │
                        │   - lyricist    │
                        │   - lyrics      │
                        │   - themes      │
                        │   - moods       │
                        │   - narrative   │
                        │   - imagery     │
                        └─────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │  Write to File  │
                        │  (ID3/FLAC tags)│
                        └─────────────────┘
```

### Day 1 Pipeline Priority

1. **Read file tags** - Use existing metadata if complete
2. **LRClib** - Fetch lyrics + album/movie info (fast, accurate, free)
3. **MusicBrainz** - Get composer, lyricist, year
4. **Whisper fallback** - Transcribe if lyrics not found online
5. **Ollama synthesis** - Extract themes, moods, narrative, imagery
6. **Write tags** - Save analysis to file tags

## Full Architecture (Day 1-5)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           VECTROLA                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │  Audio File  │───▶│  Ingest      │───▶│   Qdrant     │               │
│  │  (MP3/FLAC)  │    │  Pipeline    │    │  (Vectors)   │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                             │                    │                       │
│         ┌───────────────────┼────────────────────┘                       │
│         │                   │                                            │
│         ▼                   ▼                                            │
│  ┌──────────────┐    ┌──────────────┐                                   │
│  │   Obsidian   │    │  MCP Server  │                                   │
│  │  Wiki Vault  │    │ (Claude Code)│                                   │
│  │  (Markdown)  │    │              │                                   │
│  └──────────────┘    └──────────────┘                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
vectrola/
├── pyproject.toml              # Package dependencies
├── pytest.ini                  # Test configuration
├── README.md                   # Quick start guide
├── CLAUDE.md                   # AI assistant context
├── docs/                       # Documentation
│   ├── architecture.md         # This file
│   ├── whisper.md              # Whisper deep dive
│   ├── ollama.md               # Ollama deep dive
│   ├── lyrics.md               # Lyrics fetching
│   └── cli.md                  # CLI reference
├── vectrola/
│   ├── __init__.py
│   ├── cli.py                  # Typer CLI
│   ├── config.py               # Configuration
│   ├── ingest/
│   │   ├── transcribe.py       # Whisper transcription
│   │   ├── synthesis.py        # Ollama LLM extraction
│   │   ├── lyrics.py           # LRClib + Genius fetcher
│   │   ├── metadata.py         # MusicBrainz fetcher
│   │   ├── stems.py            # Demucs vocal separation
│   │   └── pipeline.py         # Orchestration
│   ├── storage/
│   │   ├── tags.py             # Audio file tag I/O
│   │   ├── qdrant.py           # Vector database (Day 2)
│   │   └── wiki.py             # Markdown generation (Day 4)
│   ├── search/
│   │   └── semantic.py         # Hybrid search (Day 2-3)
│   └── mcp/
│       └── server.py           # Claude Code integration (Day 5)
├── wiki/                       # Generated Obsidian vault (Day 4)
└── tests/                      # Test suite
    ├── test_lyrics.py          # Lyrics fetcher tests
    ├── test_metadata.py        # Metadata fetcher tests
    ├── test_synthesis.py       # Ollama synthesis tests
    ├── test_tags.py            # File tags tests
    └── test_pipeline.py        # Pipeline integration tests
```

## Data Flow

### Ingestion Pipeline

1. **Read File Tags**: Check existing ID3/FLAC metadata
2. **Fetch Lyrics**: LRClib → Genius → Whisper (fallback chain)
3. **Fetch Metadata**: MusicBrainz for composer, lyricist, year
4. **Synthesis**: Ollama extracts themes, moods, narrative from lyrics
5. **Embedding** (Day 2-3): Generate vectors for lyrics + audio
6. **Storage**: Save to Qdrant + write tags to file
7. **Wiki** (Day 4): Generate markdown pages with wikilinks

### Search Flow (Day 2-3)

1. **Query**: User enters natural language query
2. **Embed**: Convert query to vector(s)
3. **Search**: Qdrant hybrid search (lyrics + acoustic)
4. **Rank**: Reciprocal Rank Fusion combines results
5. **Return**: Top matches with relevance scores

## Key Design Decisions

### Lyrics-First Approach

For Bollywood and Hindi music, online lyrics (LRClib) are far more accurate than Whisper transcription:
- Proper Devanagari script (not Urdu transliteration)
- Correct spelling and punctuation
- Includes album/movie metadata

Whisper is only used as a fallback for obscure songs not in LRClib.

### Single Qdrant Collection with Named Vectors

Instead of separate collections for lyrics and audio, we use one collection with named vectors:

```python
vectors_config={
    "lyrics_dense": VectorParams(size=384),   # sentence-transformers
    "acoustic_clap": VectorParams(size=512)   # CLAP audio embeddings
}
```

This enables true multimodal search with Reciprocal Rank Fusion in a single query.

### Lazy Model Loading

All ML models are loaded lazily (on first use) to minimize startup time and memory:

```python
@property
def whisper(self):
    if self._whisper is None:
        self._whisper = WhisperModel(...)
    return self._whisper
```

### Local-First Design

- **Ollama**: Local LLM, no API keys needed
- **Qdrant**: Can run locally via Docker
- **Privacy**: Your music data never leaves your machine

## Metadata Sources

| Source | Data Provided | Priority |
|--------|--------------|----------|
| File Tags | title, artist, album, year | 1 (if complete) |
| LRClib | lyrics, artist, album/movie, duration | 2 |
| MusicBrainz | composer, lyricist, year, genres | 3 |
| Whisper | lyrics (transcribed) | 4 (fallback) |
| Ollama | themes, moods, narrative, imagery | Always |
