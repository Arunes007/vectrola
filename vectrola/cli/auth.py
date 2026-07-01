"""Authentication commands: login, logout, whoami, migrate-user."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from qdrant_client import models

from vectrola.config import get_current_user, CONFIG_PATH
from vectrola.storage.qdrant import get_db
from vectrola.storage.wiki import WikiGenerator

from .helpers import console


def login():
    """
    Login to sync your library across devices.

    Your email/username is used as your user ID to sync your library
    across multiple devices. Without login, you're in anonymous mode
    which only works on a single device.
    """
    session_path = Path.home() / ".config" / "vectrola" / "session.json"

    if session_path.exists():
        try:
            session = json.loads(session_path.read_text())
            console.print(f"[yellow]Already logged in as: {session['user_id']}[/yellow]")
            console.print("[dim]Run 'vectrola logout' first to switch users.[/dim]")
            return
        except (json.JSONDecodeError, KeyError):
            pass

    email = typer.prompt("Email or username")

    # Basic validation
    email = email.strip().lower()
    if not email or len(email) < 3:
        console.print("[red]❌ Invalid email/username (must be at least 3 characters)[/red]")
        raise typer.Exit(1)

    # Save session
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session = {
        "user_id": email,
        "logged_in_at": datetime.utcnow().isoformat() + "Z"
    }
    session_path.write_text(json.dumps(session, indent=2))

    console.print(f"[green]✅ Logged in as {email}[/green]")
    console.print("[dim]   Your library will now sync across devices.[/dim]")

    # Check if setup has been run
    if not CONFIG_PATH.exists():
        console.print()
        console.print("[yellow]Next step:[/yellow] Run [bold]vectrola setup[/bold] to configure storage, LLM, and Google Drive.")
    else:
        # Regenerate wiki for the logged-in user
        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Generating wiki...", total=None)
            WikiGenerator().generate_all()


def logout(
    no_purge: bool = typer.Option(False, "--no-purge", help="Keep wiki and Google Drive connected"),
):
    """
    Logout and switch to anonymous mode.

    By default, deletes the wiki and revokes Google Drive access for privacy.
    Use --no-purge to keep them (e.g., if you plan to login again soon).
    """
    session_path = Path.home() / ".config" / "vectrola" / "session.json"
    gdrive_token_path = Path.home() / ".config" / "vectrola" / "gdrive_token.json"

    old_user = None
    if session_path.exists():
        try:
            session = json.loads(session_path.read_text())
            old_user = session.get("user_id")
        except (json.JSONDecodeError, KeyError):
            pass
        session_path.unlink()
        console.print("[green]✅ Logged out. Switched to anonymous mode.[/green]")

        if no_purge:
            console.print("[dim]Wiki and Google Drive kept (--no-purge).[/dim]")
        else:
            # Delete wiki
            wiki_dir = Path("./wiki")
            if wiki_dir.exists():
                shutil.rmtree(wiki_dir)
                console.print("[green]🗑️  Wiki deleted.[/green]")

            # Revoke Google Drive
            try:
                from vectrola.gdrive import logout as gdrive_logout
                if gdrive_logout():
                    console.print("[green]🗑️  Google Drive access revoked.[/green]")
            except ImportError:
                if gdrive_token_path.exists():
                    gdrive_token_path.unlink()
                    console.print("[green]🗑️  Google Drive access revoked.[/green]")
    else:
        console.print("[yellow]Not logged in.[/yellow]")


def whoami():
    """
    Show current user status.

    Displays whether you're logged in or using anonymous mode,
    and your current user ID.
    """
    user_id, is_logged_in = get_current_user()

    if is_logged_in:
        console.print(f"[bold green]Logged in as:[/bold green] {user_id}")
    else:
        console.print(f"[bold yellow]Anonymous user:[/bold yellow] {user_id}")
        console.print("[dim](Single device only. Run 'vectrola login' to sync across devices.)[/dim]")


def migrate_user(
    from_user: str = typer.Option(None, "--from", "-f", help="Source user ID to migrate from (default: current anon ID)"),
    to_user: str = typer.Option(None, "--to", "-t", help="Target user ID to migrate to (default: current logged-in user)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be migrated without making changes"),
):
    """
    Migrate tracks from one user ID to another.

    Use this to transfer your anonymous library to a logged-in account.
    For security, you can only migrate from this device's anonymous user.

    Examples:
        # Migrate current anon to logged-in user (most common)
        vectrola login
        vectrola migrate-user

        # Preview migration without changes
        vectrola migrate-user --dry-run
    """
    config_dir = Path.home() / ".config" / "vectrola"
    anon_path = config_dir / "anon_id"

    # Get this device's anonymous user ID
    local_anon_id = None
    if anon_path.exists():
        local_anon_id = anon_path.read_text().strip()

    # Determine source user
    if from_user is None:
        if local_anon_id:
            from_user = local_anon_id
        else:
            console.print("[red]No anonymous user ID found on this device.[/red]")
            console.print("[dim]You can only migrate from this device's anonymous user.[/dim]")
            raise typer.Exit(1)
    else:
        # Security check: only allow migrating from this device's anon user
        if from_user != local_anon_id:
            console.print(f"[red]Security error: Cannot migrate from '{from_user}'[/red]")
            console.print(f"[dim]You can only migrate from this device's anonymous user: {local_anon_id or '(none)'}[/dim]")
            raise typer.Exit(1)

    # Determine target user
    if to_user is None:
        current_user, is_logged_in = get_current_user()
        if is_logged_in and current_user != from_user:
            to_user = current_user
        else:
            console.print("[red]No logged-in user found. Run 'vectrola login' first.[/red]")
            raise typer.Exit(1)

    if from_user == to_user:
        console.print("[yellow]Source and target user are the same. Nothing to migrate.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Migration Plan[/bold]")
    console.print(f"  From: [yellow]{from_user}[/yellow]")
    console.print(f"  To:   [green]{to_user}[/green]")
    console.print()

    # Get database
    db = get_db()

    # Find all tracks in from_user's library
    try:
        from_library_entries = db.get_user_library_entries(from_user)
    except Exception as e:
        console.print(f"[red]Error querying user library: {e}[/red]")
        raise typer.Exit(1)

    if not from_library_entries:
        console.print(f"[yellow]No tracks found for user '{from_user}'.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found [bold]{len(from_library_entries)}[/bold] tracks to migrate.")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made. Remove --dry-run to apply.[/dim]")
        console.print("\nTracks that would be migrated:")

        # Fetch track details for preview
        track_ids = [entry.payload["track_id"] for entry in from_library_entries[:10]]

        preview_points, _ = db.client.scroll(
            collection_name=db.COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id",
                        match=models.MatchAny(any=track_ids)
                    )
                ]
            ),
            limit=10,
        )

        for point in preview_points:
            title = point.payload.get("title", "Unknown")
            artists = ", ".join(point.payload.get("artists", [])[:2])
            console.print(f"  • {title} - {artists}")
        if len(from_library_entries) > 10:
            console.print(f"  ... and {len(from_library_entries) - 10} more")
        raise typer.Exit(0)

    # Confirm migration
    if not typer.confirm(f"\nMigrate {len(from_library_entries)} tracks from '{from_user}' to '{to_user}'?"):
        console.print("[yellow]Migration cancelled.[/yellow]")
        raise typer.Exit(0)

    # Perform migration
    migrated = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Migrating tracks...", total=len(from_library_entries))

        for entry in from_library_entries:
            track_id = entry.payload["track_id"]
            source = entry.payload.get("source", "local")
            file_path = entry.payload.get("file_path")
            gdrive_file_id = entry.payload.get("gdrive_file_id")

            try:
                # Add track to target user's library
                db.add_track_to_user_library(
                    user_id=to_user,
                    track_id=track_id,
                    source=source,
                    file_path=file_path,
                    gdrive_file_id=gdrive_file_id,
                )

                # Remove from source user's library
                db.remove_track_from_user_library(
                    user_id=from_user,
                    track_id=track_id,
                )

                migrated += 1
            except Exception as e:
                console.print(f"[red]Error migrating track {track_id}: {e}[/red]")

            progress.advance(task)

    console.print(f"\n[green]✅ Migrated {migrated}/{len(from_library_entries)} tracks successfully![/green]")

    # Optionally clean up anon_id file
    if from_user.startswith("anon_") and anon_path.exists():
        if typer.confirm("\nRemove anonymous ID file? (You're now using the logged-in account)"):
            anon_path.unlink()
            console.print("[dim]Removed ~/.config/vectrola/anon_id[/dim]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  • Run 'vectrola library list' to see your migrated tracks")
    console.print("  • Run 'vectrola wiki' to regenerate your wiki")
