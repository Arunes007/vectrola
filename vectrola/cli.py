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
    from vectrola.services.failed_ingests import FailedIngestsManager, detect_error_stage

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
    fm = FailedIngestsManager()

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

            # Remove from failed list if it was there (successful re-ingest)
            fm.remove_failed(f"local:{file}")

        except Exception as e:
            errors.append((file, str(e)))
            print(f"   ✗ Error: {e}")

    # Save failures for retry
    if errors:
        for file_path, error_msg in errors:
            fm.add_failed(
                name=file_path.name,
                source="local",
                source_path=str(file_path),
                error=error_msg,
                error_stage=detect_error_stage(error_msg),
            )

    # Summary
    print()
    print(f"✅ Processed: {len(results)} tracks")
    if errors:
        print(f"❌ Errors: {len(errors)} tracks")
        console.print("[yellow]Failed tracks saved. Run 'vectrola retry' to retry.[/yellow]")

    # Next steps
    if results:
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print("  • Search your library:   [cyan]vectrola search \"romantic mood\"[/cyan]")
        console.print("  • Generate Obsidian wiki: [cyan]vectrola wiki[/cyan]")
        console.print("  • Sync wiki to Drive:    [cyan]vectrola wiki --sync[/cyan]")
        console.print("  • View library stats:    [cyan]vectrola library stats[/cyan]")


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

    # Suggest sync if not already synced
    if not sync:
        console.print()
        console.print("[bold]Next step:[/bold]")
        console.print("  • Sync wiki to Drive: [cyan]vectrola wiki --sync[/cyan]")


