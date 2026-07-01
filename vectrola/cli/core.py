"""Core music commands: ingest, analyze, search, similar, wiki, refresh."""

import tempfile
import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from qdrant_client import models

from vectrola.config import get_config, get_or_create_user_id, get_device_id
from vectrola.ingest.pipeline import IngestPipeline
from vectrola.search.semantic import SemanticSearch
from vectrola.storage.qdrant import get_db
from vectrola.storage.wiki import WikiGenerator
from vectrola.services.failed_ingests import FailedIngestsManager, detect_error_stage
from vectrola.services.metadata_gap_detector import detect_missing_fields
from vectrola.services.metadata_refresher import MetadataRefresher

from .helpers import console, show_qdrant_error
from .sync import _sync_to_drive


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
            # Sync handles: audio upload → update user_library → generate wiki → upload wiki
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
    else:
        # Only generate wiki locally if not syncing
        generator = WikiGenerator(output)
        generator.generate_all()

        console.print()
        console.print(f"[green]✅ Wiki generated at: {output}[/green]")

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




