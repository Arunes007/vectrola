# Vectrola

🎧 **Multimodal Music Knowledge Graph**

Semantic music search using audio embeddings and LLM synthesis. Query your music library with natural language like *"upbeat 80s synth with rain themes"* instead of rigid metadata tags.

## Features

- **Lyrics Transcription**: Automatic speech-to-text using Whisper
- **Semantic Analysis**: Extract themes, moods, and narrative using local LLMs
- **Vector Search**: Find music by meaning, not just metadata (coming soon)
- **Acoustic Similarity**: Find songs that *sound* similar (coming soon)
- **Obsidian Wiki**: Generate a browsable knowledge graph of your music (coming soon)

## Quick Start

```bash
# Install
pip install -e .

# Check dependencies
vectrola status

# Analyze a single file (preview, no changes)
vectrola analyze ~/Music/song.mp3

# Ingest files and write metadata to tags
vectrola ingest ~/Music/
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/download) running locally
- Ollama model: `ollama pull llama3.2:1b`

## Documentation

- [Architecture Overview](docs/architecture.md)
- [How Whisper Works](docs/whisper.md)
- [How Ollama Works](docs/ollama.md)
- [CLI Reference](docs/cli.md)

## Project Status

| Day | Feature | Status |
|-----|---------|--------|
| 1 | Transcription + LLM Synthesis | ✅ Complete |
| 2 | Vector Database (Qdrant) | 🔄 In Progress |
| 3 | Audio Embeddings (CLAP) | ⏳ Planned |
| 4 | Wiki Generation (Obsidian) | ⏳ Planned |
| 5 | Claude Code Integration (MCP) | ⏳ Planned |

## License

MIT
