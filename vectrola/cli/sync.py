"""Google Drive sync helpers for wiki and audio uploads."""

import json
import os
from pathlib import Path
from multiprocessing import Pool

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from vectrola.config import load_config, get_or_create_user_id, CONFIG_PATH
from vectrola.storage.wiki import WikiGenerator
from vectrola.gdrive.sync_cache import (
    load_sync_cache,
    save_sync_cache,
    file_needs_upload,
    update_cached_file,
    get_files_to_delete,
    remove_cached_file,
    compute_md5,
)
from vectrola.gdrive.parallel_upload import init_worker, upload_single_file, upload_single_file_with_id

from .helpers import console


def _sync_to_drive(client, wiki_dir: Path, drive_root: str, db):
    """Sync both wiki and audio files to Google Drive.

    Flow:
    1. Query Drive for existing audio files → get {path: file_id} map
    2. Update user_library with gdrive sources (from Drive, not cache)
    3. Upload any NEW audio files
    4. Generate wiki ONCE (now has all gdrive IDs)
    5. Upload wiki
    """
    config = load_config()
    user_id = get_or_create_user_id()

    # Ensure folder IDs are cached
    if not config.gdrive_wiki_folder_id or not config.gdrive_audio_folder_id:
        console.print("  [yellow]Creating Vectrola folders...[/yellow]")
        audio_id, wiki_id = client.ensure_vectrola_folders()

        # Update config
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

    # Phase 1: Query Drive for existing audio files
    console.rule("[bold cyan]Reading Drive Audio Files")
    try:
        drive_audio_files = client.list_audio_files_map(config.gdrive_audio_folder_id)
        console.print(f"  [dim]Found {len(drive_audio_files)} audio files on Drive[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Warning: Could not list Drive audio files: {e}[/yellow]")
        drive_audio_files = {}

    # Phase 2: Update user_library with gdrive sources from Drive
    console.rule("[bold cyan]Updating Library with GDrive Sources")

    # Get user_library entries (has track_id, sources)
    user_tracks = db.get_all_tracks()

    # Build a map of track_id -> metadata from main library
    track_metadata = {}
    for ut in user_tracks:
        track_id = ut.get("track_id", "")
        if track_id:
            # Get full track info from main library
            track_record = db.get_track_by_id(track_id)
            if track_record:
                track_metadata[track_id] = track_record.payload

    # Build a map of filename -> (rel_path, file_id) for easier matching
    # Drive files might be under "Unknown/" but we need to match by title
    filename_to_drive = {}
    for rel_path, file_id in drive_audio_files.items():
        filename = rel_path.split("/")[-1]  # Get just the filename
        filename_to_drive[filename] = (rel_path, file_id)

    updated_count = 0

    for ut in user_tracks:
        track_id = ut.get("track_id", "")
        if not track_id or track_id not in track_metadata:
            continue

        meta = track_metadata[track_id]
        title = meta.get("title", "")

        if not title:
            continue

        # Try to match by title (filename) with multiple extensions
        matched_file_id = None
        matched_rel_path = None

        for ext in [".mp3", ".flac", ".m4a", ".wav", ".ogg", ".webm"]:
            filename = f"{title}{ext}"
            if filename in filename_to_drive:
                matched_rel_path, matched_file_id = filename_to_drive[filename]
                break

        if matched_file_id:
            success = db.update_user_library_source(
                track_id=track_id,
                user_id=user_id,
                source_type="cloud",
                provider="gdrive",
                file_id=matched_file_id,
                path=matched_rel_path,
            )
            if success:
                updated_count += 1

    if updated_count > 0:
        console.print(f"  [green]✓ Updated {updated_count} tracks with GDrive sources[/green]")
    else:
        console.print(f"  [dim]No tracks to update (no matching audio on Drive)[/dim]")

    # Phase 3: Upload NEW audio files (pass existing files to skip)
    console.rule("[bold cyan]Syncing Audio Files")
    _upload_audio_files(client, db, f"{drive_root}/audio", config.gdrive_audio_folder_id, drive_audio_files)

    # Phase 4: Generate wiki ONCE (now has gdrive IDs from user_library)
    console.rule("[bold cyan]Generating Wiki")
    generator = WikiGenerator(wiki_dir)
    generator.generate_all()

    # Phase 5: Upload wiki
    console.rule("[bold cyan]Syncing Wiki")
    _upload_wiki_files(client, wiki_dir, f"{drive_root}/wiki", config.gdrive_wiki_folder_id)


