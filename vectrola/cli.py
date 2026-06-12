"""Vectrola CLI - Multimodal Music Knowledge Graph."""

import typer
from pathlib import Path
from typing import Optional
import tempfile
import shutil

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="vectrola",
    help="🎧 Vectrola: Multimodal Music Knowledge Graph\n\nSemantic music search using audio embeddings and LLM synthesis.",
    add_completion=False,
)
console = Console()

# Google Drive subcommand group
gdrive_app = typer.Typer(
    name="gdrive",
    help="🌐 Google Drive integration for cloud music ingestion.",
)
app.add_typer(gdrive_app, name="gdrive")

# Library subcommand group (Day 7)
library_app = typer.Typer(
    name="library",
    help="📚 Manage your track library.",
)
app.add_typer(library_app, name="library")


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r/-R", help="Scan subdirectories"),
    fast: bool = typer.Option(True, "--fast/--slow", "-f/-s", help="Skip Demucs stem separation (faster)"),
    write_tags: bool = typer.Option(True, "--tags/--no-tags", help="Write analysis to file tags"),
):
    """
    Ingest audio files into the knowledge graph.

    Transcribes lyrics and extracts semantic metadata (themes, moods, narrative).
    """
    from vectrola.ingest.pipeline import IngestPipeline

    # Collect files to process
    if path.is_file():
        files = [path]
    else:
        pattern = "**/*" if recursive else "*"
        files = []
        for ext in [".mp3", ".flac", ".wav", ".m4a", ".ogg"]:
            files.extend(path.glob(f"{pattern}{ext}"))
            files.extend(path.glob(f"{pattern}{ext.upper()}"))

    if not files:
        print("⚠️  No audio files found.")
        raise typer.Exit(1)

    total = len(files)
    print(f"🎧 Found {total} audio file(s)")

    if fast:
        print("   Fast mode: skipping Demucs vocal separation")
    print()

    pipeline = IngestPipeline(use_stems=not fast)

    # Process files with simple progress
    results = []
    errors = []

    for i, file in enumerate(files, 1):
        print(f"[{i}/{total}] {file.name}", flush=True)
        try:
            result = pipeline.process_track(file, write_file_tags=write_tags)
            results.append(result)
            moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
            print(f"   ✓ Done: {moods_str}")

        except Exception as e:
            errors.append((file, str(e)))
            print(f"   ✗ Error: {e}")

    # Summary
    print()
    print(f"✅ Processed: {len(results)} tracks")
    if errors:
        print(f"❌ Errors: {len(errors)} tracks")


