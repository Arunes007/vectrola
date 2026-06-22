"""Generate Obsidian wiki vault from indexed tracks."""

import json
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass
from collections import defaultdict

from vectrola.storage.qdrant import get_db
from vectrola.config import get_or_create_user_id


def calculate_era(year) -> str:
    """Calculate era label from year (fallback for tracks without era field)."""
    if not year:
        return "Timeless"
    try:
        year = int(year)
    except (ValueError, TypeError):
        return "Timeless"

    if year < 1990:
        return "Old Melodies"
    elif year < 2000:
        return "90s Nostalgia"
    elif year < 2010:
        return "Y2K Vibes"
    elif year < 2020:
        return "2010s Rewind"
    else:
        return "Fresh Hits"


@dataclass
class WikiPage:
    """A single wiki page."""
    title: str
    file_path: Path
    content: str
    tags: List[str] = None


class WikiGenerator:
    """
    Generate Obsidian-compatible wiki from music library.

    Creates markdown pages with wikilinks for:
    - Individual tracks
    - Artists
    - Moods
    - Themes
    - Movies/Albums

    Supports both local file and GDrive playback (from Qdrant payload).
    """

    def __init__(self, output_dir: Path = Path("./wiki")):
        """
        Initialize wiki generator.

        Args:
            output_dir: Directory to write wiki pages
        """
        self.output_dir = Path(output_dir)
        self.db = get_db()

        # Subdirectories
        self.tracks_dir = self.output_dir / "Tracks"
        self.artists_dir = self.output_dir / "Artists"
        self.moods_dir = self.output_dir / "Moods"
        self.themes_dir = self.output_dir / "Themes"
        self.movies_dir = self.output_dir / "Movies"
        self.eras_dir = self.output_dir / "Eras"

    def generate_all(self):
        """Generate complete wiki for current user."""
        from vectrola.config import get_current_user

        user_id, is_logged_in = get_current_user()

        print("🎧 Generating Vectrola Wiki...")
        if is_logged_in:
            print(f"   User: {user_id}")
        else:
            print(f"   User: {user_id} (anonymous)")
        print()

        # Create directories
        self._create_directories()

        # Fetch only this user's tracks
        tracks = self.db.list_user_tracks(user_id, limit=500)
        print(f"Found {len(tracks)} tracks in your library")
        print()

        # Fetch user's sources from user_library collection
        user_entries = self.db.get_user_library_entries(user_id, limit=10000)
        sources_map = {
            e.payload["track_id"]: e.payload.get("sources", {"local": {}, "cloud": {}})
            for e in user_entries
        }

        # Generate pages (pass sources_map to methods that need it)
        self._generate_track_pages(tracks, sources_map)
        self._generate_artist_pages(tracks, sources_map)
        self._generate_mood_pages(tracks, sources_map)
        self._generate_theme_pages(tracks, sources_map)
        self._generate_movie_pages(tracks, sources_map)
        self._generate_era_pages(tracks, sources_map)
        self._generate_home_page(tracks)

        # Write owner file for security tracking
        owner_file = self.output_dir / ".wiki_owner"
        owner_file.write_text(user_id)

    def _create_directories(self):
        """Create wiki directory structure."""
        for dir_path in [
            self.tracks_dir,
            self.artists_dir,
            self.moods_dir,
            self.themes_dir,
            self.movies_dir,
            self.eras_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _generate_track_pages(self, tracks, sources_map):
        """Generate individual track pages with play button."""
        print(f"📝 Generating track pages...")

        for track in tracks:
            p = track.payload

            title = p.get("title", "Unknown")
            artists = p.get("artists", [])

            # Sanitize filename
            filename = self._sanitize_filename(f"{title}")
            file_path = self.tracks_dir / f"{filename}.md"

            # Build page content with audio player (single track playlist)
            content = self._get_audio_player_script([p], title, sources_map)
            content += "\n\n"
            content += self._build_track_page(p)

            # Write page
            file_path.write_text(content, encoding="utf-8")

        print(f"   ✓ {len(tracks)} track pages")

    def _build_track_page(self, payload: dict) -> str:
        """Build markdown content for a track page."""
        title = payload.get("title", "Unknown")
        artists = payload.get("artists", [])
        album = payload.get("album", "")
        movie = payload.get("movie", "")
        year = payload.get("year", "")
        era = payload.get("era") or calculate_era(year)  # Fallback to calculated
        composer = payload.get("composer", "")
        lyricist = payload.get("lyricist", "")
        moods = payload.get("moods", [])
        themes = payload.get("themes", [])
        narrative = payload.get("narrative", "")
        lyrics = payload.get("lyrics", "")
        file_path = payload.get("file_path", "")

        # Build frontmatter
        lines = ["---"]
        if artists:
            lines.append(f"artists: {artists}")
        if album:
            lines.append(f"album: \"{album}\"")
        if movie:
            lines.append(f"movie: \"{movie}\"")
        if year:
            lines.append(f"year: {year}")
        if era:
            lines.append(f"era: \"{era}\"")
        if moods:
            lines.append(f"tags: [{', '.join(moods)}]")
        if file_path:
            lines.append(f"file_path: \"{file_path}\"")
        lines.append("---")
        lines.append("")

        # Title
        lines.append(f"# {title}")
        lines.append("")

        # Artists
        if artists:
            artist_links = [f"[[{self._sanitize_filename(a)}]]" for a in artists]
            lines.append(f"**Artists:** {', '.join(artist_links)}")
            lines.append("")

        # Movie/Album
        if movie and movie != album:
            movie_link = f"[[{self._sanitize_filename(movie)}]]"
            lines.append(f"**Movie:** {movie_link}")
            lines.append("")
        elif album:
            lines.append(f"**Album:** {album}")
            lines.append("")

        # Era
        if era:
            era_link = f"[[Eras/{self._sanitize_filename(era)}|{era}]]"
            lines.append(f"**Era:** {era_link}")
            lines.append("")

        # Credits
        if composer or lyricist:
            lines.append("## Credits")
            if composer:
                lines.append(f"- **Music:** {composer}")
            if lyricist:
                lines.append(f"- **Lyrics:** {lyricist}")
            if year:
                lines.append(f"- **Year:** {year}")
            lines.append("")

        # AI Analysis
        lines.append("## AI Semantic Analysis")
        lines.append("")

        if narrative:
            lines.append(f"> {narrative}")
            lines.append("")

        # Moods
        if moods:
            mood_links = [f"[[{m}]]" for m in moods]
            lines.append(f"**Moods:** {', '.join(mood_links)}")
            lines.append("")

        # Themes
        if themes:
            theme_links = [f"[[{t}]]" for t in themes]
            lines.append(f"**Themes:** {', '.join(theme_links)}")
            lines.append("")

        # Lyrics
        if lyrics:
            lines.append("## Lyrics")
            lines.append("")
            lines.append("```")
            lines.append(lyrics[:1000])  # First 1000 chars
            if len(lyrics) > 1000:
                lines.append("...")
            lines.append("```")

        return "\n".join(lines)

    def _generate_artist_pages(self, tracks, sources_map):
        """Generate artist index pages with interactive audio player."""
        print(f"👤 Generating artist pages...")

        # Group tracks by artist
        artists_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            for artist in p.get("artists", []):
                artists_tracks[artist].append(p)

        # Generate page for each artist
        for artist, artist_tracks in artists_tracks.items():
            filename = self._sanitize_filename(artist)
            file_path = self.artists_dir / f"{filename}.md"

            # Use audio player script for artist pages
            lines = [self._get_audio_player_script(artist_tracks, artist, sources_map)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(artists_tracks)} artist pages")

    def _generate_mood_pages(self, tracks, sources_map):
        """Generate mood index pages with interactive audio player."""
        print(f"😊 Generating mood pages...")

        # Group tracks by mood
        moods_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            for mood in p.get("moods", []):
                moods_tracks[mood].append(p)

        # Generate page for each mood
        for mood, mood_tracks in moods_tracks.items():
            filename = self._sanitize_filename(mood.title())
            file_path = self.moods_dir / f"{filename}.md"

            lines = [self._get_audio_player_script(mood_tracks, mood.title(), sources_map)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(moods_tracks)} mood pages")

    def _generate_theme_pages(self, tracks, sources_map):
        """Generate theme index pages with interactive audio player."""
        print(f"🎭 Generating theme pages...")

        # Group tracks by theme
        themes_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            for theme in p.get("themes", []):
                themes_tracks[theme].append(p)

        # Generate page for each theme
        for theme, theme_tracks in themes_tracks.items():
            filename = self._sanitize_filename(theme.title())
            file_path = self.themes_dir / f"{filename}.md"

            lines = [self._get_audio_player_script(theme_tracks, theme.title(), sources_map)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(themes_tracks)} theme pages")

    def _generate_movie_pages(self, tracks, sources_map):
        """Generate movie/album index pages with interactive audio player."""
        print(f"🎬 Generating movie pages...")

        # Group tracks by movie
        movies_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            movie = p.get("movie", "")
            if movie:
                movies_tracks[movie].append(p)

        # Generate page for each movie
        for movie, movie_tracks in movies_tracks.items():
            filename = self._sanitize_filename(movie)
            file_path = self.movies_dir / f"{filename}.md"

            # Use audio player script for movie pages
            lines = [self._get_audio_player_script(movie_tracks, movie, sources_map)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(movies_tracks)} movie pages")

    def _generate_era_pages(self, tracks, sources_map):
        """Generate era index pages with interactive audio player."""
        print(f"📅 Generating era pages...")

        # Group tracks by era (calculate from year if not stored)
        eras_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            era = p.get("era") or calculate_era(p.get("year"))
            if era:
                eras_tracks[era].append(p)

        # Generate page for each era
        for era, era_tracks in eras_tracks.items():
            filename = self._sanitize_filename(era)
            file_path = self.eras_dir / f"{filename}.md"

            # Use audio player script for era pages
            lines = [self._get_audio_player_script(era_tracks, era, sources_map)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(eras_tracks)} era pages")

    def _generate_home_page(self, tracks):
        """Generate home page with stats."""
        print(f"🏠 Generating home page...")

        # Calculate stats
        total_tracks = len(tracks)

        artists = set()
        moods = set()
        themes = set()
        movies = set()
        eras = set()

        for track in tracks:
            p = track.payload
            artists.update(p.get("artists", []))
            moods.update(p.get("moods", []))
            themes.update(p.get("themes", []))
            if p.get("movie"):
                movies.add(p.get("movie"))
            # Calculate era from year if not stored
            era = p.get("era") or calculate_era(p.get("year"))
            if era:
                eras.add(era)

        lines = ["# 🎧 Vectrola Music Library", ""]
        lines.append("A semantic music knowledge graph powered by AI.")
        lines.append("")

        lines.append("## 📊 Library Stats")
        lines.append("")
        lines.append(f"- **Tracks:** {total_tracks}")
        lines.append(f"- **Artists:** {len(artists)}")
        lines.append(f"- **Movies:** {len(movies)}")
        lines.append(f"- **Moods:** {len(moods)}")
        lines.append(f"- **Themes:** {len(themes)}")
        lines.append(f"- **Eras:** {len(eras)}")
        lines.append("")

        lines.append("## 🗂️ Browse")
        lines.append("")
        lines.append("- [[Tracks/|All Tracks]]")
        lines.append("- [[Artists/|All Artists]]")
        lines.append("- [[Moods/|By Mood]]")
        lines.append("- [[Themes/|By Theme]]")
        lines.append("- [[Movies/|By Movie]]")
        lines.append("- [[Eras/|By Era]]")
        lines.append("")

        lines.append("## 🔍 Search Tips")
        lines.append("")
        lines.append("Use Obsidian's search (Cmd+O) to find:")
        lines.append("- Songs by mood: `tag:#melancholic`")
        lines.append("- Songs by artist: search artist name")
        lines.append("- Songs by theme: navigate to theme page")
        lines.append("")

        lines.append("## 🎨 Graph View")
        lines.append("")
        lines.append("Open Graph View (Cmd+G) to visualize:")
        lines.append("- How moods connect tracks")
        lines.append("- Artist collaboration networks")
        lines.append("- Theme clusters")

        home_path = self.output_dir / "README.md"
        home_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ Home page")

    def _build_playlist_json(self, tracks: List[dict]) -> str:
        """
        Build hidden JSON data block for playlist.

        Args:
            tracks: List of track payload dictionaries

        Returns:
            HTML div containing JSON array of track metadata
        """
        playlist = []
        for i, p in enumerate(tracks):
            title = p.get("title", "Unknown")
            artists = p.get("artists", [])
            track_id = p.get("track_id", "")
            spotify_track_id = p.get("spotify_track_id") or p.get("spotify_id")  # NEW
            sources = p.get("sources", {"local": {}, "cloud": {}})

            track_data = {
                "id": f"track-{i}",
                "title": title,
                "artist": ", ".join(artists[:1]) if artists else "Unknown",
                "sources": sources,
                "track_id": track_id,
            }

            # Add spotify_track_id if available (for backward compatibility with plugin)
            if spotify_track_id:
                track_data["spotify_track_id"] = spotify_track_id

            playlist.append(track_data)

        json_str = json.dumps(playlist, ensure_ascii=False)
        return f'<div id="playlist-data" style="display:none">{json_str}</div>'

    def _build_track_list_html(self, tracks: List[dict]) -> str:
        """
        Build HTML track list with play buttons.

        Args:
            tracks: List of track payload dictionaries

        Returns:
            HTML div containing track rows with play buttons
        """
        lines = ['<div class="vectrola-playlist">']

        for i, p in enumerate(tracks):
            title = p.get("title", "Unknown")
            artists = p.get("artists", [])
            track_link = f"[[{self._sanitize_filename(title)}]]"
            artist_str = f" by {', '.join(artists[:1])}" if artists else ""

            lines.append(f'  <div class="track-row" id="track-{i}">')
            lines.append(f'    <span class="track-info">{track_link}{artist_str}</span>')
            lines.append(f'    <button class="play-btn" data-index="{i}">🎵</button>')
            lines.append('  </div>')

        lines.append('</div>')
        return "\n".join(lines)

    def _get_audio_player_script(self, tracks: List[dict], page_title: str = "", sources_map: dict = None) -> str:
        """
        Get vectrola code block for audio player with embedded playlist.

        The Obsidian plugin (vectrola-sync) registers a code block processor
        for ```vectrola blocks that renders the player UI.

        Supports both local file and Google Drive playback (Day 7).
        Priority: GDrive (works cross-device) > Local file (faster, offline)

        Args:
            tracks: List of track payload dictionaries
            page_title: Title to display at top of page
            sources_map: Map of track_id to user's sources (from user_library)

        Returns:
            Vectrola code block as a string (JSON config for the plugin)
        """
        # Build playlist data with sources, duration, and artwork
        playlist = []
        total_duration_ms = 0
        sources_map = sources_map or {}

        for i, p in enumerate(tracks):
            title = p.get("title", "Unknown")
            artists = p.get("artists", [])
            track_link = self._sanitize_filename(title)
            track_id = p.get("track_id", "")
            spotify_track_id = p.get("spotify_track_id") or p.get("spotify_id")  # NEW
            # Duration: prefer duration_ms, fallback to duration_seconds * 1000
            duration_ms = p.get("duration_ms") or int((p.get("duration_seconds") or 0) * 1000)

            # Get sources from sources_map (user_library), not from track payload
            sources = sources_map.get(track_id, {"local": {}, "cloud": {}})

            # Get first mood for gradient fallback
            moods = p.get("moods", [])
            first_mood = moods[0] if moods else None

            track_data = {
                "id": f"track-{i}",
                "title": title,
                "artist": ", ".join(artists[:1]) if artists else "Unknown",
                "album": p.get("album", ""),  # From Qdrant
                "duration": self._format_duration(duration_ms),
                "artwork_url": p.get("album_art_url"),  # From Spotify
                "mood": first_mood,  # For gradient fallback in player
                "sources": sources,
                "track_id": track_id,
                "link": track_link,
            }

            # Add spotify_track_id if available (for backward compatibility with plugin)
            if spotify_track_id:
                track_data["spotify_track_id"] = spotify_track_id

            playlist.append(track_data)
            total_duration_ms += duration_ms or 0

        # Determine artwork for the page
        artwork = self._get_page_artwork(tracks, page_title)

        # Create config object for the plugin
        config = {
            "playlist": playlist,
            "title": page_title,
            "artwork": artwork,
            "total_duration": self._format_duration(total_duration_ms),
            "track_count": len(playlist),
        }

        return f'''```vectrola
{json.dumps(config, indent=2, ensure_ascii=False)}
```'''

    def _get_page_artwork(self, tracks: List[dict], page_title: str) -> dict:
        """
        Get artwork for the page - from first track or generate gradient.

        Args:
            tracks: List of track payload dictionaries
            page_title: Title of the page (for mood-based gradients)

        Returns:
            Dict with artwork info (url and type, or gradient and type)
        """
        # Try to get album art from first track
        for p in tracks[:1]:
            album_art = p.get("album_art_url")
            if album_art:
                return {"url": album_art, "type": "album"}

        # Generate mood-based gradient
        mood_gradients = {
            "melancholic": ["#1a1a2e", "#16213e", "#0f3460"],
            "sad": ["#1a1a2e", "#16213e", "#0f3460"],
            "romantic": ["#e63946", "#f4a261"],
            "love": ["#e63946", "#f4a261"],
            "upbeat": ["#f72585", "#7209b7", "#3a0ca3"],
            "party": ["#f72585", "#7209b7", "#3a0ca3"],
            "dance": ["#f72585", "#7209b7", "#3a0ca3"],
            "chill": ["#90e0ef", "#00b4d8", "#0077b6"],
            "relax": ["#90e0ef", "#00b4d8", "#0077b6"],
            "peaceful": ["#90e0ef", "#00b4d8", "#0077b6"],
        }

        lower = page_title.lower()
        for mood, colors in mood_gradients.items():
            if mood in lower:
                return {"gradient": colors, "type": "gradient"}

        return {"type": "none"}

    def _format_duration(self, ms) -> str:
        """
        Format milliseconds to M:SS or H:MM:SS.

        Args:
            ms: Duration in milliseconds

        Returns:
            Formatted duration string (e.g., "3:45" or "1:02:30")
        """
        if not ms:
            return ""
        seconds = int(ms / 1000)
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize name for filename."""
        # Remove/replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '-')

        # Remove leading/trailing spaces and dots
        name = name.strip('. ')

        # Limit length
        if len(name) > 200:
            name = name[:200]

        return name or "Untitled"
