# Lyrics Fetching

Vectrola fetches lyrics from online sources before falling back to Whisper transcription. This is especially important for non-English music where Whisper's accuracy is limited.

## Why Online Lyrics First?

For Bollywood and Hindi music:
- **LRClib** provides accurate Devanagari script lyrics
- Whisper often outputs Urdu script or garbled transliterations
- Online sources include metadata (album = movie name)

## Sources (Priority Order)

### 1. LRClib (Primary)

Free, no API key required. Best for popular music.

```python
from vectrola.ingest.lyrics import LyricsFetcher

fetcher = LyricsFetcher()
result = fetcher.fetch(artist="Arijit Singh", title="Tum Hi Ho")

print(result.text)           # Lyrics text
print(result.source)         # "lrclib"
print(result.synced)         # True if timestamped
print(result.album)          # Album/movie name
print(result.duration_seconds)  # Track duration
```

**Features:**
- Synced (timestamped) lyrics when available
- Album/movie metadata
- Duration info
- Works with title-only search

### 2. Genius (Secondary)

Requires API token. Good for newer/obscure songs.

**Setup:**

1. Get your API token at: https://genius.com/api-clients
2. Click "New API Client"
3. Fill in the form (Name: "Vectrola", App Website URL: optional)
4. Copy the "Client Access Token" (not Client ID or Secret)
5. Add to your `.env` file:
   ```bash
   GENIUS_API_TOKEN=your_token_here
   ```

**Usage:**

```python
from vectrola.ingest.lyrics import LyricsFetcher

# Automatically loads from GENIUS_API_TOKEN environment variable
fetcher = LyricsFetcher()
result = fetcher.fetch(artist="Artist", title="Song")

# Or pass token explicitly
fetcher = LyricsFetcher(genius_token="your_token")
result = fetcher.fetch(artist="Artist", title="Song")
```

**Note:** If `GENIUS_API_TOKEN` is not set, Genius fetching will be skipped and the fetcher will fall back to LRClib or Whisper.

### 3. Whisper (Fallback)

Only used when online sources fail.

```python
result = fetcher.fetch(
    artist="Unknown",
    title="Obscure Song",
    audio_path=Path("/path/to/song.mp3"),
    use_whisper_fallback=True,  # Default: True
)
```

## LyricsResult Structure

```python
@dataclass
class LyricsResult:
    text: str                    # Plain text lyrics
    source: str                  # "lrclib", "genius", "whisper"
    synced: bool                 # Has timestamps?
    segments: list[dict] | None  # [{start, end, text}, ...]
    artist: str | None           # Artist from source
    title: str | None            # Title from source  
    album: str | None            # Album (movie for Bollywood)
    duration_seconds: float | None
```

## Search Behavior

### With Artist + Title
```python
# Best accuracy - direct lookup
fetcher.fetch(artist="Arijit Singh", title="Tum Hi Ho")
```

### Title Only
```python
# Uses LRClib search endpoint
fetcher.fetch(artist="", title="Humnava")
```

Works for unique song names but may return wrong match for common titles.

## Title/Artist Cleaning

The fetcher automatically cleans input:

```python
# File extensions removed
"Song.mp3" → "Song"

# Common suffixes removed
"Song (Official Audio)" → "Song"
"Song [HD]" → "Song"

# Track numbers removed
"01 - Song" → "Song"

# Unknown artist normalized
"Unknown Artist" → ""
```

## Hindi/Bollywood Support

LRClib has excellent coverage of Bollywood soundtracks:

```python
result = fetcher.fetch(artist="", title="Tere Naina")

# Returns:
# - Lyrics in Devanagari: "तेरे नैना, तेरे नैना..."
# - Album: Movie soundtrack name
# - Artist: Singer name
```

## Error Handling

```python
# Returns None if not found (doesn't raise)
result = fetcher.fetch(artist="Fake", title="NotReal")
if result is None:
    print("Lyrics not found")
```

## Integration with Pipeline

The `IngestPipeline` automatically uses lyrics fetching:

```python
from vectrola.ingest.pipeline import IngestPipeline

pipeline = IngestPipeline()
analysis = pipeline.process_track(Path("song.mp3"))

print(analysis.lyrics_source)  # "lrclib", "genius", or "whisper"
print(analysis.album)          # From LRClib
print(analysis.movie)          # Same as album for soundtracks
```

## Testing

```bash
# Run lyrics tests
pytest tests/test_lyrics.py -v

# Test specific function
pytest tests/test_lyrics.py::TestLyricsFetcher::test_hindi_lyrics_in_devanagari -v
```