@app.command()
def analyze(
    file: Path = typer.Argument(..., help="Audio file to analyze"),
):
    """
    Analyze a single audio file and show detailed results.

    Does NOT write to file tags - use 'ingest' for that.
    """
    from vectrola.ingest.pipeline import IngestPipeline

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Analyzing {file.name}...[/dim]")

    pipeline = IngestPipeline(use_stems=False)

    with console.status("Transcribing audio..."):
        result = pipeline.process_track(file, write_file_tags=False)

    # Display results in a nice table
    console.print()
    console.print(f"[bold cyan]📀 {result.title}[/bold cyan]")
    console.print()

    # Metadata table
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Language", result.language)
    table.add_row("Moods", ", ".join(result.moods) if result.moods else "[dim]none[/dim]")
    table.add_row("Themes", ", ".join(result.themes) if result.themes else "[dim]none[/dim]")
    table.add_row("Imagery", ", ".join(result.imagery) if result.imagery else "[dim]none[/dim]")

    console.print(table)

    if result.narrative:
        console.print()
        console.print("[bold]Narrative:[/bold]")
        console.print(f"  {result.narrative}")

    # Show lyrics preview
    if result.lyrics:
        console.print()
        console.print("[bold]Lyrics Preview:[/bold]")
        preview = result.lyrics[:500] + "..." if len(result.lyrics) > 500 else result.lyrics
        console.print(f"[dim]{preview}[/dim]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results"),
    mode: str = typer.Option("hybrid", "--mode", "-m", help="Search mode: hybrid, lyrics, or audio"),
):
    """
    Search music by vibe/description.

    Examples:
        vectrola search "melancholic songs about heartbreak"
        vectrola search "upbeat Hindi party songs"
        vectrola search "romantic duets from 90s Bollywood"
        vectrola search "dark ambient texture" --mode audio
    """
    from vectrola.search.semantic import SemanticSearch

    # Check Qdrant is running
    try:
        from vectrola.storage.qdrant import get_db
        db = get_db()
        count = db.count()
    except Exception as e:
        console.print("[red]Error: Cannot connect to Qdrant.[/red]")
        console.print("[dim]Start it with: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")
        raise typer.Exit(1)

    if count == 0:
        console.print("[yellow]No tracks indexed yet. Run 'vectrola ingest' first.[/yellow]")
        raise typer.Exit(1)

    mode_label = {"hybrid": "hybrid (lyrics + audio)", "lyrics": "lyrics only", "audio": "audio only"}
    console.print(f"[dim]Searching {count} tracks... [{mode_label.get(mode, mode)}][/dim]")

    searcher = SemanticSearch()
    results = searcher.search(query, limit=limit, mode=mode)

    if not results:
        console.print("[yellow]No matching tracks found.[/yellow]")
        raise typer.Exit(0)

    console.print()
    console.print(f"[bold]Results for:[/bold] {query}")
    console.print()

    for i, r in enumerate(results, 1):
        artist_str = ", ".join(r.artists) if r.artists else "Unknown"
        console.print(f"[cyan]{i}. {artist_str} - {r.title}[/cyan] [dim](score: {r.score:.2f})[/dim]")

        if r.movie and r.movie != r.album:
            console.print(f"   [dim]Movie: {r.movie}[/dim]")

        if r.moods:
            console.print(f"   Moods: {', '.join(r.moods)}")

        if r.themes:
            console.print(f"   Themes: {', '.join(r.themes)}")

        console.print()


