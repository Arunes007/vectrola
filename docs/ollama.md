# How Ollama Works

Ollama is a local LLM runtime that runs models like Llama, Mistral, etc. on your machine. No API keys, no cloud, full privacy.

## Overview

```
Lyrics Text
     │
     ▼
┌─────────────────────────────────────┐
│            OLLAMA                    │
│                                      │
│  1. Load prompt with lyrics          │
│  2. Tokenize input                   │
│  3. Run through LLM (autoregressive) │
│  4. Generate JSON output             │
│  5. Parse structured response        │
└─────────────────────────────────────┘
     │
     ▼
SynthesisResult:
  - themes: ["mortality", "longing"]
  - moods: ["melancholic", "introspective"]
  - narrative: "A story about..."
  - imagery: ["desolate wasteland", ...]
```

## Installation

```bash
# macOS - Download from https://ollama.com/download

# Pull a model
ollama pull llama3.2:1b    # 1.3GB, fast
ollama pull llama3:8b      # 4.7GB, better quality

# Test it
ollama run llama3.2:1b "Say hello"
```

## Code Example

```python
import ollama
import json

# Simple generation
response = ollama.generate(
    model='llama3.2:1b',
    prompt='What is the meaning of life?'
)
print(response['response'])

# Structured JSON output
response = ollama.generate(
    model='llama3.2:1b',
    prompt='Return a JSON object with {"greeting": "hello"}',
    format='json'  # Forces valid JSON output
)
data = json.loads(response['response'])
```

## The Synthesis Prompt

Vectrola uses a carefully crafted prompt to extract semantic metadata:

```python
SYNTHESIS_PROMPT = """Analyze these song lyrics and return a JSON object with:
- "themes": list of 3-5 abstract themes (e.g., "mortality", "urban isolation", "longing")
- "moods": list of 2-3 mood tags (e.g., "melancholic", "euphoric", "aggressive")
- "narrative": one sentence describing the song's story arc
- "imagery": list of 2-3 visual images evoked

Lyrics:
{lyrics}

Return ONLY valid JSON, no explanation."""
```

### Why This Prompt Works

1. **Explicit structure**: Lists exactly what fields to return
2. **Examples**: Parenthetical examples guide the model's output style
3. **JSON format**: Combined with `format='json'`, ensures parseable output
4. **"Return ONLY"**: Prevents explanatory text before/after JSON

## Output Structure

```python
@dataclass
class SynthesisResult:
    themes: list[str]    # Abstract concepts
    moods: list[str]     # Emotional descriptors
    narrative: str       # One-sentence story arc
    imagery: list[str]   # Visual scenes evoked
    raw_response: str    # Original JSON string
```

### Example Output

```python
SynthesisResult(
    themes=["urban isolation", "longing", "rebellion"],
    moods=["melancholic", "angry", "introspective"],
    narrative="A young woman consumed by grief finds solace in a doomed relationship.",
    imagery=["a desolate wasteland", "a burning pyre", "a piercing cry"],
    raw_response='{"themes": [...], ...}'
)
```

## Models Comparison

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| `llama3.2:1b` | 1.3GB | Fast | Good | Default for tagging |
| `llama3.2:3b` | 2.0GB | Medium | Better | Better understanding |
| `llama3:8b` | 4.7GB | Slow | High | Complex analysis |
| `mistral:7b` | 4.1GB | Medium | High | Alternative |

**Vectrola default**: `llama3.2:1b` - fast enough for batch processing with decent quality.

## Error Handling

```python
def synthesize(self, lyrics: str) -> SynthesisResult:
    try:
        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            format='json'
        )
        data = json.loads(response['response'])
        return SynthesisResult(
            themes=data.get('themes', []),
            moods=data.get('moods', []),
            # ...
        )
    
    except json.JSONDecodeError:
        # Model returned invalid JSON
        return SynthesisResult(themes=[], moods=[], ...)
    
    except Exception as e:
        # Connection error, model not found, etc.
        if "Connection" in str(e):
            return SynthesisResult(
                narrative="Ollama not running. Start with 'ollama serve'",
                # ...
            )
```

## Configuration

In `vectrola/config.py`:

```python
@dataclass
class VectrolaConfig:
    ollama_model: str = "llama3.2:1b"
    ollama_host: str = "http://localhost:11434"
```

Override via environment or config file.

## Performance Tips

1. **Smaller models for tagging**: 1B-3B models are fast and good enough
2. **Batch your prompts**: Ollama keeps the model loaded between calls
3. **Truncate lyrics**: Keep input under 3000 chars to fit context window
4. **JSON format**: Always use `format='json'` for reliable parsing

## Troubleshooting

### "Connection refused"
```bash
# Start Ollama service
ollama serve
# Or launch Ollama.app
```

### "Model not found"
```bash
# Pull the model first
ollama pull llama3.2:1b
```

### "llama-server binary not found"
Homebrew Ollama 0.30+ on Apple Silicon is broken. Install from https://ollama.com/download instead.

## Implementation in Vectrola

See `vectrola/ingest/synthesis.py`:

```python
class Synthesizer:
    def __init__(self, model: str = None):
        config = get_config()
        self.model = model or config.ollama_model
    
    def synthesize(self, lyrics: str) -> SynthesisResult:
        prompt = SYNTHESIS_PROMPT.format(lyrics=lyrics[:3000])
        
        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            format='json'
        )
        
        data = json.loads(response['response'])
        return SynthesisResult(
            themes=data.get('themes', []),
            moods=data.get('moods', []),
            narrative=data.get('narrative', ''),
            imagery=data.get('imagery', []),
            raw_response=response['response']
        )
```
