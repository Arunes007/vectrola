#!/usr/bin/env python
"""Re-run Ollama LLM synthesis on all indexed tracks and update tags + Qdrant."""

import sys
from pathlib import Path
from tqdm import tqdm

from vectrola.storage.qdrant import get_db
from vectrola.storage.tags import write_tags, read_vectrola_tags
from vectrola.ingest.synthesis import Synthesizer
from vectrola.ingest.embeddings import get_text_embedder


# Mood synonyms for better semantic matching
# When we store "melancholic", we also store synonyms so "sad" queries match
MOOD_SYNONYMS = {
    "melancholic": ["sad", "sorrowful", "gloomy", "depressed", "heartbroken"],
    "hopeless": ["desperate", "despair", "defeated", "bleak", "desolate"],
    "hopeful": ["optimistic", "uplifting", "encouraging", "positive"],
    "romantic": ["loving", "passionate", "tender", "affectionate"],
    "energetic": ["upbeat", "lively", "vibrant", "dynamic", "exciting"],
    "aggressive": ["angry", "intense", "fierce", "violent", "rage"],
    "peaceful": ["calm", "serene", "tranquil", "relaxing", "soothing"],
    "nostalgic": ["reminiscent", "wistful", "longing for past", "sentimental"],
    "introspective": ["reflective", "thoughtful", "contemplative", "meditative"],
    "euphoric": ["ecstatic", "joyful", "elated", "blissful", "happy"],
}


def build_searchable_text(lyrics: str, moods: list, themes: list, narrative: str) -> str:
    """
    Build searchable text with weighted moods/themes.

    Strategy:
    1. Include lyrics (full semantic content)
    2. Repeat moods 3x with synonyms for stronger signal
    3. Repeat themes 2x
    4. Include narrative
    """
    parts = []

    # 1. Lyrics (base content)
    if lyrics:
        parts.append(lyrics)

    # 2. Moods - repeated 3x with synonyms for stronger matching
    if moods:
        mood_text = ", ".join(moods)
        # Add synonyms
        expanded_moods = list(moods)
        for mood in moods:
            mood_lower = mood.lower()
            if mood_lower in MOOD_SYNONYMS:
                expanded_moods.extend(MOOD_SYNONYMS[mood_lower])

        expanded_text = ", ".join(expanded_moods)
        # Repeat for weight
        parts.append(f"Mood: {expanded_text}")
        parts.append(f"Feeling: {expanded_text}")
        parts.append(f"Emotion: {mood_text}")

    # 3. Themes - repeated 2x
    if themes:
        theme_text = ", ".join(themes)
        parts.append(f"Themes: {theme_text}")
        parts.append(f"About: {theme_text}")

    # 4. Narrative
    if narrative:
        parts.append(f"Story: {narrative}")

    return "\n".join(parts)


def resynthesize_all(limit: int = None, skip_llm: bool = False):
    """
    Re-run LLM synthesis on all tracks.

    Args:
        limit: Max tracks to process
        skip_llm: If True, only re-embed with existing moods (faster)
    """

    db = get_db()
    synthesizer = Synthesizer() if not skip_llm else None
    embedder = get_text_embedder()

    tracks = db.list_all(limit=limit or 500)
    print(f"Found {len(tracks)} tracks to re-{'embed' if skip_llm else 'synthesize'}")

    updated = 0
    errors = 0

    for t in tqdm(tracks, desc="Processing"):
        p = t.payload
        file_path = p.get("file_path", "")
        lyrics = p.get("lyrics", "")

        if not lyrics:
            tqdm.write(f"  ⏭ {p.get('title', 'Unknown')} - no lyrics, skipping")
            continue

        try:
            if skip_llm:
                # Use existing moods/themes
                moods = p.get("moods", [])
                themes = p.get("themes", [])
                narrative = p.get("narrative", "")
            else:
                # Run LLM synthesis
                synthesis = synthesizer.synthesize(lyrics)
                moods = synthesis.moods
                themes = synthesis.themes
                narrative = synthesis.narrative

                # Update payload with new moods/themes
                p["moods"] = moods
                p["themes"] = themes
                p["narrative"] = narrative
                p["imagery"] = synthesis.imagery

            # Build searchable text with weighted moods + synonyms
            searchable_text = build_searchable_text(lyrics, moods, themes, narrative)
            new_vector = embedder.embed(searchable_text)

            # Update Qdrant
            db.upsert_track(
                file_path=file_path,
                lyrics_vector=new_vector,
                payload=p,
            )

            # Update file tags if file exists (only if we re-ran LLM)
            if not skip_llm and Path(file_path).exists():
                write_tags(Path(file_path), p)

            tqdm.write(f"  ✓ {p.get('title', 'Unknown')} → {moods}")
            updated += 1

        except Exception as e:
            tqdm.write(f"  ✗ {p.get('title', 'Unknown')} - {e}")
            errors += 1

    print(f"\n✅ Updated: {updated} tracks")
    if errors:
        print(f"❌ Errors: {errors} tracks")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Re-synthesize tracks with LLM")
    parser.add_argument("limit", nargs="?", type=int, default=None, help="Max tracks to process")
    parser.add_argument("--skip-llm", action="store_true", help="Only re-embed, don't re-run LLM")
    args = parser.parse_args()

    resynthesize_all(limit=args.limit, skip_llm=args.skip_llm)
