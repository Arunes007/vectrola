# Day 3: CLAP Audio Embeddings + Hybrid Search

## What Was Added

### 1. CLAP Audio Embeddings (`vectrola/ingest/embeddings.py`)
- `AudioEmbedder` class using `laion/clap-htsat-unfused`
- 512-dim audio embeddings from 10s audio segments
- Cross-modal text→audio embedding (e.g., "dark ambient" → audio space)

### 2. Hybrid Search (`vectrola/search/semantic.py`)
- **3 search modes:**
  - `lyrics` - Text embeddings only (Day 2 compat)
  - `audio` - Acoustic embeddings only (CLAP)
  - `hybrid` - RRF fusion of both (default)
- `find_similar()` with acoustic/lyrical similarity modes

### 3. CLI Commands (`vectrola/cli.py`)
- `vectrola search "query" --mode hybrid|lyrics|audio`
- `vectrola similar "track name" --mode audio|lyrics`

### 4. Migration Scripts (`scripts/`)
- `add_acoustic_vector.py` - Add acoustic_clap vector to Qdrant collection
- `add_audio_embeddings.py` - Generate CLAP embeddings for existing tracks

## Setup Instructions

### Step 1: Add Acoustic Vector to Qdrant
```bash
conda activate nlp
python scripts/add_acoustic_vector.py
```

### Step 2: Generate Audio Embeddings for Existing Tracks
```bash
# Test with 3 tracks first (CLAP model loads ~10s)
python scripts/add_audio_embeddings.py 3

# Then run on all tracks (~30-60s per track)
python scripts/add_audio_embeddings.py
```

### Step 3: Test Hybrid Search
```bash
# Hybrid search (lyrics + audio via RRF)
vectrola search "melancholic sad song" --mode hybrid

# Acoustic similarity
vectrola similar "Tum Hi Ho" --mode audio

# Lyrical similarity (Day 2 mode)
vectrola similar "Tum Hi Ho" --mode lyrics
```

## Performance Notes

- **CLAP model load**: ~10s (first time only)
- **Per-track embedding**: ~2-5s (10s audio segment)
- **Search latency**: ~150ms hybrid, ~100ms single-mode

## Architecture

```
Query: "dark ambient song about loneliness"
         │
         ├──▶ Text Embedder (384-dim) ──▶ Lyrics Vector
         │
         └──▶ CLAP Text→Audio (512-dim) ──▶ Audio Vector
                                │
                                ▼
                        Qdrant RRF Fusion
                        (Reciprocal Rank)
                                │
                                ▼
                          Top K Results
```

## Next Steps (Optional)

- Day 4: Obsidian wiki generation
- Day 5: MCP server for Claude Code integration
- Improve search: Re-run with improved mood embeddings (see `scripts/resynthesize.py`)
