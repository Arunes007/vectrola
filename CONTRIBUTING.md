# Contributing to Vectrola

Thank you for your interest in contributing to Vectrola! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [Conda](https://docs.conda.io/en/latest/miniconda.html) (recommended) or venv
- [Docker](https://www.docker.com/) for Qdrant
- [Ollama](https://ollama.ai/) for local LLM

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/Arunes007/vectrola.git
   cd vectrola
   ```

2. **Create a Python environment**
   ```bash
   # Using conda (recommended)
   conda create -n vectrola python=3.10
   conda activate vectrola
   
   # Or using venv
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   # Install base dependencies
   pip install -e .
   
   # Install with all optional features
   pip install -e ".[full,dev]"
   ```

4. **Set up environment variables**
   ```bash
   # Copy the example env file
   cp .env.example .env
   
   # Edit .env and add your API keys (optional)
   # - YouTube API: https://console.cloud.google.com/apis/credentials
   # - Genius API: https://genius.com/api-clients
   ```

5. **Start required services**
   ```bash
   # Start Qdrant vector database
   docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
   
   # Start Ollama
   ollama serve
   ollama pull qwen2.5:3b  # Or llama3.2:1b for faster but less accurate results
   ```

6. **Run tests**
   ```bash
   # Run unit tests only (fast)
   pytest -m "not network and not ollama and not integration"
   
   # Run all tests
   pytest
   ```

## Testing

We use pytest with custom markers for different test categories:

- **Unit tests** (no markers): Fast, no external dependencies
- `@pytest.mark.network`: Tests requiring network access
- `@pytest.mark.ollama`: Tests requiring Ollama LLM
- `@pytest.mark.integration`: End-to-end tests requiring real audio files

```bash
# Run specific test categories
pytest -m "network"         # Network tests only
pytest -m "ollama"          # Ollama tests only
pytest -m "integration"     # Integration tests only
pytest -m "not integration" # Everything except integration tests
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Install ruff
pip install ruff

# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

### Style Guidelines

- Line length: 100 characters
- Use type hints for function signatures
- Write docstrings for public functions and classes
- Follow PEP 8 conventions

## Making Contributions

### Reporting Issues

- Check existing issues first to avoid duplicates
- Use the issue templates when available
- Provide clear reproduction steps for bugs
- Include system information (OS, Python version, etc.)

### Pull Requests

1. **Fork the repository** and create a new branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clear, focused commits
   - Add tests for new functionality
   - Update documentation as needed
   - Ensure tests pass: `pytest`

3. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add clear description of changes"
   ```

4. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request**
   - Use the PR template
   - Link related issues
   - Provide a clear description of changes
   - Include screenshots/examples if relevant

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Write clear PR descriptions explaining the "why"
- Update CHANGELOG.md for user-facing changes
- Ensure CI passes (tests, linting)
- Be responsive to review feedback

## Project Structure

```
vectrola/
├── vectrola/           # Main package
│   ├── cli.py          # Typer CLI
│   ├── config.py       # Configuration
│   ├── ingest/         # Data ingestion pipeline
│   ├── storage/        # Database and file I/O
│   ├── search/         # Semantic search
│   └── mcp/            # MCP server
├── tests/              # Test suite
├── docs/               # Documentation
└── wiki/               # Generated Obsidian vault
```

## Areas for Contribution

### Good First Issues

- Documentation improvements
- Test coverage
- Bug fixes
- Example scripts

### Feature Ideas

- Support for additional metadata sources
- New embedding models
- Alternative vector databases
- Web UI
- Mobile app
- Playlist generation
- Music recommendation engine

### Documentation

- Tutorial improvements
- Use case examples
- API documentation
- Video walkthroughs

## Questions?

- Open a [Discussion](https://github.com/Arunes007/vectrola/discussions)
- Join our [Discord/Slack] (if applicable)
- Check existing documentation in `docs/`

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