def _upload_wiki_files(client, wiki_dir: Path, drive_path: str, wiki_folder_id: str):
    """Upload wiki directory to Google Drive with smart caching."""
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


def _upload_audio_files(client, db, drive_path: str, audio_folder_id: str, existing_drive_files: dict = None) -> list:
    """Upload audio files from Qdrant metadata to Google Drive.

    Args:
        client: DriveClient instance
        db: VectrolaDB instance
        drive_path: Drive path for audio folder
        audio_folder_id: Google Drive folder ID
        existing_drive_files: Optional dict of {rel_path: file_id} from Drive (to skip re-listing)

    Returns:
        List of (track_id, drive_file_id, rel_path) tuples for uploaded files.
    """
    # Load sync cache
    cache = load_sync_cache()

    # Get all tracks from Qdrant for current user
    all_tracks = db.get_all_tracks()  # Returns list of track dicts with metadata

    if not all_tracks:
        console.print("  [yellow]No tracks found in database[/yellow]")
        return []

    # Filter tracks with local file paths
    hostname = os.uname().nodename
    tracks_to_check = []
    for track in all_tracks:
        # New schema: sources.local.{hostname}.file_path
        sources = track.get("sources", {})
        local_sources = sources.get("local", {})

        # Try current device first
        file_path = None
        if hostname in local_sources:
            file_path = local_sources[hostname].get("file_path")

        # Try any device if current device not found
        if not file_path:
            for device_data in local_sources.values():
                if isinstance(device_data, dict) and "file_path" in device_data:
                    file_path = device_data["file_path"]
                    break

        if file_path and Path(file_path).exists():
            tracks_to_check.append((Path(file_path), track))

    if not tracks_to_check:
        console.print("  [yellow]No local audio files found (files may have been moved)[/yellow]")
        return []

    # Use passed-in Drive files map or query Drive
    if existing_drive_files is None:
        try:
            existing_drive_files = client.list_audio_files_map(audio_folder_id)
        except Exception as e:
            console.print(f"  [yellow]Warning: Could not list Drive files: {e}[/yellow]")
            existing_drive_files = {}

    # Check which files need upload
    files_to_upload = []
    skipped_count = 0

    for file_path, track in tracks_to_check:
        track_id = track.get("track_id", "")
        title = track.get("title", file_path.stem)
        artists = track.get("artists", [])
        artist_str = artists[0] if artists else "Unknown"

        # Create a clean relative path
        rel_path = f"{artist_str}/{title}{file_path.suffix}"

        # Skip if already on Drive
        if rel_path in existing_drive_files:
            skipped_count += 1
            continue

        # Compute current hash for cache
        try:
            local_hash = compute_md5(file_path)
        except Exception as e:
            console.print(f"  [yellow]Warning: Cannot read {file_path.name}: {e}[/yellow]")
            continue

        files_to_upload.append((file_path, rel_path, local_hash, track_id))

    upload_count = len(files_to_upload)

    if skipped_count > 0:
        console.print(f"  [dim]Skipping {skipped_count} unchanged audio files[/dim]")

    if upload_count == 0:
        console.print(f"  [green]✓ All {len(tracks_to_check)} audio files up to date![/green]")
        return []

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

    # Handle deleted files (files no longer present locally)
    current_rel_paths = set()
    for file_path, track in tracks_to_check:
        # Reconstruct relative path (same logic as earlier)
        title = track.get("title", file_path.stem)
        artists = track.get("artists", [])
        artist_str = artists[0] if artists else "Unknown"
        rel_path = f"{artist_str}/{title}{file_path.suffix}"
        current_rel_paths.add(rel_path)

    deleted_files = get_files_to_delete(cache, current_rel_paths, "audio_files")
    if deleted_files:
        console.print(f"  [dim]Cleaning up {len(deleted_files)} deleted file(s) from cache[/dim]")
        for rel_path in deleted_files:
            remove_cached_file(cache, rel_path, "audio_files")

    # Save updated cache
    save_sync_cache(cache)

    if failed_files:
        console.print(f"\n[yellow]⚠ {len(failed_files)} file(s) failed:[/yellow]")
        for rel_path, error in failed_files[:5]:
            console.print(f"  [dim]{rel_path}: {error}[/dim]")
    else:
        console.print(f"  [green]✓ Uploaded {upload_count} audio files[/green]")

    return uploaded_files
