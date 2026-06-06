# Testing Guide

## Quick Start

```bash
# Activate environment
conda activate nlp
export KMP_DUPLICATE_LIB_OK=TRUE

# Run all unit tests (fast, no external dependencies)
pytest -m "not network and not ollama and not integration"

# Run ALL tests (requires network + Ollama running)
pytest
```

## Test Categories

| Marker | Description | Requirements |
|--------|-------------|--------------|
| (none) | Unit tests | None |
| `network` | API tests | Internet connection |
| `ollama` | LLM tests | Ollama running locally |
| `integration` | Full pipeline | Audio file + all services |

## Running Specific Tests

```bash
# Run specific test file
pytest tests/test_pipeline.py -v

# Run specific test class
pytest tests/test_lyrics.py::TestLyricsFetcher -v

# Run specific test
pytest tests/test_tags.py::TestFileTags::test_file_tags_defaults -v

# Run with coverage
pytest --cov=vectrola --cov-report=html
```

## Test Files

| File | Tests | Marker |
|------|-------|--------|
| `test_pipeline.py` | TrackAnalysis, IngestPipeline | unit + integration |
| `test_lyrics.py` | LyricsFetcher, LRClib/Genius | network |
| `test_metadata.py` | MetadataFetcher, MusicBrainz | network |
| `test_synthesis.py` | Synthesizer, Ollama | ollama |
| `test_tags.py` | FileTags, read/write | unit |

## Before Running Network Tests

Ensure you have:
1. Internet connection
2. No firewall blocking LRClib/MusicBrainz

```bash
# Test LRClib connectivity
curl -s "https://lrclib.net/api/search?q=test" | head
```

## Before Running Ollama Tests

```bash
# Start Ollama
ollama serve

# Ensure model is available
ollama pull llama3.2:3b

# Verify
ollama list
```

## Test Output

```bash
# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l
```

## Writing New Tests

```python
import pytest

# Unit test (always runs)
def test_something():
    assert True

# Network test (skipped with -m "not network")
@pytest.mark.network
def test_api_call():
    result = call_api()
    assert result is not None

# Ollama test (skipped with -m "not ollama")  
@pytest.mark.ollama
def test_llm():
    result = synthesize("lyrics")
    assert result.themes
```

## CI Configuration

For GitHub Actions or similar:

```yaml
# Run unit tests only (no external services)
- name: Run Tests
  run: pytest -m "not network and not ollama and not integration"

# Full tests (with services)
- name: Run Full Tests
  run: |
    ollama serve &
    sleep 5
    ollama pull llama3.2:3b
    pytest
```
