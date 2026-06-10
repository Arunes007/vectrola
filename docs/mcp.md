# Day 5: MCP Server for Claude Code Integration

## What Was Added

### 1. MCP Server (`vectrola/mcp/server.py`)

A FastMCP server that exposes Vectrola's music knowledge graph to Claude Code.

**Tools provided:**

| Tool | Description |
|------|-------------|
| `search_music` | Search by vibe/mood/description (hybrid, lyrics, or audio mode) |
| `find_similar` | Find acoustically or lyrically similar tracks |
| `get_track_info` | Get detailed metadata for a specific track |
| `list_tracks` | List library tracks with optional mood/theme filtering |
| `library_stats` | Get library statistics (moods, themes, languages) |

**Resources provided:**

| Resource URI | Description |
|--------------|-------------|
| `vectrola://stats` | Current library statistics |
| `vectrola://tracks` | List of all indexed tracks |

### 2. Package Entry Point

New CLI command: `vectrola-mcp` runs the MCP server directly.

## Setup Instructions

### Step 1: Install MCP Dependencies

```bash
conda activate nlp
pip install "mcp[cli]"
```

### Step 2: Test the Server

```bash
# Verify tools are registered
python -c "from vectrola.mcp.server import mcp; print([t.name for t in mcp._tool_manager._tools.values()])"
# Output: ['search_music', 'find_similar', 'get_track_info', 'list_tracks', 'library_stats']
```

### Step 3: Configure Claude Code

Add to your Claude Code settings (`~/.claude/settings.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "vectrola": {
      "command": "conda",
      "args": ["run", "-n", "nlp", "python", "-m", "vectrola.mcp.server"],
      "cwd": "/path/to/your/vectrola"
    }
  }
}
```

Or if using the installed package directly:

```json
{
  "mcpServers": {
    "vectrola": {
      "command": "vectrola-mcp"
    }
  }
}
```

### Step 4: Restart Claude Code

After configuring, restart Claude Code to connect to the MCP server.

## Usage Examples

Once connected, you can ask Claude:

```
Search for melancholic songs about heartbreak
```

```
Find tracks similar to "Tum Hi Ho"
```

```
Show me library statistics
```

```
List all romantic songs in the library
```

```
Get details about the song "Ae Dil Hai Mushkil"
```

## Tool Details

### search_music

```
Arguments:
  - query (str): Natural language search query
  - limit (int, default=5): Max results (1-20)
  - mode (str, default="hybrid"): "hybrid", "lyrics", or "audio"

Example: search_music("upbeat party songs", limit=10, mode="hybrid")
```

### find_similar

```
Arguments:
  - track_name (str): Name or partial name of reference track
  - limit (int, default=5): Max results (1-20)
  - mode (str, default="audio"): "audio" or "lyrics"

Example: find_similar("Tum Hi Ho", limit=5, mode="audio")
```

### get_track_info

```
Arguments:
  - track_name (str): Name or partial name of track

Example: get_track_info("Bekhayali")
```

### list_tracks

```
Arguments:
  - limit (int, default=20): Max tracks (1-100)
  - filter_mood (str, optional): Filter by mood
  - filter_theme (str, optional): Filter by theme

Example: list_tracks(limit=10, filter_mood="romantic")
```

### library_stats

```
Arguments: None

Returns: Library statistics including track count, top moods/themes, languages
```

## Architecture

```
Claude Code
    │
    ▼
MCP Protocol (stdio)
    │
    ▼
FastMCP Server (vectrola/mcp/server.py)
    │
    ├──▶ SemanticSearch (search_music, find_similar)
    │         │
    │         ├──▶ TextEmbedder (paraphrase-multilingual-MiniLM-L12-v2)
    │         ├──▶ AudioEmbedder (CLAP)
    │         └──▶ Qdrant (hybrid RRF search)
    │
    └──▶ VectrolaDB (get_track_info, list_tracks, library_stats)
              │
              └──▶ Qdrant (metadata queries)
```

## Requirements

- **Qdrant** must be running: `docker run -d -p 6333:6333 qdrant/qdrant`
- **Ollama** must be running for ingestion: `ollama serve`
- Music must be ingested first: `vectrola ingest /path/to/music`

## Troubleshooting

### "Cannot connect to Qdrant"

Start Qdrant:
```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

### "No tracks indexed"

Ingest some music first:
```bash
vectrola ingest /path/to/music/folder
```

### "No audio embeddings found"

Run the audio embedding script:
```bash
python scripts/add_audio_embeddings.py
```

### MCP server not connecting

1. Check the command works directly:
   ```bash
   conda run -n nlp python -m vectrola.mcp.server
   ```

2. Verify the path in settings.json is correct

3. Restart Claude Code after configuration changes
