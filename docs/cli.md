# CLI Reference

Vectrola provides a command-line interface for all operations.

## Commands

### `vectrola status`

Check if all components are working.

```bash
$ vectrola status

🎧 Vectrola Status

┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Component             ┃ Status                  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ faster-whisper        │ ✓                       │
│ Ollama                │ ✓ connected             │
│ mutagen               │ ✓                       │
│ Qdrant                │ ○ not installed (Day 2) │
│ sentence-transformers │ ○ not installed (Day 2) │
│ CLAP (transformers)   │ ✓                       │
└───────────────────────┴─────────────────────────┘
```

---

### `vectrola analyze <file>`

Analyze a single audio file and display results. Does NOT write to file tags.

```bash
$ vectrola analyze ~/Music/song.mp3

📀 Song Title

 Language  en                                                   
 Moods     melancholic, introspective                           
 Themes    mortality, longing, urban isolation                  
 Imagery   a rainy street, a distant memory, fading light       

Narrative:
  A reflection on lost love and the passage of time.

Lyrics Preview:
  The first 500 characters of transcribed lyrics...
```

**Use case**: Preview what Vectrola extracts before committing to file tags.

---

### `vectrola ingest <path>`

Process audio files and write metadata to their tags.

```bash
# Single file
$ vectrola ingest ~/Music/song.mp3

# Entire directory (recursive by default)
$ vectrola ingest ~/Music/

# Non-recursive (current directory only)
$ vectrola ingest ~/Music/ --no-recursive
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--recursive / -r` | `True` | Scan subdirectories |
| `--no-recursive / -R` | - | Only scan top-level directory |
| `--fast / -f` | `True` | Skip Demucs stem separation (faster) |
| `--slow / -s` | - | Use Demucs for vocal isolation (more accurate) |
| `--tags / --no-tags` | `True` | Write analysis to file tags |

**Example output:**

```bash
$ vectrola ingest ~/Music/Album/

Found 12 audio file(s)
Fast mode: skipping Demucs vocal separation
Ingesting... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%
  ✓ track01.mp3 → melancholic, introspective
  ✓ track02.mp3 → euphoric, energetic
  ✓ track03.flac → aggressive, rebellious
  ✗ track04.mp3: Error transcribing audio

Processed: 11 tracks
Errors: 1 tracks
```

---

### `vectrola search <query>` (Day 2+)

Search music by natural language description.

```bash
$ vectrola search "melancholic songs about time passing"

Results for: melancholic songs about time passing

1. Pink Floyd - Time (score: 0.92)
   Moods: melancholic, philosophical
2. Radiohead - Paranoid Android (score: 0.87)
   Moods: anxious, melancholic
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--limit / -n` | `5` | Number of results |
| `--hybrid / --lyrics-only` | `hybrid` | Search mode |

---

### `vectrola similar <track>` (Day 3+)

Find acoustically similar tracks.

```bash
$ vectrola similar "Pink Floyd - Time"

Acoustically similar to: Pink Floyd - Time

1. King Crimson - Epitaph (similarity: 0.89)
2. Yes - Close to the Edge (similarity: 0.84)
```

---

### `vectrola wiki` (Day 4+)

Generate Obsidian-compatible markdown wiki.

```bash
$ vectrola wiki --output ./wiki

Wiki generated at ./wiki
```

---

## Supported Audio Formats

- MP3 (`.mp3`)
- FLAC (`.flac`)
- WAV (`.wav`)
- M4A (`.m4a`)
- OGG (`.ogg`)

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | No files found / Error |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OLLAMA_HOST` | Ollama API URL (default: `http://localhost:11434`) |

## Examples

```bash
# Quick analysis of one song
vectrola analyze ~/Downloads/new_song.mp3

# Batch process entire music library
vectrola ingest ~/Music/ --recursive

# Process without writing tags (dry run)
vectrola ingest ~/Music/ --no-tags

# Check system status
vectrola status
```
