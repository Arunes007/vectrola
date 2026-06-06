# Semantic Search

Vectrola uses vector embeddings for semantic search over your music library. You can search using natural language queries like "sad melancholic song about heartbreak" or "upbeat party music".

## How It Works

1. **Embedding**: Both lyrics and search queries are converted to 384-dimensional vectors using a multilingual sentence-transformer model
2. **Storage**: Vectors are stored in Qdrant (a vector database) along with track metadata
3. **Search**: Your query is embedded and compared against all stored vectors using Approximate Nearest Neighbor (ANN) search
4. **Ranking**: Results are ranked by cosine similarity score (0-1)

## Multilingual Support

Vectrola uses `paraphrase-multilingual-MiniLM-L12-v2` which supports 50+ languages including:
- Hindi (Devanagari)
- English
- Urdu
- Punjabi
- And many more

This means you can search in English ("sad love song") and find Hindi songs with matching themes!

## What Gets Embedded

For each track, we embed a combination of:
- **Lyrics** - The full lyrics text
- **Moods** - e.g., "melancholic", "euphoric"
- **Themes** - e.g., "longing", "heartbreak", "rebellion"
- **Narrative** - One-sentence story summary

This allows searching by both lyric content AND semantic mood/theme.

## CLI Usage

```bash
# Basic search
vectrola search "melancholic sad song"

# Limit results
vectrola search "romantic duet" --limit 10

# Search examples
vectrola search "party dance music"
vectrola search "heartbreak and longing"
vectrola search "90s bollywood romance"
```

## Search Tips

**Good queries:**
- Describe the mood: "sad", "happy", "energetic"
- Describe themes: "love", "heartbreak", "friendship"
- Combine multiple concepts: "melancholic song about memories"

**Less effective:**
- Artist names (use Spotify/metadata for that)
- Very specific lyrics (embedding is semantic, not exact match)

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Search Query   │────▶│   Embedder      │────▶│    Qdrant       │
│  "sad song"     │     │  (Multilingual) │     │  (ANN Search)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Top K Results  │
                                                │  (by cosine     │
                                                │   similarity)   │
                                                └─────────────────┘
```

## Performance

| Operation | Time |
|-----------|------|
| Model loading | ~12s (first search only) |
| Query embedding | ~40ms |
| Qdrant ANN search | ~70ms |
| **Total (warm)** | **~110ms** |

The model loads once and stays in memory. Subsequent searches are fast.

## Requirements

- **Qdrant**: Running on `localhost:6333`
  ```bash
  docker run -d -p 6333:6333 qdrant/qdrant
  ```
- **sentence-transformers**: Installed automatically
- **Indexed tracks**: Run `vectrola ingest` first

## Troubleshooting

### "No matching tracks found"
1. Check if Qdrant is running: `vectrola status`
2. Check if tracks are indexed: Should show track count
3. Try a broader query: "song" instead of very specific terms

### Search is slow
First search loads the model (~12s). Subsequent searches are fast (~100ms).

### Hindi songs not matching English queries
Make sure tracks were indexed with the multilingual model. Re-run:
```bash
vectrola ingest /path/to/music --no-recursive
```
