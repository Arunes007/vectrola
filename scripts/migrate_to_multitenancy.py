#!/usr/bin/env python3
"""
Migrate existing Qdrant database to Day 7 multi-tenant format.

This script:
1. Adds track_id to existing points (generated from artist+title)
2. Adds user_ids=["default"] to all existing points
3. Creates ~/.config/vectrola/library.json from existing Qdrant data

Run with:
    python scripts/migrate_to_multitenancy.py

Or with a specific user ID:
    python scripts/migrate_to_multitenancy.py --user-id my_user_id
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from qdrant_client import models


def generate_track_id(spotify_id: str | None, artist: str, title: str) -> str:
    """Generate canonical track ID."""
    if spotify_id:
        return f"spotify:{spotify_id}"
    normalized = f"{artist.lower().strip()}:{title.lower().strip()}"
    hash_digest = hashlib.md5(normalized.encode()).hexdigest()[:16]
    return f"hash:{hash_digest}"


def migrate_qdrant(user_id: str = "default", dry_run: bool = False, fetch_spotify: bool = True):
    """Migrate existing Qdrant points to multi-tenant format."""
    from vectrola.storage.qdrant import get_db

    db = get_db()

    print(f"🔍 Checking Qdrant at {db.url}...")

    if not db.is_connected():
        print("❌ Cannot connect to Qdrant. Make sure it's running.")
        return

    # Lazy load Spotify fetcher
    spotify_fetcher = None
    if fetch_spotify:
        from vectrola.ingest.spotify import SpotifyFetcher
        spotify_fetcher = SpotifyFetcher()
        print("🎵 Spotify lookup enabled")

    # Get all existing points
    points = db.list_all(limit=1000)
    print(f"📊 Found {len(points)} tracks to migrate")

    if not points:
        print("✅ No tracks to migrate")
        return

    migrated = 0
    skipped = 0
    spotify_found = 0
    library_tracks = {}

    for point in points:
        payload = point.payload or {}
        title = payload.get("title", "")
        artists = payload.get("artists", [])
        artist = artists[0] if artists else ""

        # Check if already has spotify track_id
        existing_track_id = payload.get("track_id", "")
        if existing_track_id.startswith("spotify:") and payload.get("user_ids"):
            skipped += 1
            continue

        # Try to fetch Spotify ID if we don't have one
        spotify_id = payload.get("spotify_id")
        if not spotify_id and spotify_fetcher and title:
            spotify_result = spotify_fetcher.get_best_match(title, artist)
            if spotify_result and spotify_result.spotify_id:
                spotify_id = spotify_result.spotify_id
                spotify_found += 1

        # Generate track_id
        track_id = generate_track_id(spotify_id, artist, title)

        # Prepare updates
        updates = {}
        if not payload.get("track_id") or (spotify_id and not existing_track_id.startswith("spotify:")):
            updates["track_id"] = track_id
        if spotify_id and not payload.get("spotify_id"):
            updates["spotify_id"] = spotify_id
        if not payload.get("user_ids"):
            updates["user_ids"] = [user_id]

        if updates and not dry_run:
            db.client.set_payload(
                collection_name=db.COLLECTION,
                payload=updates,
                points=[point.id],
            )

        # Add to library
        file_path = payload.get("file_path", "")
        library_tracks[track_id] = {
            "gdrive_file_id": payload.get("gdrive_file_id"),
            "local_path": file_path,
            "added_at": datetime.utcnow().isoformat() + "Z",
        }

        migrated += 1
        print(f"  ✓ {payload.get('title', 'Unknown')} → {track_id}")

    print()
    print(f"📊 Migration Summary:")
    print(f"   Migrated: {migrated}")
    print(f"   Skipped (already has spotify ID): {skipped}")
    if fetch_spotify:
        print(f"   Spotify IDs found: {spotify_found}")

    if dry_run:
        print("\n⚠️  Dry run - no changes made")
        return

    # Write library.json
    library_path = Path.home() / ".config" / "vectrola" / "library.json"
    library_path.parent.mkdir(parents=True, exist_ok=True)

    library_data = {
        "user_id": user_id,
        "tracks": library_tracks,
    }

    with open(library_path, 'w', encoding='utf-8') as f:
        json.dump(library_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Created library at: {library_path}")
    print(f"   {len(library_tracks)} tracks added to library")


def main():
    from vectrola.config import get_current_user

    parser = argparse.ArgumentParser(description="Migrate Qdrant to multi-tenant format")
    parser.add_argument(
        "--user-id",
        default=None,
        help="User ID to assign to existing tracks (default: auto-detect from session or anon_id)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--no-spotify",
        action="store_true",
        help="Skip Spotify ID lookup (faster, but won't get spotify IDs)",
    )

    args = parser.parse_args()

    # Use provided user_id or auto-detect from session/anon
    user_id = args.user_id or get_current_user()[0]

    print("🔄 Vectrola Multi-Tenant Migration")
    print("=" * 40)
    print(f"User ID: {user_id}")
    print()

    migrate_qdrant(user_id=user_id, dry_run=args.dry_run, fetch_spotify=not args.no_spotify)


if __name__ == "__main__":
    main()