def _upload_wiki_to_drive(client, wiki_dir: Path, drive_path: str):
    """Upload wiki directory to Google Drive with smart caching and parallel uploads."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from .gdrive.sync_cache import (
        load_sync_cache,
        save_sync_cache,
        file_needs_upload,
        update_cached_file,
        get_files_to_delete,
        remove_cached_file,
    )
    from multiprocessing import Pool
    import time

    # Load sync cache
    cache = load_sync_cache()

    # Create the drive folder structure
    console.print(f"  Creating folder: {drive_path}")
    root_folder_id = client.find_or_create_folder(drive_path)

    # Collect all files and check which need uploading
    all_files = []
    files_to_upload = []
    skipped_count = 0

    for item in wiki_dir.rglob("*"):
        if item.is_file() and not item.name.startswith("."):
            rel_path = str(item.relative_to(wiki_dir))
            all_files.append((item, rel_path))

            # Check if file needs upload (hash comparison)
            needs_upload, local_hash = file_needs_upload(cache, item, rel_path)
            if needs_upload:
                files_to_upload.append((item, rel_path, local_hash))
            else:
                skipped_count += 1

    # Report what we're doing
    total_files = len(all_files)
    upload_count = len(files_to_upload)

    if skipped_count > 0:
        console.print(f"  [dim]Skipping {skipped_count} unchanged files[/dim]")

    if upload_count == 0:
        console.print(f"  [green]✓ All {total_files} files up to date![/green]")
        return

    console.print(f"  Uploading {upload_count} changed files...")

    # Pre-create all folders first (sequential - folder creation is fast and needs ordering)
    folder_cache = {".": root_folder_id}
    folders_needed = set()
    for _, rel_path, _ in files_to_upload:
        parent_path = str(Path(rel_path).parent)
        if parent_path != ".":
            parts = parent_path.split("/")
            for i in range(len(parts)):
                folders_needed.add("/".join(parts[: i + 1]))

    # Create folders in order (parents before children)
    for folder_path in sorted(folders_needed, key=lambda x: x.count("/")):
        if folder_path not in folder_cache:
            full_path = f"{drive_path}/{folder_path}"
            folder_cache[folder_path] = client.find_or_create_folder(full_path)

    # Prepare upload tasks: (local_path_str, rel_path, local_hash, parent_id)
    upload_tasks = []
    for local_path, rel_path, local_hash in files_to_upload:
        parent_path = str(Path(rel_path).parent)
        parent_id = folder_cache.get(parent_path, root_folder_id)
        upload_tasks.append((str(local_path), rel_path, local_hash, parent_id))

    # Number of parallel workers (balance speed vs rate limits)
    # 5-6 workers is the sweet spot for Google Drive API
    NUM_WORKERS = min(5, upload_count)

    failed_files = []
    completed = 0

    # Use process pool for true parallelism (avoids Google API client thread-safety issues)
    from .gdrive.parallel_upload import init_worker, upload_single_file

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        transient=False,
    ) as progress:
        task = progress.add_task("Uploading", total=upload_count)

        # Process pool with initializer (each process gets its own Drive client)
        with Pool(processes=NUM_WORKERS, initializer=init_worker) as pool:
            # Use imap_unordered for better progress tracking
            for result in pool.imap_unordered(upload_single_file, upload_tasks):
                success, rel_path, local_hash, result_data = result

                if success:
                    # Update cache with drive file ID
                    update_cached_file(cache, rel_path, local_hash, result_data)
                else:
                    failed_files.append((rel_path, result_data))

                completed += 1
                progress.update(task, advance=1)

    # Handle deleted files (files in cache but not in current wiki)
    current_rel_paths = {rel_path for _, rel_path in all_files}
    deleted_files = get_files_to_delete(cache, current_rel_paths)
    if deleted_files:
        console.print(f"  [dim]Cleaning up {len(deleted_files)} deleted files from cache[/dim]")
        for rel_path in deleted_files:
            remove_cached_file(cache, rel_path)

    # Save updated cache
    save_sync_cache(cache)

    # Report results
    if failed_files:
        console.print(f"\n[yellow]⚠ {len(failed_files)} file(s) failed to upload:[/yellow]")
        for rel_path, error in failed_files[:5]:
            console.print(f"  [dim]• {rel_path}: {error}[/dim]")
        if len(failed_files) > 5:
            console.print(f"  [dim]... and {len(failed_files) - 5} more[/dim]")
    else:
        console.print(f"  [green]✓ All {upload_count} files uploaded successfully![/green]")


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


# =============================================================================
# Setup Wizard
# =============================================================================


@app.command()
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
    console.print("[bold]Step 1/4: Storage Backend[/bold]")
    console.print("─" * 25)
    console.print()
    console.print("  [1] Local (fastest, single device)")
    console.print("      [dim]Requires: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")
    console.print()
    console.print("  [2] Remote (sync across devices)")
    console.print("      [dim]Supports: Railway, Qdrant Cloud, self-hosted[/dim]")
    console.print()

    current = "2" if config.storage_mode == "remote" else "1"
    choice = typer.prompt("Choice", default=current)

    if choice == "2":
        config.storage_mode = "remote"
        default_url = config.qdrant_url if config.qdrant_url != "http://localhost:6333" else ""
        config.qdrant_url = typer.prompt("Qdrant URL", default=default_url)
        api_key = typer.prompt("API Key (optional, press Enter to skip)", default="")
        config.qdrant_api_key = api_key if api_key else None

        # Test connection
        console.print()
        with console.status("Testing connection..."):
            from vectrola.storage.qdrant import VectrolaDB
            try:
                db = VectrolaDB(url=config.qdrant_url, api_key=config.qdrant_api_key)
                if db.is_connected():
                    console.print("[green]✓ Connected[/green]")
                else:
                    raise Exception("Connection failed")
            except Exception as e:
                console.print(f"[red]✗ Connection failed: {e}[/red]")
                if not typer.confirm("Continue anyway?", default=False):
                    raise typer.Abort()
    else:
        config.storage_mode = "local"
        config.qdrant_url = "http://localhost:6333"
        config.qdrant_api_key = None

        # Check if local Qdrant is running
        console.print()
        with console.status("Checking local Qdrant..."):
            from vectrola.storage.qdrant import VectrolaDB
            try:
                db = VectrolaDB(url=config.qdrant_url)
                if db.is_connected():
                    console.print("[green]✓ Local Qdrant running[/green]")
                else:
                    raise Exception()
            except:
                console.print("[yellow]⚠ Local Qdrant not running[/yellow]")
                console.print("[dim]Start with: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")

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
        console.print("  • View library stats:    [cyan]vectrola library stats[/cyan]")


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


@gdrive_app.command("revoke")
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

    # Check if setup has been run
    from vectrola.config import CONFIG_PATH
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
            from vectrola.storage.wiki import WikiGenerator
            WikiGenerator().generate_all()


@app.command()
def logout(
    no_purge: bool = typer.Option(False, "--no-purge", help="Keep wiki and Google Drive connected"),
):
    """
    Logout and switch to anonymous mode.

    By default, deletes the wiki and revokes Google Drive access for privacy.
    Use --no-purge to keep them (e.g., if you plan to login again soon).
    """
    import json

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


@app.command()
def retry(
    list_failed: bool = typer.Option(False, "--list", "-l", help="List failed tracks"),
    clear: bool = typer.Option(False, "--clear", help="Clear all failed tracks"),
):
    """
    Retry failed ingestions.

    Tracks that failed during previous ingestion are saved and can be retried.
    Use --list to see failed tracks, --clear to remove them.
    """
    from vectrola.services.failed_ingests import FailedIngestsManager, detect_error_stage

    fm = FailedIngestsManager()

    # List mode
    if list_failed:
        failed = fm.get_failed()
        if not failed:
            console.print("[green]No failed tracks.[/green]")
            return

        console.print(f"[bold]Failed tracks ({len(failed)}):[/bold]\n")
        for i, f in enumerate(failed, 1):
            console.print(f"  {i}. {f['name']} ({f['source']})")
            console.print(f"     [red]Error:[/red] {f['error']}")
            console.print(f"     [dim]Stage: {f['error_stage']} | Attempts: {f['attempts']} | {f['failed_at']}[/dim]")
            console.print()
        return

    # Clear mode
    if clear:
        count = fm.clear()
        console.print(f"[green]Cleared {count} failed track(s).[/green]")
        return

    # Retry mode
    failed = fm.get_failed()
    if not failed:
        console.print("[green]No failed tracks to retry.[/green]")
        return

    console.print(f"[bold]🔄 Retrying {len(failed)} failed track(s)...[/bold]\n")

    from vectrola.ingest.pipeline import IngestPipeline
    pipeline = IngestPipeline()

    recovered = 0
    still_failing = []

    for i, f in enumerate(failed, 1):
        console.print(f"[{i}/{len(failed)}] {f['name']}")

        try:
            if f["source"] == "gdrive":
                # Re-download from GDrive and process
                from vectrola.gdrive import DriveClient
                from dataclasses import dataclass

                client = DriveClient()

                with tempfile.TemporaryDirectory() as temp_dir:
                    # Create DriveFile-like object for download
                    @dataclass
                    class DriveFileRetry:
                        id: str
                        name: str
                        parent_path: str
                        mime_type: str = "audio/mpeg"

                    drive_file = DriveFileRetry(
                        id=f["gdrive_file_id"],
                        name=f["name"],
                        parent_path=f["source_path"].rsplit("/", 1)[0] if "/" in f["source_path"] else "",
                    )

                    console.print("   ↓ Downloading from Drive...", end="")
                    local_path = client.download_file(drive_file, Path(temp_dir))
                    console.print(" done")

                    result = pipeline.process_track(
                        local_path,
                        write_file_tags=False,
                        gdrive_file_id=f["gdrive_file_id"],
                        gdrive_path=f["source_path"],
                    )

                    moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
                    console.print(f"   [green]✓ Done: {moods_str}[/green]")

            else:
                # Local file - just re-process
                local_path = Path(f["source_path"])
                if not local_path.exists():
                    raise FileNotFoundError(f"File not found: {local_path}")

                result = pipeline.process_track(local_path, write_file_tags=True)
                moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
                console.print(f"   [green]✓ Done: {moods_str}[/green]")

            # Success - remove from failed list
            fm.remove_failed(f["id"])
            recovered += 1

        except Exception as e:
            console.print(f"   [red]✗ Error: {e}[/red]")
            # Update the failed entry with new error and increment attempts
            fm.add_failed(
                name=f["name"],
                source=f["source"],
                source_path=f["source_path"],
                error=str(e),
                error_stage=detect_error_stage(str(e)),
                gdrive_file_id=f.get("gdrive_file_id"),
            )
            still_failing.append(f)

    # Summary
    console.print()
    if recovered:
        console.print(f"[green]✅ Recovered: {recovered} track(s)[/green]")
    if still_failing:
        console.print(f"[red]❌ Still failing: {len(still_failing)} track(s)[/red]")
        console.print("[dim]Run 'vectrola retry --list' to see details.[/dim]")


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
