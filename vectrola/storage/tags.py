"""Write metadata to audio file tags using mutagen."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import json


def has_embedded_artwork(file_path: Path) -> bool:
    """
    Check if audio file has embedded album art.

    Args:
        file_path: Path to the audio file

    Returns:
        True if file has embedded album art
    """
    from mutagen import File
    from mutagen.id3 import ID3
    from mutagen.flac import FLAC

    file_path = Path(file_path)

    try:
        if file_path.suffix.lower() == ".mp3":
            tags = ID3(file_path)
            # APIC = Attached Picture
            return any(key.startswith("APIC") for key in tags.keys())

        elif file_path.suffix.lower() == ".flac":
            flac = FLAC(file_path)
            return len(flac.pictures) > 0

        elif file_path.suffix.lower() in [".m4a", ".mp4"]:
            audio = File(file_path)
            # covr = cover art in MP4
            return "covr" in audio.tags if audio and audio.tags else False

    except Exception:
        pass

    return False


@dataclass
class FileTags:
    """Tags read from an audio file."""
    title: str = ""
    artists: list[str] = None
    album: str = ""
    year: Optional[int] = None
    composer: str = ""
    genre: str = ""

    # Indicates if file has good metadata
    has_metadata: bool = False

    def __post_init__(self):
        if self.artists is None:
            self.artists = []


def read_file_tags(file_path: Path) -> FileTags:
    """
    Read metadata tags from an audio file.

    Args:
        file_path: Path to the audio file

    Returns:
        FileTags with extracted metadata
    """
    from mutagen import File
    from mutagen.id3 import ID3
    from mutagen.flac import FLAC

    tags = FileTags()
    file_path = Path(file_path)

    try:
        audio = File(file_path)
        if audio is None or audio.tags is None:
            return tags

        # MP3 files (ID3 tags)
        if file_path.suffix.lower() == ".mp3":
            id3 = ID3(file_path)

            # Title
            if "TIT2" in id3:
                tags.title = str(id3["TIT2"])

            # Artist(s)
            if "TPE1" in id3:
                artist_str = str(id3["TPE1"])
                # Split by common separators
                tags.artists = [a.strip() for a in artist_str.replace(";", ",").replace("/", ",").split(",")]

            # Album
            if "TALB" in id3:
                tags.album = str(id3["TALB"])

            # Year
            if "TDRC" in id3:
                year_str = str(id3["TDRC"])[:4]
                if year_str.isdigit():
                    tags.year = int(year_str)
            elif "TYER" in id3:
                year_str = str(id3["TYER"])[:4]
                if year_str.isdigit():
                    tags.year = int(year_str)

            # Composer
            if "TCOM" in id3:
                tags.composer = str(id3["TCOM"])

            # Genre
            if "TCON" in id3:
                tags.genre = str(id3["TCON"])

        # FLAC files
        elif file_path.suffix.lower() == ".flac":
            flac = FLAC(file_path)

            if "title" in flac:
                tags.title = flac["title"][0]
            if "artist" in flac:
                tags.artists = [a.strip() for a in flac["artist"][0].replace(";", ",").split(",")]
            if "album" in flac:
                tags.album = flac["album"][0]
            if "date" in flac:
                year_str = flac["date"][0][:4]
                if year_str.isdigit():
                    tags.year = int(year_str)
            if "composer" in flac:
                tags.composer = flac["composer"][0]
            if "genre" in flac:
                tags.genre = flac["genre"][0]

        # M4A/MP4 files
        elif file_path.suffix.lower() in [".m4a", ".mp4"]:
            if "\xa9nam" in audio.tags:
                tags.title = str(audio.tags["\xa9nam"][0])
            if "\xa9ART" in audio.tags:
                tags.artists = [str(audio.tags["\xa9ART"][0])]
            if "\xa9alb" in audio.tags:
                tags.album = str(audio.tags["\xa9alb"][0])
            if "\xa9day" in audio.tags:
                year_str = str(audio.tags["\xa9day"][0])[:4]
                if year_str.isdigit():
                    tags.year = int(year_str)

        # Check if we have meaningful metadata
        tags.has_metadata = bool(tags.title and tags.artists and tags.artists[0] not in ["", "Unknown Artist"])

        return tags

    except Exception as e:
        print(f"Error reading tags from {file_path}: {e}")
        return tags


def write_tags(
    file_path: Path,
    analysis: dict[str, Any],
    write_to_comment: bool = True,
    write_to_lyrics: bool = False,
) -> bool:
    """
    Write analysis metadata to audio file tags.

    Writes both:
    1. Standard ID3 tags (title, artist, album, year, composer)
    2. Vectrola analysis (moods, themes, narrative, imagery) in COMMENT

    Args:
        file_path: Path to the audio file
        analysis: Dictionary with all track analysis fields
        write_to_comment: Write to COMMENT/DESCRIPTION tag
        write_to_lyrics: Write to LYRICS tag (for lyrics text)

    Returns:
        True if successful, False otherwise
    """
    from mutagen import File
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, COMM, USLT, TIT2, TPE1, TALB, TDRC, TCOM, TEXT
    from mutagen.flac import FLAC

    try:
        file_path = Path(file_path)

        # Build the semantic analysis string for human-readable comment
        metadata_parts = []

        if analysis.get("movie"):
            metadata_parts.append(f"Movie: {analysis['movie']}")

        if analysis.get("artists"):
            artists = analysis["artists"]
            if isinstance(artists, list):
                metadata_parts.append(f"Singers: {', '.join(artists)}")
            else:
                metadata_parts.append(f"Singers: {artists}")

        if analysis.get("composer"):
            metadata_parts.append(f"Composer: {analysis['composer']}")

        if analysis.get("lyricist"):
            metadata_parts.append(f"Lyricist: {analysis['lyricist']}")

        if analysis.get("year"):
            metadata_parts.append(f"Year: {analysis['year']}")

        if analysis.get("moods"):
            metadata_parts.append(f"Moods: {', '.join(analysis['moods'])}")

        if analysis.get("themes"):
            metadata_parts.append(f"Themes: {', '.join(analysis['themes'])}")

        if analysis.get("narrative"):
            metadata_parts.append(f"Narrative: {analysis['narrative']}")

        if analysis.get("imagery"):
            metadata_parts.append(f"Imagery: {', '.join(analysis['imagery'])}")

        metadata_str = " | ".join(metadata_parts)

        # Also store as JSON for programmatic access
        json_str = json.dumps(analysis, ensure_ascii=False)

        # Detect file format and write tags
        audio = File(file_path)

        if audio is None:
            return False

        # Handle MP3 files
        if file_path.suffix.lower() == ".mp3":
            try:
                tags = ID3(file_path)
            except Exception:
                tags = ID3()
                tags.save(file_path)
                tags = ID3(file_path)

            # Write standard ID3 tags
            if analysis.get("title"):
                tags.delall("TIT2")
                tags.add(TIT2(encoding=3, text=analysis["title"]))

            if analysis.get("artists"):
                tags.delall("TPE1")
                artists = analysis["artists"]
                if isinstance(artists, list):
                    tags.add(TPE1(encoding=3, text=", ".join(artists)))
                else:
                    tags.add(TPE1(encoding=3, text=artists))

            # Use movie as album for Bollywood soundtracks
            album = analysis.get("movie") or analysis.get("album")
            if album:
                tags.delall("TALB")
                tags.add(TALB(encoding=3, text=album))

            if analysis.get("year"):
                tags.delall("TDRC")
                tags.add(TDRC(encoding=3, text=str(analysis["year"])))

            if analysis.get("composer"):
                tags.delall("TCOM")
                tags.add(TCOM(encoding=3, text=analysis["composer"]))

            if analysis.get("lyricist"):
                tags.delall("TEXT")
                tags.add(TEXT(encoding=3, text=analysis["lyricist"]))

            if write_to_comment:
                # Remove existing Vectrola comments (keep others)
                for key in list(tags.keys()):
                    if key.startswith("COMM") and "Vectrola" in key:
                        del tags[key]
                # Add our analysis as a comment
                tags.add(COMM(encoding=3, lang="eng", desc="Vectrola Analysis", text=metadata_str))
                # Also add JSON version
                tags.add(COMM(encoding=3, lang="eng", desc="Vectrola JSON", text=json_str))

            tags.save(file_path)

        # Handle FLAC files
        elif file_path.suffix.lower() == ".flac":
            flac = FLAC(file_path)

            # Write standard tags
            if analysis.get("title"):
                flac["TITLE"] = analysis["title"]

            if analysis.get("artists"):
                artists = analysis["artists"]
                if isinstance(artists, list):
                    flac["ARTIST"] = ", ".join(artists)
                else:
                    flac["ARTIST"] = artists

            album = analysis.get("movie") or analysis.get("album")
            if album:
                flac["ALBUM"] = album

            if analysis.get("year"):
                flac["DATE"] = str(analysis["year"])

            if analysis.get("composer"):
                flac["COMPOSER"] = analysis["composer"]

            if write_to_comment:
                flac["COMMENT"] = metadata_str
                flac["VECTROLA_JSON"] = json_str

            flac.save()

        # Handle other formats with EasyID3-style interface
        else:
            # Try generic approach
            if hasattr(audio, "tags") and audio.tags is not None:
                audio.tags["comment"] = metadata_str
                audio.save()

        return True

    except Exception as e:
        print(f"Error writing tags to {file_path}: {e}")
        return False


def read_vectrola_tags(file_path: Path) -> Optional[dict[str, Any]]:
    """
    Read Vectrola metadata from audio file tags.

    Args:
        file_path: Path to the audio file

    Returns:
        Dictionary with analysis data, or None if not found
    """
    from mutagen import File
    from mutagen.id3 import ID3, COMM
    from mutagen.flac import FLAC

    try:
        if file_path.suffix.lower() == ".mp3":
            tags = ID3(file_path)
            for key in tags.keys():
                if key.startswith("COMM") and "Vectrola JSON" in key:
                    # COMM frames store text in .text attribute (list)
                    return json.loads(tags[key].text[0])

        elif file_path.suffix.lower() == ".flac":
            flac = FLAC(file_path)
            if "VECTROLA_JSON" in flac:
                return json.loads(flac["VECTROLA_JSON"][0])

        return None

    except Exception:
        return None
