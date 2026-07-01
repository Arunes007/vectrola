"""Google Drive commands for cloud music ingestion."""

import json
import tempfile
import shutil
from pathlib import Path

import typer
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from vectrola.config import load_config, CONFIG_PATH
from vectrola.gdrive import (
    authenticate,
    logout,
    is_authenticated,
    DriveClient,
)
from vectrola.ingest.pipeline import IngestPipeline
from vectrola.services.failed_ingests import FailedIngestsManager, detect_error_stage

from .helpers import console


def browse_and_select_folders():
    """Interactive folder browser for selecting GDrive folders."""
    try:
        from vectrola.gdrive import DriveClient  # add_allowed_folder, get_allowed_folders not available
    except ImportError:
        return

    client = DriveClient()
    current_path = "/"
    selected_folders = []

    console.print("[bold]Navigate with numbers, 's' to select current folder, 'd' when done[/bold]")
    console.print()

    while True:
        # List current directory
        try:
            items = list(client.list_contents(current_path))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            break

        folders = [f for f in items if f.is_folder]
        audio_files = [f for f in items if not f.is_folder]

        # Show current location
        display_path = current_path if current_path != "/" else "/ (root)"
        console.print(f"\n[bold blue]📁 {display_path}[/bold blue]")
        console.print(f"[dim]{len(audio_files)} audio files in this folder[/dim]")
        console.print()

        # Show navigation options
        console.print("[dim]0.[/dim] .. [dim](go up)[/dim]")
        for i, folder in enumerate(folders, 1):
            console.print(f"[dim]{i}.[/dim] 📁 {folder.name}")

        console.print()
        if selected_folders:
            console.print(f"[green]Selected: {len(selected_folders)} folder(s)[/green]")

        # Get user input
        console.print()
        choice = typer.prompt(
            "Enter number, [s]elect this folder, or [d]one",
            default="d"
        ).strip().lower()

        if choice == "d":
            break
        elif choice == "s":
            # Select current folder
            folder_id = client.resolve_path(current_path)
            if folder_id and current_path not in [f[1] for f in selected_folders]:
                selected_folders.append((folder_id, current_path))
                console.print(f"[green]✓ Added: {current_path}[/green]")
            elif current_path in [f[1] for f in selected_folders]:
                console.print("[yellow]Already selected[/yellow]")
        elif choice == "0":
            # Go up
            if current_path != "/":
                current_path = "/".join(current_path.rstrip("/").split("/")[:-1]) or "/"
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                folder = folders[idx]
                if current_path == "/":
                    current_path = f"/{folder.name}"
                else:
                    current_path = f"{current_path}/{folder.name}"
            else:
                console.print("[red]Invalid number[/red]")
        else:
            console.print("[red]Invalid choice[/red]")

    # Save selected folders
    if selected_folders:
        for folder_id, folder_path in selected_folders:
            pass  # add_allowed_folder(folder_id, folder_path) - temporarily disabled

        console.print()
        console.print(f"[green]✓ Access granted to {len(selected_folders)} folder(s):[/green]")
        for _, path in selected_folders:
            console.print(f"  📁 {path}")
        console.print()
        console.print("[dim]Now run: vectrola gdrive ingest <folder>[/dim]")
    else:
        console.print()
        console.print("[yellow]No folders selected.[/yellow]")
        console.print("[dim]You can browse later with: vectrola gdrive list[/dim]")


