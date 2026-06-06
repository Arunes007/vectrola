# How Whisper Works

Whisper is OpenAI's speech recognition model. Vectrola uses `faster-whisper`, a CTranslate2-optimized implementation that runs 4x faster.

## Overview

```
Audio File (MP3/FLAC/WAV)
         │
         ▼
┌─────────────────────────────────────┐
│           WHISPER MODEL             │
│                                     │
│  1. Load audio waveform             │
│  2. Convert to mel spectrogram      │
│  3. Transformer encoder             │
│  4. Transformer decoder (autoregr.) │
│  5. Beam search for best text       │
└─────────────────────────────────────┘
         │
         ▼
TranscriptionResult:
  - text: "Full lyrics..."
  - segments: [{start, end, text}, ...]
  - language: "en"
```

## Code Example

```python
from faster_whisper import WhisperModel

# Load model (one-time, cached)
model = WhisperModel("base", device="cpu", compute_type="int8")

# Transcribe audio
segments, info = model.transcribe("song.mp3", beam_size=5)

# info contains metadata
print(f"Detected language: {info.language}")  # e.g., "hi" for Hindi
print(f"Confidence: {info.language_probability}")  # e.g., 0.95

# segments is a generator of timestamped chunks
for segment in segments:
    print(f"[{segment.start:.2f}s - {segment.end:.2f}s] {segment.text}")
```

## Model Sizes

| Model | Parameters | VRAM | Speed | Accuracy |
|-------|------------|------|-------|----------|
| `tiny` | 39M | ~1GB | Fastest | Lower |
| `base` | 74M | ~1GB | Fast | Good |
| `small` | 244M | ~2GB | Medium | Better |
| `medium` | 769M | ~5GB | Slow | High |
| `large-v3` | 1.5B | ~10GB | Slowest | Highest |

**Vectrola default**: `base` model with `int8` quantization - good balance of speed and accuracy.

## Key Parameters

### `device`
- `"cpu"`: Works everywhere, no GPU needed
- `"cuda"`: NVIDIA GPU acceleration
- `"auto"`: Auto-detect

### `compute_type`
- `"int8"`: 2x faster, minimal quality loss (recommended)
- `"float16"`: GPU default
- `"float32"`: Highest quality, slowest

### `beam_size`
- Higher = more accurate, slower
- `beam_size=5` is a good default

## Output Structure

```python
@dataclass
class TranscriptionResult:
    text: str              # Full text, all segments joined
    segments: list[dict]   # Timestamped chunks
    language: str          # ISO code ("en", "hi", "es", etc.)
    language_probability: float  # Confidence 0.0-1.0
```

### Segment Format

```python
{
    "start": 0.0,      # Start time in seconds
    "end": 2.5,        # End time in seconds
    "text": "First line of lyrics"
}
```

## Language Detection

Whisper automatically detects the language. It supports 99 languages including:

- English (en)
- Hindi (hi)
- Spanish (es)
- French (fr)
- German (de)
- Japanese (ja)
- Chinese (zh)
- And many more...

## Performance Tips

1. **Use `int8` quantization**: 2x speedup with minimal quality loss
2. **Smaller models for tagging**: `base` is enough for lyrics extraction
3. **GPU acceleration**: Use CUDA if available for 10x+ speedup
4. **Batch processing**: Process multiple files to amortize model load time

## Implementation in Vectrola

See `vectrola/ingest/transcribe.py`:

```python
class Transcriber:
    def __init__(self):
        self._model = None  # Lazy loading
    
    @property
    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel("base", device="cpu", compute_type="int8")
        return self._model
    
    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        segments, info = self.model.transcribe(str(audio_path), beam_size=5)
        # ... collect results
```
