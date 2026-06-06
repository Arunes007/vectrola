"""Generate Obsidian wiki vault from indexed tracks."""

from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass
from collections import defaultdict

from vectrola.storage.qdrant import get_db


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

    def generate_all(self):
        """Generate complete wiki."""
        print("🎧 Generating Vectrola Wiki...")
        print()

        # Create directories
        self._create_directories()

        # Fetch all tracks
        tracks = self.db.list_all(limit=500)
        print(f"Found {len(tracks)} tracks")
        print()

        # Generate pages
        self._generate_track_pages(tracks)
        self._generate_artist_pages(tracks)
        self._generate_mood_pages(tracks)
        self._generate_theme_pages(tracks)
        self._generate_movie_pages(tracks)
        self._generate_home_page(tracks)

        print()
        print(f"✅ Wiki generated at: {self.output_dir}")
        print(f"   Open in Obsidian to explore!")

    def _create_directories(self):
        """Create wiki directory structure."""
        for dir_path in [
            self.tracks_dir,
            self.artists_dir,
            self.moods_dir,
            self.themes_dir,
            self.movies_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _generate_track_pages(self, tracks):
        """Generate individual track pages."""
        print(f"📝 Generating track pages...")

        for track in tracks:
            p = track.payload

            title = p.get("title", "Unknown")
            artists = p.get("artists", [])

            # Sanitize filename
            filename = self._sanitize_filename(f"{title}")
            file_path = self.tracks_dir / f"{filename}.md"

            # Build page content
            content = self._build_track_page(p)

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

    def _generate_artist_pages(self, tracks):
        """Generate artist index pages."""
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

            lines = [f"# {artist}", ""]
            lines.append(f"**Tracks:** {len(artist_tracks)}")
            lines.append("")
            lines.append("## Songs")
            lines.append("")

            for p in artist_tracks:
                title = p.get("title", "Unknown")
                track_link = f"[[{self._sanitize_filename(title)}]]"
                moods = p.get("moods", [])
                mood_str = f" - *{', '.join(moods[:2])}*" if moods else ""
                lines.append(f"- {track_link}{mood_str}")

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(artists_tracks)} artist pages")

    def _generate_mood_pages(self, tracks):
        """Generate mood index pages."""
        print(f"😊 Generating mood pages...")

        # Group tracks by mood
        moods_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            for mood in p.get("moods", []):
                moods_tracks[mood].append(p)

        # Generate page for each mood
        for mood, mood_tracks in moods_tracks.items():
            filename = self._sanitize_filename(mood)
            file_path = self.moods_dir / f"{filename}.md"

            lines = [f"# {mood.title()}", ""]
            lines.append(f"**Tracks:** {len(mood_tracks)}")
            lines.append("")

            for p in mood_tracks:
                title = p.get("title", "Unknown")
                artists = p.get("artists", [])
                track_link = f"[[{self._sanitize_filename(title)}]]"
                artist_str = f" by {', '.join(artists[:1])}" if artists else ""
                lines.append(f"- {track_link}{artist_str}")

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(moods_tracks)} mood pages")

    def _generate_theme_pages(self, tracks):
        """Generate theme index pages."""
        print(f"🎭 Generating theme pages...")

        # Group tracks by theme
        themes_tracks = defaultdict(list)
        for track in tracks:
            p = track.payload
            for theme in p.get("themes", []):
                themes_tracks[theme].append(p)

        # Generate page for each theme
        for theme, theme_tracks in themes_tracks.items():
            filename = self._sanitize_filename(theme)
            file_path = self.themes_dir / f"{filename}.md"

            lines = [f"# {theme.title()}", ""]
            lines.append(f"**Tracks:** {len(theme_tracks)}")
            lines.append("")

            for p in theme_tracks:
                title = p.get("title", "Unknown")
                artists = p.get("artists", [])
                track_link = f"[[{self._sanitize_filename(title)}]]"
                artist_str = f" by {', '.join(artists[:1])}" if artists else ""
                lines.append(f"- {track_link}{artist_str}")

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(themes_tracks)} theme pages")

    def _generate_movie_pages(self, tracks):
        """Generate movie/album index pages."""
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

            lines = [f"# {movie}", ""]

            # Get year from first track
            year = movie_tracks[0].get("year", "")
            if year:
                lines.append(f"**Year:** {year}")
                lines.append("")

            lines.append(f"**Tracks:** {len(movie_tracks)}")
            lines.append("")

            for p in movie_tracks:
                title = p.get("title", "Unknown")
                artists = p.get("artists", [])
                track_link = f"[[{self._sanitize_filename(title)}]]"
                artist_str = f" - {', '.join(artists[:1])}" if artists else ""
                lines.append(f"- {track_link}{artist_str}")

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(movies_tracks)} movie pages")

    def _generate_home_page(self, tracks):
        """Generate home page with stats."""
        print(f"🏠 Generating home page...")

        # Calculate stats
        total_tracks = len(tracks)

        artists = set()
        moods = set()
        themes = set()
        movies = set()

        for track in tracks:
            p = track.payload
            artists.update(p.get("artists", []))
            moods.update(p.get("moods", []))
            themes.update(p.get("themes", []))
            if p.get("movie"):
                movies.add(p.get("movie"))

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
        lines.append("")

        lines.append("## 🗂️ Browse")
        lines.append("")
        lines.append("- [[Tracks/|All Tracks]]")
        lines.append("- [[Artists/|All Artists]]")
        lines.append("- [[Moods/|By Mood]]")
        lines.append("- [[Themes/|By Theme]]")
        lines.append("- [[Movies/|By Movie]]")
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
