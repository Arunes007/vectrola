#!/usr/bin/env python
"""
Migrate Qdrant collection to support acoustic_clap vectors.

Since Qdrant doesn't support adding named vectors after creation,
this script:
1. Reads all points from old collection
2. Creates new collection with both vectors
3. Re-inserts points (acoustic_clap will be added later)
"""

from qdrant_client import QdrantClient, models
from tqdm import tqdm


def migrate_collection():
    """Migrate vectrola_library to support acoustic_clap."""

    client = QdrantClient(url="http://localhost:6333")
    collection = "vectrola_library"

    print(f"Migrating '{collection}' to support acoustic_clap vectors...")
    print()

    # Step 1: Check current collection
    try:
        info = client.get_collection(collection)
        vectors = info.config.params.vectors
        point_count = info.points_count

        print(f"Current collection:")
        print(f"  Points: {point_count}")
        print(f"  Vectors: {list(vectors.keys())}")

        if "acoustic_clap" in vectors:
            print("\n✓ Collection already has acoustic_clap")
            return

        print()
        response = input(f"Recreate collection with {point_count} points? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

    except Exception as e:
        print(f"✗ Error reading collection: {e}")
        return

    # Step 2: Read all points
    print("\nReading all points...")
    all_points = []
    offset = None

    while True:
        results, offset = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )

        all_points.extend(results)

        if offset is None:
            break

    print(f"  Read {len(all_points)} points")

    # Step 3: Delete old collection
    print("\nDeleting old collection...")
    client.delete_collection(collection)
    print("  ✓ Deleted")

    # Step 4: Create new collection with both vectors
    print("\nCreating new collection with acoustic_clap...")
    client.create_collection(
        collection_name=collection,
        vectors_config={
            "lyrics_dense": models.VectorParams(
                size=384,
                distance=models.Distance.COSINE,
            ),
            "acoustic_clap": models.VectorParams(
                size=512,
                distance=models.Distance.COSINE,
            ),
        },
    )
    print("  ✓ Created")

    # Step 5: Re-insert points (lyrics_dense only, acoustic_clap added later)
    print("\nRe-inserting points...")
    for point in tqdm(all_points):
        client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=point.id,
                    vector={"lyrics_dense": point.vector["lyrics_dense"]},
                    payload=point.payload,
                )
            ],
        )

    print(f"\n✅ Migration complete!")
    print(f"   Re-inserted {len(all_points)} points")
    print(f"   Collection now supports acoustic_clap")
    print(f"\nNext: Run 'python scripts/add_audio_embeddings.py' to add audio vectors")


if __name__ == "__main__":
    migrate_collection()
