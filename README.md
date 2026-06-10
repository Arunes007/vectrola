# Vectrola

🎧 **Multimodal Music Knowledge Graph**

Semantic music search using audio embeddings and LLM synthesis. Query your music library with natural language like *"upbeat 80s synth with rain themes"* instead of rigid metadata tags.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Features

- **Lyrics Transcription**: Automatic speech-to-text using Whisper
- **Semantic Analysis**: Extract themes, moods, and narrative using local LLMs (Ollama)
- **Vector Search**: Find music by meaning, not just metadata
- **Acoustic Similarity**: Find songs that *sound* similar using CLAP audio embeddings
- **Obsidian Wiki**: Generate a browsable knowledge graph with interactive audio player
- **Claude Code Integration**: MCP server for seamless AI assistant workflows

## Quick Start

### Prerequisites

Before you begin, make sure you have:

1. **Python 3.10+** installed
2. **Qdrant** vector database running:
   ```bash
   docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
   ```
3. **Ollama** running locally with a model:
   ```bash
   ollama serve
   ollama pull qwen2.5:3b  # Or llama3.2:1b for faster results
   ```

### Installation

```bash
# Clone the repository
git clone https://github.com/Arunes007/vectrola.git
cd vectrola

# Install with all features
pip install -e ".[full]"

# Or install base features only
pip install -e .
```

### API Keys Setup (Optional)

Some features require API keys. Copy the example environment file and add your keys:

```bash
cp .env.example .env
# Edit .env and add your API keys:
# - YouTube API: https://console.cloud.google.com/apis/credentials
# - Genius API: https://genius.com/api-clients
```

Note: Genius API token is optional - lyrics can be fetched from LRClib without authentication, with Whisper transcription as a fallback.

### Usage

```bash
# Check system status
vectrola status

# Analyze a single file (preview, no changes)
vectrola analyze ~/Music/song.mp3

# Ingest files and write metadata to tags
vectrola ingest ~/Music/

# Search by vibe/mood
vectrola search "melancholic sad song"

# Find similar tracks
vectrola similar "Tum Hi Ho"

# Generate Obsidian wiki
vectrola wiki
```

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Semantic Search Guide](docs/search.md)
- [Qdrant Vector Database](docs/qdrant.md)
- [Lyrics Fetching](docs/lyrics.md)
- [CLAP Audio Embeddings](docs/clap.md)
- [Obsidian Wiki with Audio Player](docs/wiki.md)
- [MCP Server for Claude Code](docs/mcp.md)
- [CLI Reference](docs/cli.md)
- [Testing Guide](docs/testing.md)

## Project Status

| Day | Feature | Status |
|-----|---------|--------|
| 1 | Transcription + LLM Synthesis | ✅ Complete |
| 2 | Vector Database (Qdrant) | ✅ Complete |
| 3 | Audio Embeddings (CLAP) | ✅ Complete |
| 4 | Wiki Generation (Obsidian) | ✅ Complete |
| 5 | Claude Code Integration (MCP) | ✅ Complete |
| 6 | Interactive Audio Player | ✅ Complete |
| 7 | Feature Completion & Polish | ⏳ In Progress |

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on:

- Setting up your development environment
- Running tests
- Code style guidelines
- Submitting pull requests

Check out our [open issues](https://github.com/Arunes007/vectrola/issues) for ideas on where to start.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
