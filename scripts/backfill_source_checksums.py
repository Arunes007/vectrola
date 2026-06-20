#!/usr/bin/env python3
"""
Backfill checksums for existing sources in user_library.

After migrating sources from vectrola_library to user_library, this script
adds checksums to sources that don't have them yet.

For local sources: calculates MD5 checksum from file (if file exists)
For cloud sources: uses checksum from local source if available, otherwise skips
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from vectrola.storage.qdrant import get_db
from vectrola.ingest.pipeline import calculate_checksum
from rich.console import Console
from rich.progress import Progress
from rich.prompt import Confirm


def main():
    console = Console()
    db = get_db()

    console.print("[bold cyan]Backfill Source Checksums[/bold cyan]\n")
    console.print("This script will add checksums to sources in user_library that don't have them.\n")

    # Get all user_library entries
    console.print("[bold]📊 Analyzing user_library...[/bold]")
    all_entries = []
    offset = None

    while True:
        results, next_offset = db.client.scroll(
            collection_name=db.USER_LIBRARY_COLLECTION,
            limit=100,
            offset=offset,
            with_vectors=False,
        )
        all_entries.extend(results)
        if next_offset is None:
            break
        offset = next_offset

    console.print(f"Found {len(all_entries)} user library entries\n")

    # Count entries needing checksum backfill
    needs_checksum = 0
    has_checksum = 0
    no_sources = 0

    for entry in all_entries:
        sources = entry.payload.get("sources", {"local": {}, "cloud": {}})

        if not sources or (not sources.get("local") and not sources.get("cloud")):
            no_sources += 1
            continue

        # Check if any source is missing checksum
        needs_update = False
        for device, source_info in sources.get("local", {}).items():
            if isinstance(source_info, dict) and "checksum" not in source_info:
                needs_update = True
                break

        if not needs_update:
            for provider, source_info in sources.get("cloud", {}).items():
                if isinstance(source_info, dict) and "checksum" not in source_info:
                    needs_update = True
                    break

        if needs_update:
            needs_checksum += 1
        else:
            has_checksum += 1

    console.print(f"  • Already have checksums: {has_checksum}")
    console.print(f"  • Need checksums: {needs_checksum}")
    console.print(f"  • No sources: {no_sources}\n")

    if needs_checksum == 0:
        console.print("[green]✓ All sources already have checksums. Nothing to backfill.[/green]")
        return

    # Ask for confirmation
    if not Confirm.ask(f"Proceed with backfilling checksums for {needs_checksum} entries?"):
        console.print("[yellow]Backfill cancelled.[/yellow]")
        return

    console.print()

    stats = {
        "updated": 0,
        "errors": 0,
        "skipped": 0,
        "file_not_found": 0,
        "checksums_added": 0
    }

    with Progress(console=console) as progress:
        task = progress.add_task("[cyan]Backfilling checksums...", total=len(all_entries))

        for entry in all_entries:
            try:
                sources = entry.payload.get("sources", {"local": {}, "cloud": {}})

                if not sources or (not sources.get("local") and not sources.get("cloud")):
                    stats["skipped"] += 1
                    progress.advance(task)
                    continue

                updated = False

                # Process local sources
                for device, source_info in sources.get("local", {}).items():
                    if isinstance(source_info, dict):
                        if "checksum" not in source_info:
                            file_path = source_info.get("file_path")
                            if file_path and Path(file_path).exists():
                                try:
                                    checksum = calculate_checksum(Path(file_path))
                                    source_info["checksum"] = checksum
                                    updated = True
                                    stats["checksums_added"] += 1
                                except Exception as e:
                                    progress.console.print(f"[yellow]Error calculating checksum for {file_path}: {e}[/yellow]")
                                    stats["errors"] += 1
                            else:
                                stats["file_not_found"] += 1
                    elif isinstance(source_info, str):
                        # Old format: just a file path string
                        # Convert to new format with checksum
                        if Path(source_info).exists():
                            try:
                                checksum = calculate_checksum(Path(source_info))
                                sources["local"][device] = {
                                    "file_path": source_info,
                                    "checksum": checksum
                                }
                                updated = True
                                stats["checksums_added"] += 1
                            except Exception as e:
                                progress.console.print(f"[yellow]Error calculating checksum for {source_info}: {e}[/yellow]")
                                stats["errors"] += 1
                        else:
                            stats["file_not_found"] += 1

                # Process cloud sources
                # For cloud sources, we can't calculate checksum directly
                # Skip for now (user can re-ingest from cloud to get checksums)
                for provider, source_info in sources.get("cloud", {}).items():
                    if isinstance(source_info, dict) and "checksum" not in source_info:
                        # Try to use checksum from local source if same track
                        local_sources = sources.get("local", {})
                        if local_sources:
                            # Use first available local checksum
                            first_local = next(iter(local_sources.values()), None)
                            if isinstance(first_local, dict) and "checksum" in first_local:
                                source_info["checksum"] = first_local["checksum"]
                                updated = True
                                stats["checksums_added"] += 1

                if updated:
                    # Update user_library entry
                    db.client.set_payload(
                        collection_name=db.USER_LIBRARY_COLLECTION,
                        payload={"sources": sources},
                        points=[entry.id]
                    )
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as e:
                progress.console.print(f"\n[red]Error processing entry {entry.id}: {e}[/red]")
                stats["errors"] += 1

            progress.advance(task)

    console.print()
    console.print("[bold green]✅ Backfill Complete![/bold green]")
    console.print(f"  • Entries updated: {stats['updated']}")
    console.print(f"  • Checksums added: {stats['checksums_added']}")
    console.print(f"  • Skipped: {stats['skipped']}")
    console.print(f"  • Files not found: {stats['file_not_found']}")
    if stats['errors'] > 0:
        console.print(f"  • [red]Errors: {stats['errors']}[/red]")

    if stats['file_not_found'] > 0:
        console.print()
        console.print("[yellow]Note: Files not found will not have checksums.[/yellow]")
        console.print("If you still have these files, re-ingest them to add checksums.")


if __name__ == "__main__":
    main()
