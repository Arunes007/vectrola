# CLAP Audio Embeddings

Vectrola uses CLAP (Contrastive Language-Audio Pretraining) for acoustic similarity search. CLAP creates audio embeddings that are aligned with text embeddings, enabling cross-modal search.

## What is CLAP?

CLAP is a neural network trained to align audio and text in the same embedding space. This means:

- You can search for "dark ambient drone" and find matching audio
- Audio embeddings can be compared directly with text descriptions
- Enables true multimodal search (lyrics + sound texture)

**Model**: `laion/clap-htsat-unfused` (512 dimensions)

## How It Works

### Audio Embedding

```python
from vectrola.ingest.embeddings import get_audio_embedder

embedder = get_audio_embedder()

# Generate 512-dim embedding from audio file
# Uses 10s segment from middle of track (skip intro)
audio_vector = embedder.embed_audio(
    audio_path="/path/to/song.mp3",
    duration=10.0,   # seconds
    offset=30.0      # skip first 30s
)
```

### Text→Audio Embedding

The magic of CLAP is text descriptions produce embeddings in the **audio space**:

```python
# Text description → audio-space embedding
audio_vector = embedder.embed_text("slow piano with rain sounds")

# Now search for audio that matches this description
results = db.search_by_audio(audio_vector)
```

## Usage

### Acoustic Similarity

Find songs that **sound** similar (not just similar lyrics):

```bash
vectrola similar "Tum Hi Ho" --mode audio
```

Returns tracks with similar:
- Instrumentation
- Tempo
- Energy level
- Acoustic texture

### Audio-Only Search

Search by sound description:

```bash
vectrola search "dark ambient with strings" --mode audio
```

### Hybrid Search (Default)

Combines lyrics semantics + acoustic texture using **Reciprocal Rank Fusion**:

```bash
vectrola search "melancholic piano song about rain" --mode hybrid
```

This finds songs that match BOTH:
- Lyrical themes (rain, melancholy)
- Acoustic texture (piano, slow)

## Hybrid Search Architecture

```
User Query: "sad piano song about time"
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
Text Embedder (384-dim)    CLAP Text→Audio (512-dim)
        │                       │
        ▼                       ▼
 Lyrics Vector            Audio Vector
        │                       │
        └───────────┬───────────┘
                    │
                    ▼
            Qdrant Collection
          (Named Vectors: Both!)
                    │
                    ▼
         Prefetch Top 20 from Each
                    │
                    ▼
        Reciprocal Rank Fusion (RRF)
                    │
                    ▼
              Top K Results
```

### Reciprocal Rank Fusion (RRF)

RRF combines rankings from multiple searches without needing to normalize scores:

```
RRF_score(track) = sum(1 / (k + rank_i))
```

Where:
- `k = 60` (constant)
- `rank_i` = rank in search i (lyrics or audio)

Tracks ranking high in **both** searches get the highest RRF scores.

## Adding Audio Embeddings to Existing Tracks

### Step 1: Add Vector to Qdrant Collection

```bash
python scripts/add_acoustic_vector.py
```

This adds the `acoustic_clap` named vector to your collection without losing existing data.

### Step 2: Generate Embeddings

```bash
# Test with 3 tracks
python scripts/add_audio_embeddings.py 3

# Run on all tracks
python scripts/add_audio_embeddings.py
```

**Performance**: ~2-5 seconds per track (10s audio segment)

## Python API

```python
from vectrola.search.semantic import SemanticSearch

searcher = SemanticSearch()

# Hybrid search (default)
results = searcher.search("sad piano song", mode="hybrid")

# Audio-only search
results = searcher.search("dark ambient drone", mode="audio")

# Acoustic similarity
results = searcher.find_similar("/path/to/song.mp3", mode="audio")

# Lyrical similarity (Day 2)
results = searcher.find_similar("/path/to/song.mp3", mode="lyrics")
```

## Requirements

- **transformers**: For CLAP model
- **torch**: PyTorch backend
- **librosa**: Audio loading
- **Qdrant**: Named vectors support

```bash
conda activate nlp
# Already installed in nlp environment
```

## Performance

| Operation | Time |
|-----------|------|
| CLAP model loading | ~10s (first time only) |
| Audio embedding (10s segment) | ~2-5s |
| Hybrid search (RRF) | ~150ms |
| Audio-only search | ~100ms |

## Model Details

**CLAP Model**: `laion/clap-htsat-unfused`
- **Size**: ~600MB download
- **Dimensions**: 512
- **Audio Sample Rate**: 48kHz
- **Input Length**: Variable (we use 10s)
- **Training**: Contrastive learning on audio-text pairs

## Troubleshooting

### "No acoustic_clap vector"

Run the migration scripts:
```bash
python scripts/add_acoustic_vector.py
python scripts/add_audio_embeddings.py
```

### Slow Embedding Generation

CLAP processes 10s audio segments. For 120 tracks:
- Total time: ~5-10 minutes
- Can't be parallelized (model is already using GPU/CPU fully)

### Model Download Fails

CLAP downloads from HuggingFace Hub (~600MB). If it fails:
```bash
# Pre-download manually
python -c "from transformers import ClapModel; ClapModel.from_pretrained('laion/clap-htsat-unfused')"
```

## Comparison: Lyrics vs Audio Search

### Lyrics Search (Day 2)
- Finds songs about similar **topics/themes**
- "heartbreak" → songs about breakups
- Language-aware (Hindi, English)

### Audio Search (Day 3)
- Finds songs that **sound** similar
- "slow piano" → acoustic piano tracks
- Language-agnostic (instrumental matches work)

### Hybrid (Day 3, Default)
- Best of both worlds
- "sad piano ballad" → songs that are BOTH sad in lyrics AND have piano
- Most accurate for complex queries