@app.command()
def similar(
    track_name: str = typer.Argument(..., help="Track name or file path"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results"),
    mode: str = typer.Option("audio", "--mode", "-m", help="Similarity mode: audio (acoustic) or lyrics"),
):
    """
    Find tracks similar to a given track.

    Acoustic similarity (default) finds tracks that sound similar.
    Lyrics similarity finds tracks with similar themes/moods.

    Examples:
        vectrola similar "Tum Hi Ho"
        vectrola similar "Ae Dil Hai Mushkil" --mode lyrics
        vectrola similar /path/to/song.mp3
    """
    from vectrola.search.semantic import SemanticSearch
    from vectrola.storage.qdrant import get_db

    # Check if it's a file path
    track_path = Path(track_name)
    if not track_path.exists():
        # Search for track by name
        db = get_db()
        tracks = db.list_all(limit=500)

        # Find matching track
        matching = None
        for t in tracks:
            title = t.payload.get("title", "").lower()
            if track_name.lower() in title:
                matching = t.payload.get("file_path")
                console.print(f"[dim]Found: {t.payload.get('title')}[/dim]")
                break

        if not matching:
            console.print(f"[red]Track not found: {track_name}[/red]")
            console.print("[dim]Tip: Use full path or exact title[/dim]")
            raise typer.Exit(1)

        track_path = Path(matching)

    mode_label = "acoustic" if mode == "audio" else "lyrical"
    console.print(f"[dim]Finding {mode_label} similarity...[/dim]")

    searcher = SemanticSearch()
    results = searcher.find_similar(str(track_path), limit=limit, mode=mode)

    if not results:
        console.print("[yellow]No similar tracks found.[/yellow]")
        if mode == "audio":
            console.print("[dim]Make sure tracks have audio embeddings (run scripts/add_audio_embeddings.py)[/dim]")
        raise typer.Exit(0)

    console.print()
    console.print(f"[bold]Tracks similar to:[/bold] {track_path.stem}")
    console.print()

    for i, r in enumerate(results, 1):
        artist_str = ", ".join(r.artists) if r.artists else "Unknown"
        console.print(f"[cyan]{i}. {artist_str} - {r.title}[/cyan] [dim](similarity: {r.score:.2f})[/dim]")

        if r.moods:
            console.print(f"   Moods: {', '.join(r.moods)}")

        console.print()


@app.command()
def wiki(
    output: Path = typer.Option(Path("./wiki"), "--output", "-o", help="Wiki output directory"),
    sync: bool = typer.Option(False, "--sync", "-s", help="Upload wiki to Google Drive after generation"),
    drive_path: str = typer.Option("/Vectrola/wiki", "--drive-path", help="Google Drive folder path for sync"),
):
    """
    Generate Obsidian wiki from indexed tracks.

    Creates markdown pages with wikilinks for tracks, artists, moods, themes, and movies.
    Open the generated directory in Obsidian to explore the music knowledge graph.

    Use --sync to upload the wiki to Google Drive for cross-device access.
    """
    from vectrola.storage.wiki import WikiGenerator

    # Check if there are indexed tracks
    try:
        from vectrola.storage.qdrant import get_db
        db = get_db()
        count = db.count()
    except Exception as e:
        console.print("[red]Error: Cannot connect to Qdrant.[/red]")
        console.print("[dim]Start it with: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")
        raise typer.Exit(1)

    if count == 0:
        console.print("[yellow]No tracks indexed yet. Run 'vectrola ingest' first.[/yellow]")
        raise typer.Exit(1)

    # Generate wiki
    generator = WikiGenerator(output)
    generator.generate_all()

    console.print()
    console.print(f"[green]✅ Wiki generated at: {output}[/green]")

    # Sync to Google Drive if requested
    if sync:
        console.print()
        console.print("[bold]☁️  Syncing wiki to Google Drive...[/bold]")

        try:
            from vectrola.gdrive import is_authenticated
            from vectrola.gdrive.client import DriveClient

            if not is_authenticated():
                console.print("[red]Not authenticated with Google Drive.[/red]")
                console.print("[dim]Run 'vectrola gdrive auth' first.[/dim]")
                raise typer.Exit(1)

            client = DriveClient()
            _upload_wiki_to_drive(client, output, drive_path)

            console.print()
            console.print(f"[green]✅ Wiki synced to Google Drive: {drive_path}[/green]")

        except ImportError:
            console.print("[red]Google Drive support not installed.[/red]")
            console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Sync failed: {e}[/red]")
            raise typer.Exit(1)

    console.print()
    console.print("[dim]To view in Obsidian:[/dim]")
    console.print(f"[dim]1. Open Obsidian[/dim]")
    console.print(f"[dim]2. Open folder as vault: {output.absolute()}[/dim]")
    console.print(f"[dim]3. Enable Graph View (Cmd+G) to see connections[/dim]")


def _upload_wiki_to_drive(client, wiki_dir: Path, drive_path: str):
    """Upload wiki directory to Google Drive."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

    # Create the drive folder structure
    console.print(f"  Creating folder: {drive_path}")
    root_folder_id = client.find_or_create_folder(drive_path)

    # Collect all files to upload
    files_to_upload = []
    for item in wiki_dir.rglob("*"):
        if item.is_file() and not item.name.startswith("."):
            rel_path = item.relative_to(wiki_dir)
            files_to_upload.append((item, rel_path))

    console.print(f"  Uploading {len(files_to_upload)} files...")

    # Upload with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        transient=False,
    ) as progress:
        task = progress.add_task("Uploading", total=len(files_to_upload))

        for local_path, rel_path in files_to_upload:
            # Get or create parent folder
            parent_path = str(rel_path.parent)
            if parent_path == ".":
                parent_id = root_folder_id
            else:
                full_parent_path = f"{drive_path}/{parent_path}"
                parent_id = client.find_or_create_folder(full_parent_path)

            # Upload or update the file
            client.upload_or_update_file(local_path, parent_id)
            progress.update(task, advance=1)


@app.command()
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
        from qdrant_client import QdrantClient

        try:
            client = QdrantClient(url="http://localhost:6333", timeout=2)
            client.get_collections()
            checks.append(("Qdrant", "✓ connected", "green"))
        except Exception:
            checks.append(("Qdrant", "○ not running (Day 2)", "dim"))
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


# =============================================================================
# Google Drive Commands
# =============================================================================


def _browse_and_select_folders():
    """Interactive folder browser for selecting GDrive folders."""
    try:
        from vectrola.gdrive import DriveClient, add_allowed_folder, get_allowed_folders
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
            add_allowed_folder(folder_id, folder_path)

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


@gdrive_app.command("auth")
def gdrive_auth(
    logout: bool = typer.Option(False, "--logout", help="Remove stored credentials"),
    skip_select: bool = typer.Option(False, "--skip-select", help="Skip folder selection after auth"),
):
    """
    Authenticate with Google Drive and select folders.

    Opens your browser for Google sign-in. After authorization,
    prompts you to select which folders Vectrola can access.
    """
    try:
        from vectrola.gdrive import authenticate, logout as do_logout, is_authenticated
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

    if already_authed:
        console.print("[green]✓ Already authenticated with Google Drive[/green]")
    else:
        try:
            authenticate()
        except Exception as e:
            console.print(f"[red]Authentication failed: {e}[/red]")
            raise typer.Exit(1)

    # After successful auth, prompt for folder selection
    if not skip_select:
        console.print()
        console.print("[bold]Select folders to allow Vectrola access:[/bold]")
        console.print()

        # Try browser-based Google Picker first, fall back to CLI browser
        import os
        picker_client_id = os.getenv("GOOGLE_PICKER_CLIENT_ID", "")
        api_key = os.getenv("GOOGLE_API_KEY", "")

        if picker_client_id and api_key:
            # Use browser-based Google Picker UI
            try:
                from vectrola.gdrive.picker import open_folder_picker
                from vectrola.gdrive import add_allowed_folder, clear_allowed_folders

                folders, access_token = open_folder_picker(picker_client_id, api_key)

                if folders:
                    clear_allowed_folders()
                    for folder in folders:
                        add_allowed_folder(folder['id'], folder['name'])

                    console.print(f"\n[green]✓ Access granted to {len(folders)} folder(s):[/green]")
                    for folder in folders:
                        console.print(f"  📁 {folder['name']}")
                    console.print()
                    console.print("[dim]Now run: vectrola gdrive ingest <folder>[/dim]")
                else:
                    console.print("[yellow]No folders selected.[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Browser picker failed: {e}[/yellow]")
                console.print("[dim]Falling back to CLI folder browser...[/dim]")
                console.print()
                _browse_and_select_folders()
        else:
            # Fall back to CLI-based folder browser
            console.print("[dim]Tip: Set GOOGLE_PICKER_CLIENT_ID and GOOGLE_API_KEY in .env for browser-based folder picker[/dim]")
            console.print()
            _browse_and_select_folders()


@gdrive_app.command("setup")
def gdrive_setup(
    client_id: str = typer.Option(..., "--client-id", help="Your Google OAuth Client ID"),
    client_secret: str = typer.Option(..., "--client-secret", help="Your Google OAuth Client Secret"),
):
    """
    Configure custom Google OAuth credentials (BYOC).

    Power users can provide their own Google Cloud project credentials
    to avoid the unverified app warning and 100-user limit.

    See docs/gdrive.md for instructions on creating credentials.
    """
    try:
        from vectrola.gdrive import setup_custom_credentials
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    setup_custom_credentials(client_id, client_secret)
    console.print("[green]✓ Custom credentials saved[/green]")
    console.print("[dim]Run 'vectrola gdrive auth' to authenticate[/dim]")


@gdrive_app.command("list")
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
        from vectrola.gdrive import is_authenticated, DriveClient, is_path_allowed, get_allowed_folders
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[red]Not authenticated. Run 'vectrola gdrive auth' first.[/red]")
        raise typer.Exit(1)

    client = DriveClient()

    # Check if path is allowed
    allowed_folders = get_allowed_folders()
    if allowed_folders and not is_path_allowed(path, client.resolve_path):
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


@gdrive_app.command("ingest")
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

    client = DriveClient()

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
            console.print(f"[{i}/{total}] {file.name}", flush=True)

            try:
                # Download file
                console.print(f"   ↓ Downloading from Drive...", end="", flush=True)
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

                # Clean up this file immediately to save space
                local_path.unlink()

            except Exception as e:
                errors.append((file, str(e)))
                console.print(f"   ✗ Error: {e}")

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Summary
    console.print()
    console.print(f"✅ Processed: {len(results)} tracks from Google Drive")
    if errors:
        console.print(f"❌ Errors: {len(errors)} tracks")


@gdrive_app.command("status")
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


@gdrive_app.command("select")
def gdrive_select():
    """
    Open Google Picker to select which folders Vectrola can access.

    Opens a browser window with Google's folder picker. Select one or more
    folders containing your music. Vectrola will ONLY be able to access
    the folders you choose - this is enforced by Google, not just the app.
    """
    import os
    try:
        from vectrola.gdrive.picker import open_folder_picker
        from vectrola.gdrive import add_allowed_folder, clear_allowed_folders
    except ImportError as e:
        console.print(f"[red]Google Drive support not installed: {e}[/red]")
        console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
        raise typer.Exit(1)

    # Use Web App client ID for Picker (different from Desktop app for CLI auth)
    client_id = os.getenv("GOOGLE_PICKER_CLIENT_ID", "")
    api_key = os.getenv("GOOGLE_API_KEY", "")

    if not client_id:
        console.print("[red]GOOGLE_PICKER_CLIENT_ID not set in .env[/red]")
        console.print("[dim]Create a Web Application OAuth credential at:[/dim]")
        console.print("[dim]https://console.cloud.google.com/apis/credentials[/dim]")
        raise typer.Exit(1)

    if not api_key:
        console.print("[red]GOOGLE_API_KEY not set in .env[/red]")
        console.print("[dim]Create an API key at: https://console.cloud.google.com/apis/credentials[/dim]")
        raise typer.Exit(1)

    try:
        folders, access_token = open_folder_picker(client_id, api_key)

        if not folders:
            console.print("[yellow]No folders selected.[/yellow]")
            return

        # Clear existing and add new
        clear_allowed_folders()
        for folder in folders:
            add_allowed_folder(folder['id'], folder['name'])

        console.print(f"\n[green]✓ Access granted to {len(folders)} folder(s):[/green]")
        for folder in folders:
            console.print(f"  📁 {folder['name']}")

        console.print("\n[dim]Vectrola can only access these folders and their contents.[/dim]")

    except RuntimeError as e:
        console.print(f"[red]Folder selection failed: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@gdrive_app.command("allow")
def gdrive_allow(
    path: str = typer.Argument(..., help="Drive folder path to allow (e.g., /songs)"),
):
    """
    Allow access to a specific Google Drive folder.

    By default, Vectrola can access your entire Drive. Use this command
    to restrict access to only specific folders.

    Examples:
        vectrola gdrive allow /songs
        vectrola gdrive allow "/Music/Bollywood"
    """
    try:
        from vectrola.gdrive import is_authenticated, DriveClient, add_allowed_folder
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        raise typer.Exit(1)

    if not is_authenticated():
        console.print("[red]Not authenticated. Run 'vectrola gdrive auth' first.[/red]")
        raise typer.Exit(1)

    client = DriveClient()

    # Resolve path to folder ID
    folder_id = client.resolve_path(path)
    if folder_id is None:
        console.print(f"[red]Folder not found: {path}[/red]")
        raise typer.Exit(1)

    # Add to allowed list
    add_allowed_folder(folder_id, path)
    console.print(f"[green]✓ Allowed access to: {path}[/green]")
    console.print("[dim]Vectrola will only access this folder and its subfolders.[/dim]")


@gdrive_app.command("allowed")
def gdrive_allowed():
    """
    Show folders that Vectrola is allowed to access.
    """
    try:
        from vectrola.gdrive import get_allowed_folders
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        raise typer.Exit(1)

    folders = get_allowed_folders()

    if not folders:
        console.print("[yellow]No folder restrictions set.[/yellow]")
        console.print("[dim]Vectrola can access your entire Google Drive.[/dim]")
        console.print("[dim]Use 'vectrola gdrive allow <path>' to restrict access.[/dim]")
        return

    console.print("[bold]Allowed folders:[/bold]")
    for folder_id, folder_path in folders.items():
        console.print(f"  📁 {folder_path}")

    console.print(f"\n[dim]{len(folders)} folder(s) allowed[/dim]")


@gdrive_app.command("disallow")
def gdrive_disallow(
    path: str = typer.Argument(None, help="Folder path to remove (or --all to clear all)"),
    all_folders: bool = typer.Option(False, "--all", help="Remove all folder restrictions"),
):
    """
    Remove a folder from the allowed list.

    Examples:
        vectrola gdrive disallow /songs      # Remove specific folder
        vectrola gdrive disallow --all       # Clear all restrictions
    """
    try:
        from vectrola.gdrive import (
            is_authenticated, DriveClient, get_allowed_folders,
            remove_allowed_folder, clear_allowed_folders
        )
    except ImportError:
        console.print("[red]Google Drive support not installed.[/red]")
        raise typer.Exit(1)

    if all_folders:
        count = clear_allowed_folders()
        console.print(f"[green]✓ Removed all folder restrictions ({count} folders)[/green]")
        console.print("[dim]Vectrola can now access your entire Google Drive.[/dim]")
        return

    if not path:
        console.print("[red]Specify a folder path or use --all to clear all restrictions.[/red]")
        raise typer.Exit(1)

    # Find folder ID by path
    folders = get_allowed_folders()
    normalized_path = "/" + path.strip("/")

    folder_id = None
    for fid, fpath in folders.items():
        if "/" + fpath.strip("/") == normalized_path:
            folder_id = fid
            break

    if folder_id is None:
        console.print(f"[red]Folder not in allowed list: {path}[/red]")
        console.print("[dim]Use 'vectrola gdrive allowed' to see allowed folders.[/dim]")
        raise typer.Exit(1)

    remove_allowed_folder(folder_id)
    console.print(f"[green]✓ Removed: {path}[/green]")


# =============================================================================
# Library Commands (Day 7)
# =============================================================================


@library_app.command("list")
def library_list(
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum tracks to show"),
):
    """
    List all tracks in your library.

    Shows track IDs, titles, and their playback sources (GDrive/local).
    """
    try:
        from vectrola.services.library import UserLibrary
    except ImportError:
        console.print("[red]Library service not available.[/red]")
        raise typer.Exit(1)

    library = UserLibrary()
    tracks = library.get_tracks()

    if not tracks:
        console.print("[yellow]Your library is empty.[/yellow]")
        console.print("[dim]Run 'vectrola ingest' or 'vectrola gdrive ingest' to add tracks.[/dim]")
        return

    table = Table(title=f"📚 Your Library ({len(tracks)} tracks)")
    table.add_column("Track ID", style="cyan", max_width=30)
    table.add_column("Source", justify="center")
    table.add_column("Added", justify="right")

    count = 0
    for track_id, info in tracks.items():
        if count >= limit:
            break

        # Determine source
        has_gdrive = bool(info.get("gdrive_file_id"))
        has_local = bool(info.get("local_path"))

        if has_gdrive and has_local:
            source = "☁️ + 💾"
        elif has_gdrive:
            source = "☁️ GDrive"
        elif has_local:
            source = "💾 Local"
        else:
            source = "❌ None"

        added = info.get("added_at", "")[:10]  # Just the date part

        table.add_row(track_id, source, added)
        count += 1

    console.print(table)

    if len(tracks) > limit:
        console.print(f"[dim]Showing {limit} of {len(tracks)} tracks. Use --limit to see more.[/dim]")


@library_app.command("stats")
def library_stats():
    """
    Show library statistics.

    Displays counts of tracks by source (GDrive, local, both).
    """
    try:
        from vectrola.services.library import UserLibrary
        from vectrola.config import get_current_user
    except ImportError:
        console.print("[red]Library service not available.[/red]")
        raise typer.Exit(1)

    library = UserLibrary()
    stats = library.stats()
    user_id, is_logged_in = get_current_user()

    console.print("[bold]📊 Library Statistics[/bold]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    status = f"{user_id} (logged in)" if is_logged_in else f"{user_id} (anonymous)"
    table.add_row("User", status)
    table.add_row("Total Tracks", str(stats["total"]))
    table.add_row("☁️ GDrive only", str(stats["gdrive_only"]))
    table.add_row("💾 Local only", str(stats["local_only"]))
    table.add_row("☁️ + 💾 Both", str(stats["both"]))

    console.print(table)


@library_app.command("add")
def library_add(
    track_id: str = typer.Argument(..., help="Track ID to add (e.g., spotify:xxx or hash:xxx)"),
    gdrive_id: Optional[str] = typer.Option(None, "--gdrive", "-g", help="Google Drive file ID"),
    local_path: Optional[str] = typer.Option(None, "--local", "-l", help="Local file path"),
):
    """
    Add a track to your library manually.

    Requires either a GDrive file ID or local path for playback.
    """
    try:
        from vectrola.services.library import UserLibrary
    except ImportError:
        console.print("[red]Library service not available.[/red]")
        raise typer.Exit(1)

    if not gdrive_id and not local_path:
        console.print("[red]Specify at least one source: --gdrive or --local[/red]")
        raise typer.Exit(1)

    library = UserLibrary()
    library.add_track(track_id, gdrive_file_id=gdrive_id, local_path=local_path)

    console.print(f"[green]✓ Added {track_id} to your library[/green]")


@library_app.command("remove")
def library_remove(
    track_id: str = typer.Argument(..., help="Track ID to remove"),
):
    """
    Remove a track from your library.

    Note: This only removes it from your library, not from the global catalog.
    """
    try:
        from vectrola.services.library import UserLibrary
    except ImportError:
        console.print("[red]Library service not available.[/red]")
        raise typer.Exit(1)

    library = UserLibrary()

    if library.remove_track(track_id):
        console.print(f"[green]✓ Removed {track_id} from your library[/green]")
    else:
        console.print(f"[red]Track not found in your library: {track_id}[/red]")
        raise typer.Exit(1)


@library_app.command("clear")
def library_clear(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """
    Clear all tracks from your library.

    Warning: This removes all tracks from your library but not from the global catalog.
    """
    try:
        from vectrola.services.library import UserLibrary
    except ImportError:
        console.print("[red]Library service not available.[/red]")
        raise typer.Exit(1)

    library = UserLibrary()
    count = library.count()

    if count == 0:
        console.print("[yellow]Your library is already empty.[/yellow]")
        return

    if not confirm:
        console.print(f"[yellow]This will remove {count} tracks from your library.[/yellow]")
        if not typer.confirm("Are you sure?"):
            console.print("[dim]Cancelled[/dim]")
            return

    removed = library.clear()
    console.print(f"[green]✓ Cleared {removed} tracks from your library[/green]")


# =============================================================================
# Authentication Commands
# =============================================================================


@app.command()
def login():
    """
    Login to sync your library across devices.

    Your email/username is used as your user ID to sync your library
    across multiple devices. Without login, you're in anonymous mode
    which only works on a single device.
    """
    import json
    from datetime import datetime

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

    # Check if wiki exists with different owner - auto-regenerate
    wiki_owner_file = Path("./wiki/.wiki_owner")
    if wiki_owner_file.exists():
        old_owner = wiki_owner_file.read_text().strip()
        if old_owner != email:
            console.print()
            console.print(f"[yellow]Wiki was generated for '{old_owner}'. Regenerating for you...[/yellow]")
            console.print()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("Generating wiki...", total=None)
                from vectrola.storage.wiki import WikiGenerator
                WikiGenerator().generate_all()


@app.command()
def logout(
    purge_wiki: bool = typer.Option(False, "--purge-wiki", help="Delete the wiki folder for privacy"),
):
    """
    Logout and switch to anonymous mode.

    After logout, you'll use a device-local anonymous user ID.
    Your library data remains on the server but won't be accessible
    until you login again with the same email/username.

    Use --purge-wiki to delete the wiki folder (for privacy when switching users).
    """
    import json

    session_path = Path.home() / ".config" / "vectrola" / "session.json"

    old_user = None
    if session_path.exists():
        try:
            session = json.loads(session_path.read_text())
            old_user = session.get("user_id")
        except (json.JSONDecodeError, KeyError):
            pass
        session_path.unlink()
        console.print("[green]✅ Logged out. Switched to anonymous mode.[/green]")

        # Handle wiki based on --purge-wiki flag
        wiki_dir = Path("./wiki")
        wiki_owner_file = wiki_dir / ".wiki_owner"

        if purge_wiki and wiki_dir.exists():
            shutil.rmtree(wiki_dir)
            console.print("[green]🗑️  Wiki deleted.[/green]")
        elif wiki_owner_file.exists() and old_user:
            owner = wiki_owner_file.read_text().strip()
            if owner == old_user:
                console.print()
                console.print(f"[yellow]Wiki was generated for '{old_user}'. Regenerating for anonymous user...[/yellow]")
                console.print()

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                    transient=True,
                ) as progress:
                    progress.add_task("Generating wiki...", total=None)
                    from vectrola.storage.wiki import WikiGenerator
                    WikiGenerator().generate_all()
    else:
        console.print("[yellow]Not logged in.[/yellow]")


@app.command()
def whoami():
    """
    Show current user status.

    Displays whether you're logged in or using anonymous mode,
    and your current user ID.
    """
    from vectrola.config import get_current_user

    user_id, is_logged_in = get_current_user()

    if is_logged_in:
        console.print(f"[bold green]Logged in as:[/bold green] {user_id}")
    else:
        console.print(f"[bold yellow]Anonymous user:[/bold yellow] {user_id}")
        console.print("[dim](Single device only. Run 'vectrola login' to sync across devices.)[/dim]")


@app.command("migrate-user")
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
    from vectrola.config import get_current_user
    from vectrola.storage.qdrant import get_db
    from pathlib import Path
    import json

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

    # Find all tracks with from_user in user_ids
    try:
        from qdrant_client import models

        results, _ = db.client.scroll(
            collection_name=db.COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_ids",
                        match=models.MatchAny(any=[from_user]),
                    )
                ]
            ),
            limit=1000,
            with_payload=True,
        )
    except Exception as e:
        console.print(f"[red]Error querying Qdrant: {e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print(f"[yellow]No tracks found for user '{from_user}'.[/yellow]")
        raise typer.Exit(0)

    console.print(f"Found [bold]{len(results)}[/bold] tracks to migrate.")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made. Remove --dry-run to apply.[/dim]")
        console.print("\nTracks that would be migrated:")
        for point in results[:10]:
            title = point.payload.get("title", "Unknown")
            artists = ", ".join(point.payload.get("artists", [])[:2])
            console.print(f"  • {title} - {artists}")
        if len(results) > 10:
            console.print(f"  ... and {len(results) - 10} more")
        raise typer.Exit(0)

    # Confirm migration
    if not typer.confirm(f"\nMigrate {len(results)} tracks from '{from_user}' to '{to_user}'?"):
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
        task = progress.add_task("Migrating tracks...", total=len(results))

        for point in results:
            user_ids = point.payload.get("user_ids", [])

            # Replace from_user with to_user
            if from_user in user_ids:
                user_ids.remove(from_user)
            if to_user not in user_ids:
                user_ids.append(to_user)

            # Update in Qdrant
            try:
                db.client.set_payload(
                    collection_name=db.COLLECTION,
                    payload={"user_ids": user_ids},
                    points=[point.id],
                )
                migrated += 1
            except Exception as e:
                console.print(f"[red]Error updating track: {e}[/red]")

            progress.advance(task)

    console.print(f"\n[green]✅ Migrated {migrated}/{len(results)} tracks successfully![/green]")

    # Optionally clean up anon_id file
    if from_user.startswith("anon_") and anon_path.exists():
        if typer.confirm("\nRemove anonymous ID file? (You're now using the logged-in account)"):
            anon_path.unlink()
            console.print("[dim]Removed ~/.config/vectrola/anon_id[/dim]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  • Run 'vectrola library list' to see your migrated tracks")
    console.print("  • Run 'vectrola wiki' to regenerate your wiki")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