def gdrive_auth(
    logout: bool = typer.Option(False, "--logout", help="Remove stored credentials"),
    force: bool = typer.Option(False, "--force", help="Force re-authentication"),
):
    """
    Authenticate with Google Drive and create Vectrola folder.

    Opens your browser for Google sign-in via vectrola-oauth.up.railway.app.
    After authorization, creates /Vectrola/audio and /Vectrola/wiki folders.
    """
    try:
        from vectrola.gdrive import authenticate, logout as do_logout, is_authenticated
        from vectrola.gdrive.client import DriveClient
        from vectrola.config import load_config, CONFIG_PATH
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if logout:
        if do_logout():
            console.print("[green]✓ Logged out from Google Drive[/green]")
        else:
            console.print("[dim]No credentials to remove[/dim]")
        return

    already_authed = is_authenticated()

    if already_authed and not force:
        console.print("[green]✓ Already authenticated with Google Drive[/green]")
    else:
        try:
            creds = authenticate(force=force)
            if not creds:
                console.print("[red]Authentication failed or cancelled[/red]")
                raise typer.Exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Authentication cancelled by user[/yellow]")
            raise typer.Exit(0)
        except Exception as e:
            console.print(f"[red]Authentication error: {e}[/red]")
            raise typer.Exit(1)

    # Create Vectrola folders
    console.print()
    console.print("[bold cyan]Setting up Vectrola folders in Google Drive...[/bold cyan]")

    try:
        client = DriveClient()
        audio_id, wiki_id = client.ensure_vectrola_folders()

        # Save folder IDs to config
        config = load_config()
        config.gdrive_enabled = True
        config.gdrive_audio_folder_id = audio_id
        config.gdrive_wiki_folder_id = wiki_id

        # Save to config.json
        import json
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if CONFIG_PATH.exists():
            config_data = json.loads(CONFIG_PATH.read_text())
        else:
            config_data = {}

        if "gdrive" not in config_data:
            config_data["gdrive"] = {}

        config_data["gdrive"]["enabled"] = True
        config_data["gdrive"]["audio_folder_id"] = audio_id
        config_data["gdrive"]["wiki_folder_id"] = wiki_id

        CONFIG_PATH.write_text(json.dumps(config_data, indent=2))

        console.print("[green]✅ Vectrola folders created:[/green]")
        console.print(f"  📁 /Vectrola/audio (ID: {audio_id})")
        console.print(f"  📁 /Vectrola/wiki (ID: {wiki_id})")
        console.print()
        console.print("[dim]Now run: vectrola ingest <path> && vectrola wiki --sync[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to create folders: {e}[/red]")
        raise typer.Exit(1)


