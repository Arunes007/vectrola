# Setup Wizard

Vectrola includes an interactive setup wizard to configure all components.

## Quick Start

```bash
vectrola setup
```

This walks you through:
1. **Storage Backend** - Local or Remote Qdrant
2. **LLM Provider** - Ollama, OpenAI, Anthropic, or None
3. **Google Drive** - Connect for cloud music ingestion
4. **User Account** - Anonymous or Login

## Configuration File

Settings are saved to `~/.config/vectrola/config.json`:

```json
{
  "version": 1,
  "storage": {
    "mode": "remote",
    "qdrant_url": "https://qdrant-vectrola.up.railway.app",
    "qdrant_api_key": null
  },
  "llm": {
    "provider": "ollama",
    "model": "llama3.2:1b",
    "api_key": null
  },
  "gdrive": {
    "enabled": true
  },
  "user": {
    "mode": "login",
    "multi_tenant": false
  }
}
```

## Priority Order

Settings are loaded with this priority (highest first):
1. **Environment variables** - Override everything (for CI/containers)
2. **config.json** - User configuration
3. **Defaults** - Local Qdrant, Ollama, anonymous

## Skip Steps

Re-run setup and skip steps you don't want to change:

```bash
# Only reconfigure storage
vectrola setup --skip-llm --skip-gdrive --skip-user

# Only reconfigure LLM
vectrola setup --skip-storage --skip-gdrive --skip-user
```

## Storage Options

### Local (Default)

Best for single-device use. Fastest, works offline.

```bash
# Start local Qdrant
docker run -d -p 6333:6333 qdrant/qdrant
```

### Remote

Best for multi-device sync. Requires internet.

Supports:
- **Railway** - Easy deployment, free tier available
- **Qdrant Cloud** - Managed service
- **Self-hosted** - Your own server

## LLM Options

### Ollama (Default)

Free, local, private. Runs on your machine.

```bash
# Install Ollama
brew install ollama  # macOS

# Start server
ollama serve

# Pull a model
ollama pull llama3.2:1b
```

### OpenAI

Cloud-based, paid. Better quality analysis.

Requires `OPENAI_API_KEY` environment variable or enter during setup.

### Anthropic

Cloud-based, paid. Better quality analysis.

Requires `ANTHROPIC_API_KEY` environment variable or enter during setup.

### None

Skip LLM analysis entirely. Moods and themes won't be extracted.

## Environment Variables

These override config.json:

| Variable | Description |
|----------|-------------|
| `QDRANT_URL` | Qdrant server URL |
| `QDRANT_API_KEY` | Qdrant API key |
| `OPENAI_API_KEY` | OpenAI API key (auto-sets provider to openai) |
| `ANTHROPIC_API_KEY` | Anthropic API key (auto-sets provider to anthropic) |
| `VECTROLA_USER_ID` | Override user ID |
| `VECTROLA_MULTI_TENANT` | Enable multi-tenant filtering |

## Verify Setup

After setup, verify everything works:

```bash
vectrola status
```

Expected output:
```
🎧 Vectrola Status

┌──────────────┬─────────────────────────────────────────┐
│ Component    │ Status                                  │
├──────────────┼─────────────────────────────────────────┤
│ Qdrant       │ ✓ connected (qdrant-vectrola.up.railway)│
│ Ollama       │ ✓ connected                             │
│ Google Drive │ ✓ authenticated                         │
│ ...          │                                         │
└──────────────┴─────────────────────────────────────────┘
```
