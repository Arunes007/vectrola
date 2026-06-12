# Installation Guide

Quick start guide for installing Vectrola.

## Quick Install (Recommended)

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.ps1 | iex
```

The installer will guide you through configuration options.

## What the Installer Asks

### 1. LLM for Semantic Analysis

Vectrola uses an LLM to extract themes, moods, and narratives from your music.

| Option | Description |
|--------|-------------|
| **Local Ollama** (default) | Runs on your machine. Private, no API costs. Requires [Ollama](https://ollama.ai). |
| **Remote LLM** | Use your own Ollama-compatible endpoint. |

### 2. Vector Database

Vectrola stores music embeddings in a vector database for semantic search.

| Option | Description |
|--------|-------------|
| **Hosted Qdrant** (default) | No setup needed. Uses Vectrola's hosted instance. |
| **Local Qdrant** | Runs in Docker on your machine. Full control over your data. |
| **Remote Qdrant** | Use your own Qdrant instance. |

## Prerequisites

The installer checks for these automatically:

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Git** | Any | For cloning the repository |
| **Python** | 3.10+ | Core runtime |
| **Ollama** | Any | Only if you choose "Local Ollama" |
| **Docker** | Any | Only if you choose "Local Qdrant" |

## Post-Installation

### If you chose Local Ollama

1. Install Ollama (if not already installed):
   - **macOS**: `brew install ollama` or [download](https://ollama.ai/download)
   - **Linux**: `curl -fsSL https://ollama.ai/install.sh | sh`
   - **Windows**: [Download](https://ollama.ai/download)

2. Start Ollama and download a model:
   ```bash
   ollama serve          # In one terminal
   ollama pull qwen2.5:3b  # In another terminal
   ```

### Verify Installation

```bash
# Reload your shell first
source ~/.zshrc  # or ~/.bashrc

# Check status
vectrola status
```

## Non-Interactive Installation

For CI/CD or scripted installations:

```bash
# macOS/Linux - with defaults
curl -fsSL .../install.sh | bash -s -- --non-interactive

# macOS/Linux - with local everything
curl -fsSL .../install.sh | bash -s -- --non-interactive --llm=local --qdrant=local

# Windows - with defaults
& ([scriptblock]::Create((irm .../install.ps1))) -NonInteractive
```

See [installer/README.md](../installer/README.md) for all options.

## Manual Installation

If you prefer manual control:

```bash
# Clone the repository
git clone https://github.com/Arunes007/vectrola.git
cd vectrola

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows

# Install with all features
pip install -e ".[full]"

# Or install specific features
pip install -e ".[vectors]"   # Vector search only
pip install -e ".[audio]"     # Audio embeddings only
pip install -e .              # Minimal (no vectors/audio)

# Configure services
mkdir -p ~/.config/vectrola
cat > ~/.config/vectrola/.env << EOF
OLLAMA_HOST=http://localhost:11434
QDRANT_URL=https://qdrant.vectrola.dev
EOF

# Verify
vectrola status
```

## Troubleshooting

### "vectrola: command not found"

Open a new terminal window, or reload your shell:
```bash
source ~/.zshrc  # or ~/.bashrc
```

### "Python 3.10+ required"

Install Python 3.11:
- **macOS**: `brew install python@3.11`
- **Ubuntu/Debian**: `sudo apt install python3.11 python3.11-venv`
- **Windows**: `winget install Python.Python.3.11`

### "Failed to create virtual environment"

On Ubuntu/Debian, install the venv module:
```bash
sudo apt install python3-venv
```

### Ollama connection errors

Make sure Ollama is running:
```bash
ollama serve
```

### Docker permission denied (Linux)

Add your user to the docker group:
```bash
sudo usermod -aG docker $USER
# Then log out and back in
```

## Uninstallation

```bash
# Remove installation directory
rm -rf ~/.vectrola

# Remove configuration
rm -rf ~/.config/vectrola

# Remove from shell config (edit manually)
# Remove lines containing "# Vectrola" from ~/.zshrc or ~/.bashrc

# Optional: Remove Qdrant container
docker rm -f qdrant
```
