#!/usr/bin/env python
"""Generate audio embeddings for all indexed tracks and update Qdrant."""

import sys
from pathlib import Path
from tqdm import tqdm

from vectrola.storage.qdrant import get_db
from vectrola.ingest.embeddings import get_audio_embedder


def add_audio_embeddings(limit: int = None):
    """
    Generate CLAP audio embeddings for all tracks.

    This reads existing tracks from Qdrant and adds acoustic_clap vectors.
    """

    db = get_db()
    audio_embedder = get_audio_embedder()

    tracks = db.list_all(limit=limit or 500)
    print(f"Found {len(tracks)} tracks to process")
    print("Loading CLAP model (this takes ~10s)...")

    # Force model load
    _ = audio_embedder.model

    updated = 0
    errors = 0
    skipped = 0

    for t in tqdm(tracks, desc="Embedding audio"):
        p = t.payload
        file_path = p.get("file_path", "")

        if not file_path or not Path(file_path).exists():
            tqdm.write(f"  ⏭ {p.get('title', 'Unknown')} - file not found")
            skipped += 1
            continue

        try:
            # Generate CLAP embedding (10s from middle of track)
            audio_vector = audio_embedder.embed_audio(file_path, duration=10.0, offset=30.0)

            # Get existing lyrics vector
            track_record = db.get_track(file_path)
            if not track_record or not track_record.vector:
                tqdm.write(f"  ⏭ {p.get('title', 'Unknown')} - no lyrics vector")
                skipped += 1
                continue

            lyrics_vector = track_record.vector.get("lyrics_dense")
            if not lyrics_vector:
                tqdm.write(f"  ⏭ {p.get('title', 'Unknown')} - no lyrics vector")
                skipped += 1
                continue

            # Update with both vectors
            db.upsert_track(
                file_path=file_path,
                lyrics_vector=lyrics_vector,
                audio_vector=audio_vector,
                payload=p,
            )

            tqdm.write(f"  ✓ {p.get('title', 'Unknown')}")
            updated += 1

        except Exception as e:
            tqdm.write(f"  ✗ {p.get('title', 'Unknown')} - {e}")
            errors += 1

    print(f"\n✅ Updated: {updated} tracks")
    if skipped:
        print(f"⏭ Skipped: {skipped} tracks")
    if errors:
        print(f"❌ Errors: {errors} tracks")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    add_audio_embeddings(limit)
