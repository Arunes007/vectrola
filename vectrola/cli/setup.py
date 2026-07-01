"""Setup wizard for Vectrola configuration."""

import json
import typer
from pathlib import Path
from datetime import datetime
from rich.table import Table
from urllib.parse import urlparse

from vectrola.config import (
    load_config,
    save_config,
    reset_config,
    CONFIG_PATH,
    get_current_user,
    _DEFAULTS,
)
from vectrola.messages import load_messages
from vectrola.storage.qdrant import VectrolaDB

from .helpers import console

# Import from gdrive module (will be created)
# This creates a forward reference that will work once gdrive.py exists
def _browse_and_select_folders():
    """Forward reference to gdrive._browse_and_select_folders."""
    from .gdrive import browse_and_select_folders
    browse_and_select_folders()


def setup(
    skip_storage: bool = typer.Option(False, "--skip-storage", help="Skip storage setup"),
    skip_llm: bool = typer.Option(False, "--skip-llm", help="Skip LLM setup"),
    skip_gdrive: bool = typer.Option(False, "--skip-gdrive", help="Skip Google Drive setup"),
    skip_user: bool = typer.Option(False, "--skip-user", help="Skip user setup"),
):
    """
    Interactive setup wizard for Vectrola.

    Configures storage backend, LLM provider, Google Drive, and user account.
    Settings are saved to ~/.config/vectrola/config.json.

    Re-run anytime to change settings. Use --skip-X flags to skip steps.
    """
    from vectrola.config import load_config, save_config, reset_config, CONFIG_PATH

    console.print("[bold]🎧 Vectrola Setup Wizard[/bold]\n")

    config = load_config()

    # Step 1: Storage
    if not skip_storage:
        config = _setup_storage(config)

    # Step 2: LLM
    if not skip_llm:
        config = _setup_llm(config)

    # Step 3: GDrive
    if not skip_gdrive:
        config = _setup_gdrive(config)

    # Step 4: User
    if not skip_user:
        config = _setup_user(config)

    # Save and show summary
    save_config(config)
    reset_config()  # Clear cached config so next get_config() reads new values
    _show_setup_summary(config)


def _setup_storage(config):
    """Step 1: Configure storage backend."""
    msgs = load_messages()["setup"]["storage"]

    console.print(f"[bold]{msgs['header']}[/bold]")
    console.print("─" * 25)
    console.print()

    for opt in msgs["options"]:
        console.print(f"  [{opt['key']}] {opt['name']} ({opt['desc']})")
        if opt.get("hint"):
            console.print(f"      [dim]{opt['hint']}[/dim]")
        console.print()

    choice = typer.prompt("Choice", default=msgs["default"])

    if choice == "2":
        config.storage_mode = "remote"
        # Vectrola Cloud - use config default (can be overridden via VECTROLA_CLOUD_URL env var)
        config.qdrant_url = config.vectrola_cloud_url
        config.qdrant_api_key = None  # Public access

        # Test connection
        console.print()
        with console.status(msgs["connecting"]):
            from vectrola.storage.qdrant import VectrolaDB
            try:
                db = VectrolaDB(url=config.qdrant_url, api_key=config.qdrant_api_key)
                if db.is_connected():
                    console.print(f"[green]✓ {msgs['connected']}[/green]")
                else:
                    raise Exception(msgs["connection_failed"])
            except Exception as e:
                console.print(f"[red]✗ {msgs['connection_failed']}: {e}[/red]")
                if not typer.confirm("Continue anyway?", default=False):
                    raise typer.Abort()
    else:
        from vectrola.config import _DEFAULTS
        config.storage_mode = "local"
        config.qdrant_url = _DEFAULTS["storage"]["local_url"]
        config.qdrant_api_key = None

        # Check if local Qdrant is running
        console.print()
        with console.status(msgs["checking_local"]):
            from vectrola.storage.qdrant import VectrolaDB
            try:
                db = VectrolaDB(url=config.qdrant_url)
                if db.is_connected():
                    console.print(f"[green]✓ {msgs['local_running']}[/green]")
                else:
                    raise Exception()
            except:
                console.print(f"[yellow]⚠ {msgs['local_not_running']}[/yellow]")
                console.print(f"[dim]{msgs['local_hint']}[/dim]")

    console.print()
    return config


