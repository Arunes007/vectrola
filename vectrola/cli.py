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

from vectrola.messages import load_messages

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


app = typer.Typer(
    name="vectrola",
    help="🎧 Vectrola: Multimodal Music Knowledge Graph\n\nSemantic music search using audio embeddings and LLM synthesis.",
    add_completion=False,
    invoke_without_command=True,
    callback=show_welcome,
)

# Google Drive subcommand group
gdrive_app = typer.Typer(
    name="gdrive",
    help="🌐 Google Drive integration for cloud music ingestion.",
)
app.add_typer(gdrive_app, name="gdrive")


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r/-R", help="Scan subdirectories"),
    fast: bool = typer.Option(True, "--fast/--slow", "-f/-s", help="Skip Demucs stem separation (faster)"),
    write_tags: bool = typer.Option(True, "--tags/--no-tags", help="Write analysis to file tags"),
    force: bool = typer.Option(False, "--force", "-F", help="Skip dedup check and re-analyze existing tracks"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed progress for each track"),
):
    """
    Ingest audio files into the knowledge graph.

    Transcribes lyrics and extracts semantic metadata (themes, moods, narrative).

    By default shows a progress bar. Use --verbose to see detailed per-track output.
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
    if force:
        print("   Force mode: re-analyzing all tracks (ignoring dedup)")
    print()

    pipeline = IngestPipeline(use_stems=not fast)
    fm = FailedIngestsManager()

    # Process files with conditional output
    results = []
    errors = []
    stats = {"new": 0, "existing": 0, "errors": 0}

    if verbose:
        # VERBOSE MODE: Show detailed per-track output (original behavior)
        for i, file in enumerate(files, 1):
            print(f"[{i}/{total}] {file.name}", flush=True)
            try:
                result = pipeline.process_track(
                    file,
                    write_file_tags=write_tags,
                    verbose=True,
                    force=force
                )
                results.append(result)

                # Track stats
                if hasattr(result, '_was_deduplicated') and result._was_deduplicated:
                    stats["existing"] += 1
                else:
                    stats["new"] += 1

                moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
                print(f"   ✓ Done: {moods_str}")

                # Remove from failed list if it was there (successful re-ingest)
                fm.remove_failed(f"local:{file}")

            except Exception as e:
                errors.append((file, str(e)))
                stats["errors"] += 1
                print(f"   ✗ Error: {e}")

    else:
        # DEFAULT MODE: Show progress bar only (like refresh command)
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("Ingesting tracks", total=total)

            for file in files:
                try:
                    result = pipeline.process_track(
                        file,
                        write_file_tags=write_tags,
                        verbose=False,
                        force=force
                    )
                    results.append(result)

                    # Track stats
                    if hasattr(result, '_was_deduplicated') and result._was_deduplicated:
                        stats["existing"] += 1
                    else:
                        stats["new"] += 1

                    # Remove from failed list if it was there (successful re-ingest)
                    fm.remove_failed(f"local:{file}")

                except Exception as e:
                    errors.append((file, str(e)))
                    stats["errors"] += 1
                    # Show errors even in non-verbose mode
                    progress.console.print(f"[red]✗ {file.name}: {str(e)}[/red]")

                progress.advance(task)

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
    if stats["errors"] == 0:
        print(f"✅ Ingested {len(results)} tracks")
    else:
        print(f"✅ Processed: {len(results)}/{total} tracks")

    if stats["existing"] > 0:
        print(f"   • {stats['existing']} existing (skipped analysis)")
    if stats["new"] > 0:
        print(f"   • {stats['new']} new (full pipeline)")
    if stats["errors"] > 0:
        print(f"   ❌ {stats['errors']} errors")
        console.print("[yellow]To retry failed tracks, just run the same ingest command again.[/yellow]")
        console.print("[dim]Successfully processed tracks will be skipped (dedup).[/dim]")

    # Next steps
    if results:
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print("  • Search your library:   [cyan]vectrola search \"romantic mood\"[/cyan]")
        console.print("  • Generate Obsidian wiki: [cyan]vectrola wiki[/cyan]")
        console.print("  • Sync wiki to Drive:    [cyan]vectrola wiki --sync[/cyan]")



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
    from vectrola.config import get_config

    # Check Qdrant is running
    try:
        from vectrola.storage.qdrant import get_db
        db = get_db()
        count = db.count()
    except Exception as e:
        show_qdrant_error(get_config())
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
    sync: bool = typer.Option(False, "--sync", "-s", help="Upload wiki AND audio to Google Drive after generation"),
    drive_path: str = typer.Option("/Vectrola", "--drive-path", help="Google Drive root folder path"),
):
    """
    Generate Obsidian wiki from indexed tracks.

    Creates markdown pages with wikilinks for tracks, artists, moods, themes, and movies.
    Open the generated directory in Obsidian to explore the music knowledge graph.

    Use --sync to upload BOTH wiki and audio files to Google Drive for cross-device access.
    This enables streaming playback from Drive on any device.
    """
    from vectrola.storage.wiki import WikiGenerator
    from vectrola.config import get_config

    # Check if there are indexed tracks
    try:
        from vectrola.storage.qdrant import get_db
        db = get_db()
        count = db.count()
    except Exception as e:
        show_qdrant_error(get_config())
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
        console.print("[bold cyan]☁️  Syncing to Google Drive...[/bold cyan]")

        try:
            from vectrola.gdrive import is_authenticated
            from vectrola.gdrive.client import DriveClient

            if not is_authenticated():
                console.print("[red]Not authenticated with Google Drive.[/red]")
                console.print("[dim]Run 'vectrola gdrive auth' first.[/dim]")
                raise typer.Exit(1)

            client = DriveClient()
            _sync_to_drive(client, output, drive_path, db)

            console.print()
            console.print(f"[green]✅ Sync complete! Your music is now accessible from any device.[/green]")

        except ImportError:
            console.print("[red]Google Drive support not installed.[/red]")
            console.print("[dim]Install with: pip install vectrola[gdrive][/dim]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Sync failed: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
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
        console.print("  • Sync wiki + audio to Drive: [cyan]vectrola wiki --sync[/cyan]")


def _sync_to_drive(client, wiki_dir: Path, drive_root: str, db):
    """Sync both wiki and audio files to Google Drive."""
    from vectrola.config import load_config

    config = load_config()

    # Ensure folder IDs are cached
    if not config.gdrive_wiki_folder_id or not config.gdrive_audio_folder_id:
        console.print("  [yellow]Creating Vectrola folders...[/yellow]")
        audio_id, wiki_id = client.ensure_vectrola_folders()

        # Update config
        import json
        from vectrola.config import CONFIG_PATH

        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            config_data = json.loads(CONFIG_PATH.read_text())
        else:
            config_data = {}

        if "gdrive" not in config_data:
            config_data["gdrive"] = {}

        config_data["gdrive"]["audio_folder_id"] = audio_id
        config_data["gdrive"]["wiki_folder_id"] = wiki_id

        CONFIG_PATH.write_text(json.dumps(config_data, indent=2))

        config.gdrive_audio_folder_id = audio_id
        config.gdrive_wiki_folder_id = wiki_id

    # Phase 1: Sync Wiki
    console.rule("[bold cyan]Syncing Wiki")
    _upload_wiki_files(client, wiki_dir, f"{drive_root}/wiki", config.gdrive_wiki_folder_id)

    # Phase 2: Sync Audio
    console.rule("[bold cyan]Syncing Audio Files")
    _upload_audio_files(client, db, f"{drive_root}/audio", config.gdrive_audio_folder_id)


def _upload_wiki_files(client, wiki_dir: Path, drive_path: str, wiki_folder_id: str):
    """Upload wiki directory to Google Drive with smart caching."""
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

    # Load sync cache
    cache = load_sync_cache()

    # Collect all files and check which need uploading
    all_files = []
    files_to_upload = []
    skipped_count = 0

    for item in wiki_dir.rglob("*"):
        if item.is_file() and not item.name.startswith("."):
            rel_path = str(item.relative_to(wiki_dir))
            all_files.append((item, rel_path))

            # Check if file needs upload (hash comparison)
            needs_upload, local_hash = file_needs_upload(cache, item, rel_path, "wiki_files")
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
        console.print(f"  [green]✓ All {total_files} wiki files up to date![/green]")
        return

    console.print(f"  Uploading {upload_count} changed files...")

    # Pre-create all folders first
    folder_cache = {".": wiki_folder_id}
    folders_needed = set()
    for _, rel_path, _ in files_to_upload:
        parent_path = str(Path(rel_path).parent)
        if parent_path != ".":
            parts = parent_path.split("/")
            for i in range(len(parts)):
                folders_needed.add("/".join(parts[: i + 1]))

    # Create folders in order
    for folder_path in sorted(folders_needed, key=lambda x: x.count("/")):
        if folder_path not in folder_cache:
            full_path = f"{drive_path}/{folder_path}"
            folder_cache[folder_path] = client.find_or_create_folder(full_path)

    # Prepare upload tasks
    upload_tasks = []
    for local_path, rel_path, local_hash in files_to_upload:
        parent_path = str(Path(rel_path).parent)
        parent_id = folder_cache.get(parent_path, wiki_folder_id)
        upload_tasks.append((str(local_path), rel_path, local_hash, parent_id))

    NUM_WORKERS = min(5, upload_count)
    failed_files = []

    from .gdrive.parallel_upload import init_worker, upload_single_file

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        transient=False,
    ) as progress:
        task = progress.add_task("Uploading wiki", total=upload_count)

        with Pool(processes=NUM_WORKERS, initializer=init_worker) as pool:
            for result in pool.imap_unordered(upload_single_file, upload_tasks):
                success, rel_path, local_hash, result_data = result

                if success:
                    update_cached_file(cache, rel_path, local_hash, result_data, "wiki_files")
                else:
                    failed_files.append((rel_path, result_data))

                progress.update(task, advance=1)

    # Handle deleted files
    current_rel_paths = {rel_path for _, rel_path in all_files}
    deleted_files = get_files_to_delete(cache, current_rel_paths, "wiki_files")
    if deleted_files:
        console.print(f"  [dim]Cleaning up {len(deleted_files)} deleted files[/dim]")
        for rel_path in deleted_files:
            remove_cached_file(cache, rel_path, "wiki_files")

    # Save updated cache
    save_sync_cache(cache)

    if failed_files:
        console.print(f"\n[yellow]⚠ {len(failed_files)} file(s) failed:[/yellow]")
        for rel_path, error in failed_files[:5]:
            console.print(f"  [dim]{rel_path}: {error}[/dim]")
    else:
        console.print(f"  [green]✓ Uploaded {upload_count} wiki files[/green]")


def _upload_audio_files(client, db, drive_path: str, audio_folder_id: str):
    """Upload audio files from Qdrant metadata to Google Drive."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from .gdrive.sync_cache import load_sync_cache, save_sync_cache, compute_md5
    from multiprocessing import Pool
    from pathlib import Path

    # Load sync cache
    cache = load_sync_cache()

    # Get all tracks from Qdrant for current user
    console.print("  [dim]Querying indexed tracks...[/dim]")

    all_tracks = db.get_all_tracks()  # Returns list of track dicts with metadata

    if not all_tracks:
        console.print("  [yellow]No tracks found in database[/yellow]")
        return

    # Filter tracks with local file paths
    tracks_to_check = []
    for track in all_tracks:
        file_path = track.get("file_path")
        if file_path and Path(file_path).exists():
            tracks_to_check.append((Path(file_path), track))

    if not tracks_to_check:
        console.print("  [yellow]No local audio files found (files may have been moved)[/yellow]")
        return

    console.print(f"  [dim]Found {len(tracks_to_check)} tracks with local files[/dim]")

    # Check which files need upload
    files_to_upload = []
    skipped_count = 0

    for file_path, track in tracks_to_check:
        # Extract relative path to preserve folder structure
        # Use track title and artist for relative path if original structure unknown
        track_id = track.get("track_id", "")
        title = track.get("title", file_path.stem)
        artists = track.get("artists", [])
        artist_str = artists[0] if artists else "Unknown"

        # Create a clean relative path
        rel_path = f"{artist_str}/{title}{file_path.suffix}"

        # Compute current hash
        try:
            local_hash = compute_md5(file_path)
        except Exception as e:
            console.print(f"  [yellow]Warning: Cannot read {file_path.name}: {e}[/yellow]")
            continue

        # Check cache
        audio_cache = cache.get("audio_files", {})
        cached_entry = audio_cache.get(rel_path)

        if cached_entry and cached_entry.get("local_hash") == local_hash:
            # File unchanged
            skipped_count += 1
        else:
            files_to_upload.append((file_path, rel_path, local_hash, track_id))

    upload_count = len(files_to_upload)

    if skipped_count > 0:
        console.print(f"  [dim]Skipping {skipped_count} unchanged audio files[/dim]")

    if upload_count == 0:
        console.print(f"  [green]✓ All {len(tracks_to_check)} audio files up to date![/green]")
        return

    console.print(f"  Uploading {upload_count} audio files...")

    # Pre-create artist folders
    folder_cache = {".": audio_folder_id}
    folders_needed = set()
    for _, rel_path, _, _ in files_to_upload:
        parent_path = str(Path(rel_path).parent)
        if parent_path != ".":
            folders_needed.add(parent_path)

    for folder_path in sorted(folders_needed):
        if folder_path not in folder_cache:
            full_path = f"{drive_path}/{folder_path}"
            folder_cache[folder_path] = client.find_or_create_folder(full_path)

    # Prepare upload tasks
    upload_tasks = []
    for local_path, rel_path, local_hash, track_id in files_to_upload:
        parent_path = str(Path(rel_path).parent)
        parent_id = folder_cache.get(parent_path, audio_folder_id)
        # Include track_id in tuple for later Qdrant update
        upload_tasks.append((str(local_path), rel_path, local_hash, parent_id, track_id))

    NUM_WORKERS = min(3, upload_count)  # Fewer workers for large audio files
    failed_files = []
    uploaded_files = []

    from .gdrive.parallel_upload import init_worker, upload_single_file_with_id

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        transient=False,
    ) as progress:
        task = progress.add_task("Uploading audio", total=upload_count)

        with Pool(processes=NUM_WORKERS, initializer=init_worker) as pool:
            for result in pool.imap_unordered(upload_single_file_with_id, upload_tasks):
                success, rel_path, local_hash, result_data, track_id = result

                if success:
                    drive_file_id = result_data
                    uploaded_files.append((track_id, drive_file_id, rel_path))

                    # Update cache
                    if "audio_files" not in cache:
                        cache["audio_files"] = {}
                    cache["audio_files"][rel_path] = {
                        "local_hash": local_hash,
                        "gdrive_file_id": drive_file_id,
                        "last_synced": None  # Will be set by save_sync_cache
                    }
                else:
                    failed_files.append((rel_path, result_data))

                progress.update(task, advance=1)

    # Update Qdrant with gdrive_file_id for successful uploads
    if uploaded_files:
        console.print(f"  [dim]Updating database with Drive file IDs...[/dim]")
        for track_id, drive_file_id, rel_path in uploaded_files:
            try:
                db.update_track_metadata(track_id, {"gdrive_file_id": drive_file_id})
            except Exception as e:
                console.print(f"  [yellow]Warning: Failed to update {rel_path}: {e}[/yellow]")

    # Save updated cache
    save_sync_cache(cache)

    if failed_files:
        console.print(f"\n[yellow]⚠ {len(failed_files)} file(s) failed:[/yellow]")
        for rel_path, error in failed_files[:5]:
            console.print(f"  [dim]{rel_path}: {error}[/dim]")
    else:
        console.print(f"  [green]✓ Uploaded {upload_count} audio files[/green]")
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
def refresh(
    path: Optional[Path] = typer.Argument(None, help="Refresh tracks from specific file or folder"),
    track: Optional[str] = typer.Option(None, "--track", help="Refresh specific track by name"),
    list_gaps: bool = typer.Option(False, "--list", "-l", help="List tracks with missing metadata"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed progress for each track"),
):
    """
    Refresh metadata for existing tracks in Qdrant by filling missing fields.

    This command scans tracks already in your library and fills any missing
    metadata (lyrics, moods, themes, album art, etc.) by re-running the
    appropriate pipeline stages.

    By default, only tracks with missing metadata are shown. Use --verbose
    to see detailed progress for each track.

    Examples:
        vectrola refresh                          # Refresh all user's tracks
        vectrola refresh --verbose                # Show detailed per-track progress
        vectrola refresh --track "Song Name"      # Refresh one track
        vectrola refresh /path/to/music           # Refresh tracks from folder
        vectrola refresh --list                   # Show tracks with gaps

    Note: For failed ingestions, just run 'vectrola ingest' again.
          Deduplication will skip already-processed tracks.
    """
    from vectrola.storage.qdrant import get_db
    from vectrola.services.metadata_gap_detector import detect_missing_fields
    from vectrola.services.metadata_refresher import MetadataRefresher
    from vectrola.config import get_or_create_user_id, get_device_id
    from qdrant_client import models

    db = get_db()
    user_id = get_or_create_user_id()
    device_id = get_device_id()

    # Collect tracks to refresh
    tracks_to_refresh = []

    if track:
        # Refresh specific track by name
        # First get user's track IDs
        user_track_ids = db.get_user_track_ids(user_id)

        if not user_track_ids:
            console.print(f"[red]No tracks found in your library.[/red]")
            return

        # Search for tracks matching the title
        points, _ = db.client.scroll(
            collection_name=db.COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="track_id",
                        match=models.MatchAny(any=user_track_ids[:1000])
                    ),
                    models.FieldCondition(
                        key="title",
                        match=models.MatchText(text=track)
                    )
                ]
            ),
            limit=10,
        )

        if not points:
            console.print(f"[red]Track '{track}' not found in your library.[/red]")
            return

        # If multiple matches, show list and pick first
        if len(points) > 1:
            console.print(f"[yellow]Found {len(points)} matches for '{track}', refreshing first:[/yellow]")
            for p in points:
                artists = ", ".join(p.payload.get("artists", []))
                console.print(f"  • {p.payload.get('title')} - {artists}")

        point = points[0]
        # Try to find local file path from sources
        sources = point.payload.get("sources", {})
        file_path = sources.get("local", {}).get(device_id)
        tracks_to_refresh.append((point.id, point.payload, Path(file_path) if file_path else None))

    elif path:
        # Refresh tracks from specific file/folder
        if not path.exists():
            console.print(f"[red]Path not found: {path}[/red]")
            return

        # Collect file paths
        if path.is_file():
            file_paths = [path]
        else:
            pattern = "**/*"
            file_paths = []
            for ext in [".mp3", ".flac", ".wav", ".m4a", ".ogg"]:
                file_paths.extend(path.glob(f"{pattern}{ext}"))
                file_paths.extend(path.glob(f"{pattern}{ext.upper()}"))

        # Query Qdrant for each file
        for fp in file_paths:
            points, _ = db.client.scroll(
                collection_name=db.COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key=f"sources.local.{device_id}",
                            match=models.MatchValue(value=str(fp))
                        )
                    ]
                ),
                limit=1,
            )
            if points:
                tracks_to_refresh.append((points[0].id, points[0].payload, fp))

    else:
        # Default: refresh all user's tracks
        # Get user's track IDs from user_library collection
        user_track_ids = db.get_user_track_ids(user_id)

        if not user_track_ids:
            console.print(f"[yellow]No tracks found in your library.[/yellow]")
            return

        tracks_to_refresh = []
        offset = None

        # Fetch tracks in batches (handle >1000 tracks)
        for i in range(0, len(user_track_ids), 1000):
            batch_ids = user_track_ids[i:i+1000]

            batch_offset = None
            while True:
                points, batch_offset = db.client.scroll(
                    collection_name=db.COLLECTION,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="track_id",
                                match=models.MatchAny(any=batch_ids)
                            )
                        ]
                    ),
                    limit=100,
                    offset=batch_offset,
                    with_payload=True,
                )

                for point in points:
                    # Try to find local file path
                    sources = point.payload.get("sources", {})
                    file_path = sources.get("local", {}).get(device_id)
                    tracks_to_refresh.append((point.id, point.payload, Path(file_path) if file_path else None))

                if batch_offset is None:
                    break

    if not tracks_to_refresh:
        console.print("[yellow]No tracks found to refresh.[/yellow]")
        return

    # List mode - just show tracks with gaps
    if list_gaps:
        console.print(f"[bold]Tracks with missing metadata:[/bold]\n")

        gaps_found = 0
        for point_id, payload, file_path in tracks_to_refresh:
            missing = detect_missing_fields(payload)
            if missing:
                gaps_found += 1
                title = payload.get("title", "Unknown")
                artists = ", ".join(payload.get("artists", []))
                console.print(f"• {title} - {artists}")
                console.print(f"  Missing: {', '.join(missing)}")

        if gaps_found == 0:
            console.print("[green]All tracks have complete metadata![/green]")
        else:
            console.print(f"\n[yellow]{gaps_found} tracks need refreshing.[/yellow]")

        return

    # Pre-scan: identify tracks with gaps
    tracks_with_gaps = []
    for point_id, payload, file_path in tracks_to_refresh:
        missing = detect_missing_fields(payload)
        if missing:
            tracks_with_gaps.append((point_id, payload, file_path, missing))

    if not tracks_with_gaps:
        console.print("[green]All tracks have complete metadata![/green]")
        return

    total_tracks = len(tracks_to_refresh)
    tracks_needing_refresh = len(tracks_with_gaps)

    console.print(f"🔄 Found {tracks_needing_refresh} tracks with missing metadata (out of {total_tracks} total)\n")

    refresher = MetadataRefresher()
    updated_count = 0
    error_count = 0

    if verbose:
        # Verbose mode: show detailed per-track output
        for i, (point_id, payload, file_path, missing) in enumerate(tracks_with_gaps, 1):
            title = payload.get("title", "Unknown")
            track_id = payload.get("track_id", "")

            console.print(f"[{i}/{tracks_needing_refresh}] {title}")
            console.print(f"   → Filling: {', '.join(missing)}")

            try:
                updates = refresher.refresh_track(track_id, missing, file_path)

                if updates:
                    db.client.set_payload(
                        collection_name=db.COLLECTION,
                        payload=updates,
                        points=[point_id]
                    )
                    updated_count += 1
                    console.print(f"   ✓ Updated: {len(updates)} fields")
                else:
                    console.print(f"   ⚠ No updates available")

            except Exception as e:
                error_count += 1
                console.print(f"   ✗ Error: {e}")

    else:
        # Non-verbose mode: show progress bar (like --sync)
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            transient=False,
            console=console,
        ) as progress:
            task = progress.add_task("Refreshing metadata", total=tracks_needing_refresh)

            for point_id, payload, file_path, missing in tracks_with_gaps:
                track_id = payload.get("track_id", "")

                try:
                    updates = refresher.refresh_track(track_id, missing, file_path)

                    if updates:
                        db.client.set_payload(
                            collection_name=db.COLLECTION,
                            payload=updates,
                            points=[point_id]
                        )
                        updated_count += 1

                except Exception as e:
                    error_count += 1

                progress.advance(task)

    # Summary
    console.print()
    console.print(f"✅ Updated: {updated_count}/{tracks_needing_refresh} tracks")
    if error_count > 0:
        console.print(f"❌ Errors: {error_count} tracks")

    # Suggest wiki regeneration if any tracks were updated
    if updated_count > 0:
        console.print()
        console.print("[bold]Next step:[/bold]")
        console.print("  • Regenerate wiki to see changes: [cyan]vectrola wiki[/cyan]")


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
        from qdrant_client import models

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


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
