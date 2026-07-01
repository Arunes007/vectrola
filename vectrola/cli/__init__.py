"""Vectrola CLI - Command Line Interface Package."""

import typer
from rich.console import Console

# Create console instance to be shared across all CLI modules
console = Console()

# Create main app
app = typer.Typer(
    name="vectrola",
    help="🎧 Vectrola: Multimodal Music Knowledge Graph\n\nSemantic music search using audio embeddings and LLM synthesis.",
    add_completion=False,
    invoke_without_command=True,
)

# Create gdrive subcommand group
gdrive_app = typer.Typer(
    name="gdrive",
    help="🌐 Google Drive integration for cloud music ingestion.",
)
app.add_typer(gdrive_app, name="gdrive")

# Import commands from submodules
from .helpers import show_welcome, status
from .core import ingest, analyze, search, similar, wiki, refresh
from .auth import login, logout, whoami, migrate_user
from .setup import setup
from .gdrive import (
    gdrive_auth,
    gdrive_list,
    gdrive_ingest,
    gdrive_status,
    gdrive_revoke,
)

# Attach welcome callback using decorator syntax
@app.callback()
def callback_wrapper(ctx: typer.Context):
    """Wrapper to call show_welcome."""
    show_welcome(ctx)

# Register commands to main app
app.command()(ingest)
app.command()(analyze)
app.command()(search)
app.command()(similar)
app.command()(wiki)
app.command()(refresh)
app.command()(login)
app.command()(logout)
app.command()(whoami)
app.command("migrate-user")(migrate_user)
app.command()(setup)
app.command()(status)

# Register commands to gdrive subapp
gdrive_app.command("auth")(gdrive_auth)
gdrive_app.command("list")(gdrive_list)
gdrive_app.command("ingest")(gdrive_ingest)
gdrive_app.command("status")(gdrive_status)
gdrive_app.command("revoke")(gdrive_revoke)


def main():
    """Entry point for the CLI."""
    app()


__all__ = ["app", "main", "console"]