def gdrive_list(
    path: str = typer.Argument("/", help="Drive folder path to list"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Include subfolders (audio files only)"),
):
    """
    Browse Google Drive folders and audio files.

    Shows folders and audio files at the given path. Use --recursive to
    find all audio files in subfolders.

    Examples:
        vectrola gdrive list                     # Browse root
        vectrola gdrive list /Music              # Browse Music folder
        vectrola gdrive list /Music --recursive  # Find all audio in Music
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient  # is_path_allowed, get_allowed_folders not available
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[red]Not authenticated. Run 'vectrola gdrive auth' first.[/red]")
        raise typer.Exit(1)

    client = DriveClient()

    # Check if path is allowed
    # allowed_folders = get_allowed_folders()  # Feature temporarily disabled
    if False:  # Allowed folders check temporarily disabled
        console.print(f"[red]Access denied: {path}[/red]")
        console.print("[dim]This folder is not in your allowed list.[/dim]")
        console.print("[dim]Allowed folders:[/dim]")
        for fpath in allowed_folders.values():
            console.print(f"[dim]  📁 {fpath}[/dim]")
        raise typer.Exit(1)

    try:
        if recursive:
            # Recursive mode: only show audio files
            items = list(client.list_files(path, recursive=True))
        else:
            # Browse mode: show folders and audio files
            items = list(client.list_contents(path))
    except FileNotFoundError:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing files: {e}[/red]")
        raise typer.Exit(1)

    if not items:
        console.print(f"[yellow]Empty folder: {path}[/yellow]")
        return

    # Count folders and files
    folders = [f for f in items if f.is_folder]
    audio_files = [f for f in items if not f.is_folder]

    # Display table
    display_path = path if path != "/" else "/ (root)"
    table = Table(title=f"📁 {display_path}")
    table.add_column("Name")
    table.add_column("Type", justify="center")
    table.add_column("Size", justify="right")

    for f in items:
        if f.is_folder:
            table.add_row(f"📁 {f.name}", "[blue]folder[/blue]", "-")
        else:
            table.add_row(f"🎵 {f.name}", f.extension, f"{f.size_mb:.1f} MB")

    console.print(table)
    console.print(f"\n[dim]{len(folders)} folders, {len(audio_files)} audio files[/dim]")

    if folders and not recursive:
        console.print("[dim]Tip: Use 'vectrola gdrive list <folder>' to browse deeper[/dim]")


def gdrive_ingest(
    path: str = typer.Argument(..., help="Drive folder path to ingest"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r/-R", help="Include subfolders"),
    fast: bool = typer.Option(True, "--fast/--slow", "-f/-s", help="Skip Demucs stem separation"),
):
    """
    Ingest audio files from Google Drive into the knowledge graph.

    Downloads files temporarily, processes them with the full pipeline
    (metadata, lyrics, embeddings), then cleans up.

    Examples:
        vectrola gdrive ingest "/Music"
        vectrola gdrive ingest "/Music/Bollywood" --recursive
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[red]Not authenticated. Run 'vectrola gdrive auth' first.[/red]")
        raise typer.Exit(1)

    from vectrola.ingest.pipeline import IngestPipeline
    from vectrola.services.failed_ingests import FailedIngestsManager, detect_error_stage

    client = DriveClient()
    fm = FailedIngestsManager()

    # List files to ingest
    console.print(f"[dim]Scanning {path}...[/dim]")

    try:
        files = list(client.list_files(path, recursive=recursive))
    except FileNotFoundError:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing files: {e}[/red]")
        raise typer.Exit(1)

    if not files:
        console.print(f"[yellow]No audio files found in {path}[/yellow]")
        return

    total = len(files)
    console.print(f"🎧 Found {total} audio file(s) in Google Drive")

    if fast:
        console.print("   Fast mode: skipping Demucs vocal separation")
    console.print()

    pipeline = IngestPipeline(use_stems=not fast)

    # Create temp directory for downloads
    temp_dir = Path(tempfile.mkdtemp(prefix="vectrola_gdrive_"))

    results = []
    errors = []

    try:
        for i, file in enumerate(files, 1):
            console.print(f"[{i}/{total}] {file.name}")

            try:
                # Download file
                console.print(f"   ↓ Downloading from Drive...", end="")
                local_path = client.download_file(file, temp_dir)
                console.print(" done")

                # Process with pipeline (Day 7: pass GDrive file ID for playback)
                result = pipeline.process_track(
                    local_path,
                    write_file_tags=False,
                    gdrive_file_id=file.id,  # Day 7: Store GDrive ID for playback
                    gdrive_path=f"{file.parent_path}/{file.name}",  # Day 7: Original path in Drive
                )

                results.append(result)
                moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
                console.print(f"   ✓ Done: {moods_str}")

                # Remove from failed list if it was there (successful re-ingest)
                fm.remove_failed(f"gdrive:{file.id}")

                # Clean up this file immediately to save space
                local_path.unlink()

            except Exception as e:
                errors.append((file, str(e)))
                console.print(f"   ✗ Error: {e}")

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Save failures for retry
    if errors:
        for file, error_msg in errors:
            fm.add_failed(
                name=file.name,
                source="gdrive",
                source_path=f"{file.parent_path}/{file.name}",
                error=error_msg,
                error_stage=detect_error_stage(error_msg),
                gdrive_file_id=file.id,
            )

    # Summary
    console.print()
    console.print(f"✅ Processed: {len(results)} tracks from Google Drive")
    if errors:
        console.print(f"❌ Errors: {len(errors)} tracks")
        console.print("[yellow]Failed tracks saved. Run 'vectrola retry' to retry.[/yellow]")

    # Next steps
    if results:
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print("  • Search your library:   [cyan]vectrola search \"romantic mood\"[/cyan]")
        console.print("  • Generate Obsidian wiki: [cyan]vectrola wiki[/cyan]")
        console.print("  • Sync wiki to Drive:    [cyan]vectrola wiki --sync[/cyan]")



def gdrive_status():
    """
    Show Google Drive authentication status and quota.
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[yellow]Not authenticated with Google Drive[/yellow]")
        console.print("[dim]Run 'vectrola gdrive auth' to connect[/dim]")
        return

    client = DriveClient()

    try:
        user = client.get_user_info()
        quota = client.get_quota()

        console.print("[green]✓ Authenticated with Google Drive[/green]")
        console.print()

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Account", user.get("emailAddress", "Unknown"))
        table.add_row("Name", user.get("displayName", "Unknown"))

        # Format quota
        usage = int(quota.get("usage", 0))
        limit = int(quota.get("limit", 0))

        if limit > 0:
            usage_gb = usage / (1024**3)
            limit_gb = limit / (1024**3)
            pct = (usage / limit) * 100
            table.add_row("Storage", f"{usage_gb:.1f} GB / {limit_gb:.1f} GB ({pct:.0f}%)")
        else:
            table.add_row("Storage", "Unlimited")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")
        raise typer.Exit(1)




def gdrive_revoke():
    """
    Revoke Google Drive access and delete stored credentials.

    This disconnects Vectrola from your Google Drive. You'll need to
    run 'vectrola gdrive auth' again to reconnect.

    Use this when:
    - Switching to a different Google account
    - Troubleshooting authentication issues
    - Privacy cleanup
    """
    try:
        from vectrola.gdrive import logout as do_logout
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        raise typer.Exit(1)

    if do_logout():
        console.print("[green]✓ Google Drive access revoked.[/green]")
        console.print("[dim]Run 'vectrola gdrive auth' to reconnect.[/dim]")
    else:
        console.print("[yellow]Google Drive not connected.[/yellow]")


def gdrive_auth(
    logout: bool = typer.Option(False, "--logout", help="Remove stored credentials"),
    force: bool = typer.Option(False, "--force", help="Force re-authentication"),
):
    """
    Authenticate with Google Drive and create Vectrola folder.

    Opens your browser for Google sign-in via vectrola-oauth.up.railway.app.
    After authorization, creates /Vectrola/audio and /Vectrola/wiki folders.
    """
    try:
        from vectrola.gdrive import authenticate, logout as do_logout, is_authenticated
        from vectrola.gdrive.client import DriveClient
        from vectrola.config import load_config, CONFIG_PATH
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if logout:
        if do_logout():
            console.print("[green]✓ Logged out from Google Drive[/green]")
        else:
            console.print("[dim]No credentials to remove[/dim]")
        return

    already_authed = is_authenticated()

    if already_authed and not force:
        console.print("[green]✓ Already authenticated with Google Drive[/green]")
    else:
        try:
            creds = authenticate(force=force)
            if not creds:
                console.print("[red]Authentication failed or cancelled[/red]")
                raise typer.Exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Authentication cancelled by user[/yellow]")
            raise typer.Exit(0)
        except Exception as e:
            console.print(f"[red]Authentication error: {e}[/red]")
            raise typer.Exit(1)

    # Create Vectrola folders
    console.print()
    console.print("[bold cyan]Setting up Vectrola folders in Google Drive...[/bold cyan]")

    try:
        client = DriveClient()
        audio_id, wiki_id = client.ensure_vectrola_folders()

        # Save folder IDs to config
        config = load_config()
        config.gdrive_enabled = True
        config.gdrive_audio_folder_id = audio_id
        config.gdrive_wiki_folder_id = wiki_id

        # Save to config.json
        import json
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if CONFIG_PATH.exists():
            config_data = json.loads(CONFIG_PATH.read_text())
        else:
            config_data = {}

        if "gdrive" not in config_data:
            config_data["gdrive"] = {}

        config_data["gdrive"]["enabled"] = True
        config_data["gdrive"]["audio_folder_id"] = audio_id
        config_data["gdrive"]["wiki_folder_id"] = wiki_id

        CONFIG_PATH.write_text(json.dumps(config_data, indent=2))

        console.print("[green]✅ Vectrola folders created:[/green]")
        console.print(f"  📁 /Vectrola/audio (ID: {audio_id})")
        console.print(f"  📁 /Vectrola/wiki (ID: {wiki_id})")
        console.print()
        console.print("[dim]Now run: vectrola ingest <path> && vectrola wiki --sync[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to create folders: {e}[/red]")
        raise typer.Exit(1)


def gdrive_list(
    path: str = typer.Argument("/", help="Drive folder path to list"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Include subfolders (audio files only)"),
):
    """
    Browse Google Drive folders and audio files.

    Shows folders and audio files at the given path. Use --recursive to
    find all audio files in subfolders.

    Examples:
        vectrola gdrive list                     # Browse root
        vectrola gdrive list /Music              # Browse Music folder
        vectrola gdrive list /Music --recursive  # Find all audio in Music
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient  # is_path_allowed, get_allowed_folders not available
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[red]Not authenticated. Run 'vectrola gdrive auth' first.[/red]")
        raise typer.Exit(1)

    client = DriveClient()

    # Check if path is allowed
    # allowed_folders = get_allowed_folders()  # Feature temporarily disabled
    if False:  # Allowed folders check temporarily disabled
        console.print(f"[red]Access denied: {path}[/red]")
        console.print("[dim]This folder is not in your allowed list.[/dim]")
        console.print("[dim]Allowed folders:[/dim]")
        for fpath in allowed_folders.values():
            console.print(f"[dim]  📁 {fpath}[/dim]")
        raise typer.Exit(1)

    try:
        if recursive:
            # Recursive mode: only show audio files
            items = list(client.list_files(path, recursive=True))
        else:
            # Browse mode: show folders and audio files
            items = list(client.list_contents(path))
    except FileNotFoundError:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing files: {e}[/red]")
        raise typer.Exit(1)

    if not items:
        console.print(f"[yellow]Empty folder: {path}[/yellow]")
        return

    # Count folders and files
    folders = [f for f in items if f.is_folder]
    audio_files = [f for f in items if not f.is_folder]

    # Display table
    display_path = path if path != "/" else "/ (root)"
    table = Table(title=f"📁 {display_path}")
    table.add_column("Name")
    table.add_column("Type", justify="center")
    table.add_column("Size", justify="right")

    for f in items:
        if f.is_folder:
            table.add_row(f"📁 {f.name}", "[blue]folder[/blue]", "-")
        else:
            table.add_row(f"🎵 {f.name}", f.extension, f"{f.size_mb:.1f} MB")

    console.print(table)
    console.print(f"\n[dim]{len(folders)} folders, {len(audio_files)} audio files[/dim]")

    if folders and not recursive:
        console.print("[dim]Tip: Use 'vectrola gdrive list <folder>' to browse deeper[/dim]")


def gdrive_ingest(
    path: str = typer.Argument(..., help="Drive folder path to ingest"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r/-R", help="Include subfolders"),
    fast: bool = typer.Option(True, "--fast/--slow", "-f/-s", help="Skip Demucs stem separation"),
):
    """
    Ingest audio files from Google Drive into the knowledge graph.

    Downloads files temporarily, processes them with the full pipeline
    (metadata, lyrics, embeddings), then cleans up.

    Examples:
        vectrola gdrive ingest "/Music"
        vectrola gdrive ingest "/Music/Bollywood" --recursive
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[red]Not authenticated. Run 'vectrola gdrive auth' first.[/red]")
        raise typer.Exit(1)

    from vectrola.ingest.pipeline import IngestPipeline
    from vectrola.services.failed_ingests import FailedIngestsManager, detect_error_stage

    client = DriveClient()
    fm = FailedIngestsManager()

    # List files to ingest
    console.print(f"[dim]Scanning {path}...[/dim]")

    try:
        files = list(client.list_files(path, recursive=recursive))
    except FileNotFoundError:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error listing files: {e}[/red]")
        raise typer.Exit(1)

    if not files:
        console.print(f"[yellow]No audio files found in {path}[/yellow]")
        return

    total = len(files)
    console.print(f"🎧 Found {total} audio file(s) in Google Drive")

    if fast:
        console.print("   Fast mode: skipping Demucs vocal separation")
    console.print()

    pipeline = IngestPipeline(use_stems=not fast)

    # Create temp directory for downloads
    temp_dir = Path(tempfile.mkdtemp(prefix="vectrola_gdrive_"))

    results = []
    errors = []

    try:
        for i, file in enumerate(files, 1):
            console.print(f"[{i}/{total}] {file.name}")

            try:
                # Download file
                console.print(f"   ↓ Downloading from Drive...", end="")
                local_path = client.download_file(file, temp_dir)
                console.print(" done")

                # Process with pipeline (Day 7: pass GDrive file ID for playback)
                result = pipeline.process_track(
                    local_path,
                    write_file_tags=False,
                    gdrive_file_id=file.id,  # Day 7: Store GDrive ID for playback
                    gdrive_path=f"{file.parent_path}/{file.name}",  # Day 7: Original path in Drive
                )

                results.append(result)
                moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
                console.print(f"   ✓ Done: {moods_str}")

                # Remove from failed list if it was there (successful re-ingest)
                fm.remove_failed(f"gdrive:{file.id}")

                # Clean up this file immediately to save space
                local_path.unlink()

            except Exception as e:
                errors.append((file, str(e)))
                console.print(f"   ✗ Error: {e}")

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Save failures for retry
    if errors:
        for file, error_msg in errors:
            fm.add_failed(
                name=file.name,
                source="gdrive",
                source_path=f"{file.parent_path}/{file.name}",
                error=error_msg,
                error_stage=detect_error_stage(error_msg),
                gdrive_file_id=file.id,
            )

    # Summary
    console.print()
    console.print(f"✅ Processed: {len(results)} tracks from Google Drive")
    if errors:
        console.print(f"❌ Errors: {len(errors)} tracks")
        console.print("[yellow]Failed tracks saved. Run 'vectrola retry' to retry.[/yellow]")

    # Next steps
    if results:
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print("  • Search your library:   [cyan]vectrola search \"romantic mood\"[/cyan]")
        console.print("  • Generate Obsidian wiki: [cyan]vectrola wiki[/cyan]")
        console.print("  • Sync wiki to Drive:    [cyan]vectrola wiki --sync[/cyan]")



def gdrive_status():
    """
    Show Google Drive authentication status and quota.
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[yellow]Not authenticated with Google Drive[/yellow]")
        console.print("[dim]Run 'vectrola gdrive auth' to connect[/dim]")
        return

    client = DriveClient()

    try:
        user = client.get_user_info()
        quota = client.get_quota()

        console.print("[green]✓ Authenticated with Google Drive[/green]")
        console.print()

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Account", user.get("emailAddress", "Unknown"))
        table.add_row("Name", user.get("displayName", "Unknown"))

        # Format quota
        usage = int(quota.get("usage", 0))
        limit = int(quota.get("limit", 0))

        if limit > 0:
            usage_gb = usage / (1024**3)
            limit_gb = limit / (1024**3)
            pct = (usage / limit) * 100
            table.add_row("Storage", f"{usage_gb:.1f} GB / {limit_gb:.1f} GB ({pct:.0f}%)")
        else:
            table.add_row("Storage", "Unlimited")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")
        raise typer.Exit(1)




def gdrive_revoke():
    """
    Revoke Google Drive access and delete stored credentials.

    This disconnects Vectrola from your Google Drive. You'll need to
    run 'vectrola gdrive auth' again to reconnect.

    Use this when:
    - Switching to a different Google account
    - Troubleshooting authentication issues
    - Privacy cleanup
    """
    try:
        from vectrola.gdrive import logout as do_logout
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        raise typer.Exit(1)

    if do_logout():
        console.print("[green]✓ Google Drive access revoked.[/green]")
        console.print("[dim]Run 'vectrola gdrive auth' to reconnect.[/dim]")
    else:
        console.print("[yellow]Google Drive not connected.[/yellow]")