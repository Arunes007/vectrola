"""CLI helper utilities for UI and error handling."""

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def show_qdrant_error(config):
    """Show context-aware Qdrant connection error message."""
    console.print("[red]Error: Cannot connect to Qdrant.[/red]")

    if config.storage_mode == "remote" or ("localhost" not in config.qdrant_url and "127.0.0.1" not in config.qdrant_url):
        console.print(f"[dim]Remote Qdrant URL: {config.qdrant_url}[/dim]")
        console.print("[dim]Check that:[/dim]")
        console.print("[dim]  1. The URL is correct[/dim]")
        console.print("[dim]  2. Your API key is set (QDRANT_API_KEY env var)[/dim]")
        console.print("[dim]  3. The Qdrant server is running[/dim]")
    else:
        console.print("[dim]Start local Qdrant with: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")


def show_welcome(ctx: typer.Context):
    """Show welcome message when no command is provided."""
    from vectrola.messages import load_messages

    if ctx.invoked_subcommand is None:
        msgs = load_messages()["welcome"]

        console.print()
        console.print(f"[bold cyan]{msgs['title']}[/bold cyan]")
        console.print(f"[dim]{msgs['subtitle']}[/dim]")
        console.print()

        # Getting started
        gs = msgs["getting_started"]
        console.print(f"[bold]{gs['header']}[/bold]")
        for cmd in gs["commands"]:
            console.print(f"  {cmd['cmd']:25} [dim]# {cmd['desc']}[/dim]")
        console.print()

        # Sections
        for section in msgs["sections"].values():
            console.print(f"[bold]{section['header']}[/bold]")
            for cmd in section["commands"]:
                console.print(f"  {cmd['name']:12} [dim]{cmd['desc']}[/dim]")
            console.print()

        console.print(f"[dim]{msgs['footer']}[/dim]")
        console.print()
        raise typer.Exit(0)


def status():
    """Show Vectrola system status and component availability."""
    console.print("[bold]🎧 Vectrola Status[/bold]\n")

    checks = []

    # Check Whisper
    try:
        from faster_whisper import WhisperModel

        checks.append(("faster-whisper", "✓", "green"))
    except ImportError:
        checks.append(("faster-whisper", "✗ not installed", "red"))

    # Check Ollama
    try:
        import ollama

        # Try to connect
        try:
            ollama.list()
            checks.append(("Ollama", "✓ connected", "green"))
        except Exception:
            checks.append(("Ollama", "✗ not running (start with 'ollama serve')", "yellow"))
    except ImportError:
        checks.append(("Ollama", "✗ not installed", "red"))

    # Check mutagen
    try:
        import mutagen

        checks.append(("mutagen", "✓", "green"))
    except ImportError:
        checks.append(("mutagen", "✗ not installed", "red"))

    # Check Qdrant (Day 2)
    try:
        from vectrola.storage.qdrant import get_db
        from vectrola.config import get_config

        config = get_config()
        qdrant_url = config.qdrant_url

        try:
            db = get_db()
            if db.is_connected():
                # Show if local or remote
                if "localhost" in qdrant_url or "127.0.0.1" in qdrant_url:
                    checks.append(("Qdrant", "✓ connected (local)", "green"))
                else:
                    # Extract hostname for display
                    from urllib.parse import urlparse
                    host = urlparse(qdrant_url).hostname or qdrant_url
                    checks.append(("Qdrant", f"✓ connected ({host})", "green"))
            else:
                checks.append(("Qdrant", f"✗ not reachable ({qdrant_url})", "red"))
        except Exception as e:
            checks.append(("Qdrant", f"✗ error: {e}", "red"))
    except ImportError:
        checks.append(("Qdrant", "○ not installed (Day 2)", "dim"))

    # Check sentence-transformers (Day 2)
    try:
        from sentence_transformers import SentenceTransformer

        checks.append(("sentence-transformers", "✓", "green"))
    except ImportError:
        checks.append(("sentence-transformers", "○ not installed (Day 2)", "dim"))

    # Check CLAP (Day 3)
    try:
        from transformers import ClapModel

        checks.append(("CLAP (transformers)", "✓", "green"))
    except ImportError:
        checks.append(("CLAP (transformers)", "○ not installed (Day 3)", "dim"))

    # Check Google Drive
    try:
        from vectrola.gdrive import is_authenticated

        if is_authenticated():
            checks.append(("Google Drive", "✓ authenticated", "green"))
        else:
            checks.append(("Google Drive", "○ not authenticated", "dim"))
    except ImportError:
        checks.append(("Google Drive", "○ not installed (pip install vectrola[gdrive])", "dim"))

    # Display
    table = Table(show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Status")

    for name, status, color in checks:
        table.add_row(name, f"[{color}]{status}[/{color}]")

    console.print(table)