def _setup_llm(config):
    """Step 2: Configure LLM provider."""
    console.print("[bold]Step 2/4: LLM Provider[/bold]")
    console.print("─" * 22)
    console.print()
    console.print("  [1] Ollama (free, local, private)")
    console.print("  [2] OpenAI (cloud, paid)")
    console.print("  [3] Anthropic (cloud, paid)")
    console.print("  [4] None (skip mood/theme analysis)")
    console.print()

    provider_map = {"ollama": "1", "openai": "2", "anthropic": "3", "none": "4"}
    current = provider_map.get(config.llm_provider, "1")
    choice = typer.prompt("Choice", default=current)

    if choice == "1":
        config.llm_provider = "ollama"
        config.llm_api_key = None

        # Check Ollama and list available models
        console.print()
        try:
            import ollama
            models_response = ollama.list()
            models = [m.get('name', m.get('model', '')) for m in models_response.get('models', [])]

            if models:
                console.print("[green]✓ Ollama running[/green]")
                console.print()
                console.print("Available models:")
                for i, model in enumerate(models, 1):
                    console.print(f"  [{i}] {model}")
                console.print()

                # Find current model index if it exists
                current_idx = "1"
                if config.llm_model:
                    for i, m in enumerate(models, 1):
                        if m == config.llm_model or m.startswith(config.llm_model.split(':')[0]):
                            current_idx = str(i)
                            break

                model_choice = typer.prompt("Select model", default=current_idx)
                try:
                    idx = int(model_choice) - 1
                    if 0 <= idx < len(models):
                        config.llm_model = models[idx]
                    else:
                        config.llm_model = models[0]
                except ValueError:
                    # User typed a model name directly
                    config.llm_model = model_choice

                console.print(f"[green]✓ Using {config.llm_model}[/green]")
            else:
                console.print("[yellow]⚠ Ollama running but no models installed[/yellow]")
                console.print("[dim]Install a model with: ollama pull llama3.2:1b[/dim]")
                config.llm_model = "llama3.2:1b"  # Default, user needs to pull
        except Exception as e:
            console.print("[yellow]⚠ Ollama not running[/yellow]")
            console.print("[dim]Start with: ollama serve[/dim]")
            config.llm_model = "llama3.2:1b"

    elif choice == "2":
        config.llm_provider = "openai"
        config.llm_api_key = typer.prompt("OpenAI API Key", hide_input=True)
        config.llm_model = typer.prompt("Model", default="gpt-4o-mini")
        console.print("[green]✓ OpenAI configured[/green]")

    elif choice == "3":
        config.llm_provider = "anthropic"
        config.llm_api_key = typer.prompt("Anthropic API Key", hide_input=True)
        config.llm_model = typer.prompt("Model", default="claude-3-haiku-20240307")
        console.print("[green]✓ Anthropic configured[/green]")

    else:
        config.llm_provider = "none"
        config.llm_model = None
        config.llm_api_key = None
        console.print("[dim]LLM analysis disabled. Moods/themes won't be extracted.[/dim]")

    console.print()
    return config


def _setup_gdrive(config):
    """Step 3: Configure Google Drive."""
    console.print("[bold]Step 3/4: Google Drive[/bold]")
    console.print("─" * 22)
    console.print()
    console.print("  [1] Skip (local files only)")
    console.print("  [2] Connect (ingest from cloud)")
    console.print()

    current = "2" if config.gdrive_enabled else "1"
    choice = typer.prompt("Choice", default=current)

    if choice == "2":
        config.gdrive_enabled = True

        try:
            from vectrola.gdrive import authenticate, is_authenticated

            if is_authenticated():
                console.print("[green]✓ Already authenticated[/green]")
                if typer.confirm("Re-authenticate?", default=False):
                    authenticate()
            else:
                console.print("Opening browser for authentication...")
                authenticate()
                console.print("[green]✓ Authenticated[/green]")

            if typer.confirm("Select allowed folders?", default=False):
                # Actually run the folder browser
                _browse_and_select_folders()

        except ImportError:
            console.print("[red]✗ Google Drive not installed[/red]")
            console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
            config.gdrive_enabled = False
    else:
        config.gdrive_enabled = False

    console.print()
    return config


def _setup_user(config):
    """Step 4: Configure user account."""
    from vectrola.config import get_current_user

    console.print("[bold]Step 4/4: User Account[/bold]")
    console.print("─" * 22)
    console.print()

    user_id, is_logged_in = get_current_user()

    if is_logged_in:
        console.print(f"[green]✓ Logged in as {user_id}[/green]")
        config.user_mode = "login"
    else:
        console.print(f"[dim]Anonymous user: {user_id}[/dim]")
        if typer.confirm("Login to sync across devices?", default=False):
            email = typer.prompt("Email or username")
            _do_setup_login(email)
            config.user_mode = "login"
        else:
            config.user_mode = "anonymous"

    console.print()
    return config


def _do_setup_login(email: str):
    """Perform login during setup."""
    import json
    from datetime import datetime

    email = email.strip().lower()
    if not email or len(email) < 3:
        console.print("[red]Invalid email/username[/red]")
        return

    session_path = Path.home() / ".config" / "vectrola" / "session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)

    session = {
        "user_id": email,
        "logged_in_at": datetime.utcnow().isoformat() + "Z"
    }
    session_path.write_text(json.dumps(session, indent=2))
    console.print(f"[green]✓ Logged in as {email}[/green]")


def _show_setup_summary(config):
    """Show setup completion summary."""
    from vectrola.config import CONFIG_PATH, get_current_user
    from urllib.parse import urlparse

    console.print("━" * 50)
    console.print()
    console.print("[bold green]✅ Setup complete![/bold green]")
    console.print()
    console.print(f"Config saved to: [dim]{CONFIG_PATH}[/dim]")
    console.print()

    table = Table(show_header=False, box=None)
    table.add_column("", style="bold")
    table.add_column("")

    # Storage
    if config.storage_mode == "remote":
        host = urlparse(config.qdrant_url).hostname or config.qdrant_url
        table.add_row("Storage", f"Remote ({host})")
    else:
        table.add_row("Storage", "Local")

    # LLM
    if config.llm_provider == "none":
        table.add_row("LLM", "Disabled")
    else:
        table.add_row("LLM", f"{config.llm_provider.title()} ({config.llm_model})")

    # GDrive
    if config.gdrive_enabled:
        table.add_row("GDrive", "Connected")
    else:
        table.add_row("GDrive", "Disabled")

    # User
    user_id, is_logged_in = get_current_user()
    if is_logged_in:
        table.add_row("User", f"{user_id} (logged in)")
    else:
        table.add_row("User", f"{user_id} (anonymous)")

    console.print(table)
    console.print()
    console.print("[dim]Next steps:[/dim]")
    console.print("  vectrola status          # Verify all components")
    console.print("  vectrola ingest ./music  # Ingest local files")
    if config.gdrive_enabled:
        console.print("  vectrola gdrive ingest   # Ingest from Google Drive")