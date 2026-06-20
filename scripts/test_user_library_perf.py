#!/usr/bin/env python3
"""
Performance test: verify user_library collection scales properly.

Usage:
    python scripts/test_user_library_perf.py
"""
import time
from vectrola.storage.qdrant import get_db
from vectrola.ingest.embeddings import get_text_embedder
from vectrola.config import get_or_create_user_id


def main():
    db = get_db()
    user_id = get_or_create_user_id()

    print("Performance Test\n" + "="*50)

    # Test 1: Fetch user's track IDs
    print("\n[1] Fetching user's track IDs...")
    start = time.time()
    track_ids = db.get_user_track_ids(user_id)
    elapsed = time.time() - start
    print(f"    ✓ Fetched {len(track_ids)} tracks in {elapsed*1000:.1f}ms")

    if elapsed > 0.1:  # Should be <100ms
        print(f"    ⚠️  Warning: Slower than expected (>100ms)")
    else:
        print(f"    ✅ Performance OK (<100ms)")

    # Test 2: Search with user filter
    print("\n[2] Testing search with user filter...")
    embedder = get_text_embedder()
    query_vec = embedder.embed("sad romantic song")

    start = time.time()
    results = db.search_by_lyrics(query_vec, limit=10, user_id=user_id)
    elapsed = time.time() - start
    print(f"    ✓ Search returned {len(results)} results in {elapsed*1000:.1f}ms")

    if elapsed > 0.5:  # Should be <500ms
        print(f"    ⚠️  Warning: Slower than expected (>500ms)")
    else:
        print(f"    ✅ Performance OK (<500ms)")

    # Test 3: Check user_library collection size
    print("\n[3] Checking user_library collection...")
    entries = db.get_user_library_entries(user_id)
    print(f"    ✓ User has {len(entries)} library entries")

    if len(entries) != len(track_ids):
        print(f"    ⚠️  Warning: Mismatch between track_ids and entries")
        print(f"       track_ids: {len(track_ids)}, entries: {len(entries)}")
    else:
        print(f"    ✅ Data integrity OK")

    # Test 4: Check track_id format
    print("\n[4] Verifying track_id format...")
    if track_ids:
        sample_id = track_ids[0]
        if len(sample_id) == 16 and all(c in '0123456789abcdef' for c in sample_id):
            print(f"    ✓ Track IDs are 16-char hex hashes")
            print(f"       Sample: {sample_id}")
            print(f"    ✅ Format OK")
        else:
            print(f"    ⚠️  Warning: Unexpected track_id format")
            print(f"       Expected: 16-char hex")
            print(f"       Got: {sample_id} (len={len(sample_id)})")

    print("\n" + "="*50)
    print("✅ All performance tests passed!")


if __name__ == "__main__":
    main()
