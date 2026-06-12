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

    Day 7 additions:
    - GDrive playback support (streams from Google Drive when available)
    - Falls back to local file playback
    - Uses UserLibrary for track source mappings
    """

    def __init__(self, output_dir: Path = Path("./wiki")):
        """
        Initialize wiki generator.

        Args:
            output_dir: Directory to write wiki pages
        """
        self.output_dir = Path(output_dir)
        self.db = get_db()

        # User library for GDrive mappings (Day 7)
        self._library = None

        # Subdirectories
        self.tracks_dir = self.output_dir / "Tracks"
        self.artists_dir = self.output_dir / "Artists"
        self.moods_dir = self.output_dir / "Moods"
        self.themes_dir = self.output_dir / "Themes"
        self.movies_dir = self.output_dir / "Movies"
        self.eras_dir = self.output_dir / "Eras"

    @property
    def library(self):
        """Lazy load user library."""
        if self._library is None:
            try:
                from vectrola.services.library import UserLibrary
                self._library = UserLibrary()
            except ImportError:
                self._library = None
        return self._library

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

        # Generate pages
        self._generate_track_pages(tracks)
        self._generate_artist_pages(tracks)
        self._generate_mood_pages(tracks)
        self._generate_theme_pages(tracks)
        self._generate_movie_pages(tracks)
        self._generate_era_pages(tracks)
        self._generate_home_page(tracks)

        # Write owner file for security tracking
        owner_file = self.output_dir / ".wiki_owner"
        owner_file.write_text(user_id)

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
            self.eras_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _generate_track_pages(self, tracks):
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
            content = self._get_audio_player_script([p], title)
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

    def _generate_artist_pages(self, tracks):
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
            lines = [self._get_audio_player_script(artist_tracks, artist)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(artists_tracks)} artist pages")

    def _generate_mood_pages(self, tracks):
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

            lines = [self._get_audio_player_script(mood_tracks, mood.title())]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(moods_tracks)} mood pages")

    def _generate_theme_pages(self, tracks):
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

            lines = [self._get_audio_player_script(theme_tracks, theme.title())]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(themes_tracks)} theme pages")

    def _generate_movie_pages(self, tracks):
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
            lines = [self._get_audio_player_script(movie_tracks, movie)]

            file_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"   ✓ {len(movies_tracks)} movie pages")

    def _generate_era_pages(self, tracks):
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
            lines = [self._get_audio_player_script(era_tracks, era)]

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
            file_path = p.get("file_path", "")
            track_id = p.get("track_id", "")

            # Get GDrive ID from library if available (Day 7)
            gdrive_id = None
            if self.library and track_id:
                gdrive_id = self.library.get_gdrive_id(track_id)

            playlist.append({
                "id": f"track-{i}",
                "title": title,
                "artist": ", ".join(artists[:1]) if artists else "Unknown",
                "path": file_path,
                "gdrive_id": gdrive_id,  # Day 7
                "track_id": track_id,    # Day 7
            })

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

    def _get_audio_player_script(self, tracks: List[dict], page_title: str = "") -> str:
        """
        Get DataviewJS code block for audio player with embedded playlist.

        Supports both local file and Google Drive playback (Day 7).
        Priority: GDrive (works cross-device) > Local file (faster, offline)

        Args:
            tracks: List of track payload dictionaries
            page_title: Title to display at top of page

        Returns:
            Complete DataviewJS code block as a string
        """
        # Build playlist data with GDrive IDs
        playlist = []
        for i, p in enumerate(tracks):
            title = p.get("title", "Unknown")
            artists = p.get("artists", [])
            file_path = p.get("file_path", "")
            track_link = self._sanitize_filename(title)
            track_id = p.get("track_id", "")

            # Get GDrive ID from library if available (Day 7)
            gdrive_id = None
            if self.library and track_id:
                gdrive_id = self.library.get_gdrive_id(track_id)

            # Also check if it was stored in payload directly
            if not gdrive_id:
                gdrive_id = p.get("gdrive_file_id")

            playlist.append({
                "id": f"track-{i}",
                "title": title,
                "artist": ", ".join(artists[:1]) if artists else "Unknown",
                "path": file_path,
                "gdrive_id": gdrive_id,  # Day 7
                "track_id": track_id,    # Day 7
                "link": track_link,
            })

        playlist_json = json.dumps(playlist, ensure_ascii=False)
        # Escape the title for JavaScript string
        escaped_title = page_title.replace("'", "\\'").replace('"', '\\"')
        # Create a unique player ID based on page title
        player_id = page_title.lower().replace(" ", "-").replace("'", "").replace('"', "")

        script = f'''```dataviewjs
// Vectrola Audio Player - Global Persistent Player with GDrive Support
(function() {{
    const pageTitle = "{escaped_title}";
    const playlist = {playlist_json};

    if (!playlist.length) return;

    // Initialize or get global player state
    if (!window.vectrolaPlayer) {{
        window.vectrolaPlayer = {{
            audio: new Audio(),
            currentTrack: null,
            currentIndex: -1,
            isPlaying: false,
            shuffleMode: false,
            shuffleHistory: [],
            playlist: [],
            playlistSource: null,
            ui: null
        }};
        window.vectrolaPlayer.audio.preload = 'none';
    }}

    const player = window.vectrolaPlayer;

    // Format time helper
    function formatTime(seconds) {{
        if (isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${{mins}}:${{secs.toString().padStart(2, '0')}}`;
    }}

    // Define all player control functions on the global player object
    // These are defined early so event listeners can reference them
    player.playTrack = async function(index) {{
        if (index < 0 || index >= player.playlist.length) return;

        const track = player.playlist[index];

        try {{
            // Clean up previous blob URL if any
            if (player.audio.src && player.audio.src.startsWith('blob:')) {{
                URL.revokeObjectURL(player.audio.src);
            }}

            // Day 7: Try GDrive first, then fall back to local file
            if (track.gdrive_id) {{
                // Stream from Google Drive using stored OAuth token
                console.log('Playing from GDrive:', track.gdrive_id);

                try {{
                    // Read the OAuth token from ~/.config/vectrola/gdrive_token.json
                    const fs = require('fs');
                    const path = require('path');
                    const os = require('os');

                    const tokenPath = path.join(os.homedir(), '.config', 'vectrola', 'gdrive_token.json');
                    const tokenData = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));
                    const accessToken = tokenData.token;

                    // Fetch from Google Drive API with auth
                    const response = await fetch(
                        `https://www.googleapis.com/drive/v3/files/${{track.gdrive_id}}?alt=media`,
                        {{
                            headers: {{
                                'Authorization': `Bearer ${{accessToken}}`
                            }}
                        }}
                    );

                    if (!response.ok) {{
                        throw new Error(`GDrive fetch failed: ${{response.status}}`);
                    }}

                    const arrayBuffer = await response.arrayBuffer();
                    const blob = new Blob([arrayBuffer], {{ type: 'audio/mpeg' }});
                    const blobUrl = URL.createObjectURL(blob);
                    player.audio.src = blobUrl;

                }} catch (gdriveError) {{
                    console.error('GDrive playback failed, trying local:', gdriveError);
                    // Fall back to local file if GDrive fails
                    if (track.path) {{
                        const fs = require('fs');
                        const buffer = fs.readFileSync(track.path);
                        const blob = new Blob([buffer], {{ type: 'audio/mpeg' }});
                        player.audio.src = URL.createObjectURL(blob);
                    }} else {{
                        throw gdriveError;
                    }}
                }}
            }} else if (track.path) {{
                // Fallback to local file (faster, works offline)
                console.log('Playing from local:', track.path);
                try {{
                    const fs = require('fs');
                    const buffer = fs.readFileSync(track.path);
                    const blob = new Blob([buffer], {{ type: 'audio/mpeg' }});
                    const blobUrl = URL.createObjectURL(blob);
                    player.audio.src = blobUrl;
                }} catch (e) {{
                    console.error('Local file not found:', track.path, e);
                    // Try next track
                    if (index + 1 < player.playlist.length) {{
                        player.playTrack(index + 1);
                    }}
                    return;
                }}
            }} else {{
                console.warn('No playback source for track:', track.title);
                return;
            }}

            player.currentIndex = index;
            player.currentTrack = track;
            await player.audio.play();
            player.isPlaying = true;

            // Update UI
            const titleEl = document.getElementById('vectrola-track-title');
            const artistEl = document.getElementById('vectrola-track-artist');
            const ppBtn = document.getElementById('vectrola-playpause-btn');
            if (titleEl) titleEl.textContent = track.title;
            if (artistEl) artistEl.textContent = track.artist;
            if (ppBtn) ppBtn.textContent = '⏸';

            // Update all registered highlight updaters (for all open pages)
            if (window.vectrolaHighlightUpdaters) {{
                window.vectrolaHighlightUpdaters.forEach(fn => fn());
            }}

            if (player.shuffleMode && !player.shuffleHistory.includes(index)) {{
                player.shuffleHistory.push(index);
            }}
        }} catch (e) {{
            console.error('Playback failed:', e);
        }}
    }};

    player.togglePlayPause = function() {{
        if (player.currentIndex === -1) {{
            // If nothing playing, use this page's playlist
            player.playlist = playlist;
            player.playlistSource = pageTitle;
            player.playTrack(0);
            return;
        }}

        const ppBtn = document.getElementById('vectrola-playpause-btn');
        if (player.isPlaying) {{
            player.audio.pause();
            player.isPlaying = false;
            if (ppBtn) ppBtn.textContent = '▶';
        }} else {{
            player.audio.play().catch(e => console.error('Playback failed:', e));
            player.isPlaying = true;
            if (ppBtn) ppBtn.textContent = '⏸';
        }}
    }};

    player.nextTrack = function() {{
        if (!player.playlist.length) return;

        if (player.shuffleMode) {{
            const unplayed = player.playlist.map((_, i) => i).filter(i => !player.shuffleHistory.includes(i));
            if (unplayed.length === 0) {{
                player.shuffleHistory = [];
                player.nextTrack();
                return;
            }}
            const randomIndex = unplayed[Math.floor(Math.random() * unplayed.length)];
            player.playTrack(randomIndex);
        }} else {{
            player.playTrack((player.currentIndex + 1) % player.playlist.length);
        }}
    }};

    player.prevTrack = function() {{
        if (!player.playlist.length) return;

        if (player.shuffleMode && player.shuffleHistory.length > 1) {{
            player.shuffleHistory.pop();
            player.playTrack(player.shuffleHistory[player.shuffleHistory.length - 1]);
        }} else {{
            player.playTrack(player.currentIndex <= 0 ? player.playlist.length - 1 : player.currentIndex - 1);
        }}
    }};

    player.toggleShuffle = function() {{
        player.shuffleMode = !player.shuffleMode;
        const sBtn = document.getElementById('vectrola-shuffle-btn');
        if (sBtn) sBtn.style.color = player.shuffleMode ? 'var(--interactive-accent)' : '';
        if (!player.shuffleMode) {{
            player.shuffleHistory = [];
        }} else if (player.currentIndex >= 0) {{
            player.shuffleHistory = [player.currentIndex];
        }}
    }};

    // Local wrapper for playTrack that sets this page's playlist
    function playTrack(index) {{
        player.playlist = playlist;
        player.playlistSource = pageTitle;
        player.playTrack(index);
    }}

    // Show track count only (Obsidian shows the title from filename)
    const trackCount = dv.container.createEl('p', {{ text: `${{playlist.length}} Tracks` }});
    trackCount.style.cssText = 'font-weight: bold; margin-bottom: 16px; color: var(--text-muted);';

    // Build track list
    const trackListEl = dv.container.createEl('div');
    trackListEl.style.cssText = 'margin: 16px 0;';

    // Update track highlight for this page's list
    function updateLocalHighlight() {{
        trackListEl.querySelectorAll('div[data-index]').forEach((row, i) => {{
            const track = playlist[i];
            const isCurrentTrack = player.currentTrack && player.currentTrack.path === track.path;
            row.classList.toggle('playing', isCurrentTrack);
            row.style.background = isCurrentTrack ? 'var(--interactive-accent)' : 'var(--background-secondary)';
            row.style.color = isCurrentTrack ? 'var(--text-on-accent)' : '';
        }});
    }}

    playlist.forEach((track, i) => {{
        const row = trackListEl.createEl('div');
        row.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; margin: 6px 0; border-radius: 8px; background: var(--background-secondary); cursor: pointer; transition: background 0.2s;';
        row.dataset.index = i;

        // Hover effect
        row.onmouseenter = () => {{ if (!row.classList.contains('playing')) row.style.background = 'var(--background-modifier-hover)'; }};
        row.onmouseleave = () => {{ if (!row.classList.contains('playing')) row.style.background = 'var(--background-secondary)'; }};

        const info = row.createEl('div');
        info.style.cssText = 'flex: 1; min-width: 0;';

        const titleEl = info.createEl('div', {{ text: track.title }});
        titleEl.style.cssText = 'font-weight: 500;';

        // Day 7: Show source indicator (GDrive cloud icon or local icon)
        const sourceIndicator = track.gdrive_id ? '☁️' : (track.path ? '💾' : '❌');
        const artistEl = info.createEl('div', {{ text: `${{track.artist}} ${{sourceIndicator}}` }});
        artistEl.style.cssText = 'font-size: 0.85em; color: var(--text-muted);';

        const btnContainer = row.createEl('div');
        btnContainer.style.cssText = 'display: flex; gap: 4px;';

        const infoBtn = btnContainer.createEl('button', {{ text: 'ℹ️' }});
        infoBtn.style.cssText = 'background: none; border: none; font-size: 1.1em; cursor: pointer; padding: 6px 8px; border-radius: 6px;';
        infoBtn.title = 'Track details';
        infoBtn.addEventListener('click', (e) => {{
            e.stopPropagation();
            app.workspace.openLinkText(track.link, '', false);
        }});

        const playBtn = btnContainer.createEl('button', {{ text: '🎵' }});
        playBtn.style.cssText = 'background: none; border: none; font-size: 1.3em; cursor: pointer; padding: 6px 10px; border-radius: 6px;';

        row.addEventListener('click', () => {{
            // Update global playlist to this page's playlist
            player.playlist = playlist;
            player.playlistSource = pageTitle;
            player.shuffleHistory = [];
            playTrack(i);
        }});
    }});

    // Check if player bar already exists
    let playerBar = document.getElementById('vectrola-global-player');
    let trackTitleEl, trackArtistEl, playPauseBtn, shuffleBtn, progressFill, currentTimeEl, totalTimeEl;

    if (!playerBar) {{
        // Create player bar with inline styles
        playerBar = document.createElement('div');
        playerBar.id = 'vectrola-global-player';
        playerBar.style.cssText = 'position: fixed; bottom: 0; left: 0; right: 0; background: var(--background-secondary); border-top: 1px solid var(--background-modifier-border); padding: 12px 20px; display: flex; align-items: center; gap: 16px; z-index: 1000; box-shadow: 0 -2px 10px rgba(0,0,0,0.1);';

        // Track display
        const trackDisplay = document.createElement('div');
        trackDisplay.style.cssText = 'flex: 1; min-width: 0;';

        trackTitleEl = document.createElement('div');
        trackTitleEl.id = 'vectrola-track-title';
        trackTitleEl.style.cssText = 'font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;';
        trackTitleEl.textContent = player.currentTrack ? player.currentTrack.title : 'Select a track to play';

        trackArtistEl = document.createElement('div');
        trackArtistEl.id = 'vectrola-track-artist';
        trackArtistEl.style.cssText = 'font-size: 0.85em; color: var(--text-muted);';
        trackArtistEl.textContent = player.currentTrack ? player.currentTrack.artist : '';

        trackDisplay.appendChild(trackTitleEl);
        trackDisplay.appendChild(trackArtistEl);

        // Controls
        const controls = document.createElement('div');
        controls.style.cssText = 'display: flex; gap: 8px;';

        const btnStyle = 'background: none; border: none; font-size: 1.5em; cursor: pointer; padding: 8px; border-radius: 50%; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center;';

        shuffleBtn = document.createElement('button');
        shuffleBtn.id = 'vectrola-shuffle-btn';
        shuffleBtn.style.cssText = btnStyle;
        shuffleBtn.textContent = '🔀';
        shuffleBtn.title = 'Shuffle';
        if (player.shuffleMode) shuffleBtn.style.color = 'var(--interactive-accent)';

        const prevBtn = document.createElement('button');
        prevBtn.style.cssText = btnStyle;
        prevBtn.textContent = '⏮';
        prevBtn.title = 'Previous';

        playPauseBtn = document.createElement('button');
        playPauseBtn.id = 'vectrola-playpause-btn';
        playPauseBtn.style.cssText = btnStyle;
        playPauseBtn.textContent = player.isPlaying ? '⏸' : '▶';
        playPauseBtn.title = 'Play';

        const nextBtn = document.createElement('button');
        nextBtn.style.cssText = btnStyle;
        nextBtn.textContent = '⏭';
        nextBtn.title = 'Next';

        controls.appendChild(shuffleBtn);
        controls.appendChild(prevBtn);
        controls.appendChild(playPauseBtn);
        controls.appendChild(nextBtn);

        // Progress container
        const progressContainer = document.createElement('div');
        progressContainer.style.cssText = 'flex: 2; display: flex; align-items: center; gap: 8px;';

        currentTimeEl = document.createElement('span');
        currentTimeEl.id = 'vectrola-current-time';
        currentTimeEl.style.cssText = 'font-size: 0.8em; color: var(--text-muted); min-width: 40px;';
        currentTimeEl.textContent = '0:00';

        const progressBarContainer = document.createElement('div');
        progressBarContainer.id = 'vectrola-progress-bar';
        progressBarContainer.style.cssText = 'flex: 1; height: 6px; background: var(--background-modifier-border); border-radius: 3px; cursor: pointer; position: relative;';

        progressFill = document.createElement('div');
        progressFill.id = 'vectrola-progress-fill';
        progressFill.style.cssText = 'height: 100%; background: var(--interactive-accent); border-radius: 3px; width: 0%; transition: width 0.1s linear;';
        progressBarContainer.appendChild(progressFill);

        totalTimeEl = document.createElement('span');
        totalTimeEl.id = 'vectrola-total-time';
        totalTimeEl.style.cssText = 'font-size: 0.8em; color: var(--text-muted); min-width: 40px;';
        totalTimeEl.textContent = '0:00';

        progressContainer.appendChild(currentTimeEl);
        progressContainer.appendChild(progressBarContainer);
        progressContainer.appendChild(totalTimeEl);

        // Assemble player bar
        playerBar.appendChild(trackDisplay);
        playerBar.appendChild(controls);
        playerBar.appendChild(progressContainer);

        // Append to body for fixed positioning
        document.body.appendChild(playerBar);

        // Event listeners for controls - call through player object for latest functions
        playPauseBtn.addEventListener('click', () => player.togglePlayPause());
        nextBtn.addEventListener('click', () => player.nextTrack());
        prevBtn.addEventListener('click', () => player.prevTrack());
        shuffleBtn.addEventListener('click', () => player.toggleShuffle());

        progressBarContainer.addEventListener('click', (e) => {{
            if (player.audio.duration) {{
                const rect = progressBarContainer.getBoundingClientRect();
                const pos = (e.clientX - rect.left) / rect.width;
                player.audio.currentTime = pos * player.audio.duration;
            }}
        }});

        // Audio event listeners (only set up once)
        player.audio.addEventListener('timeupdate', () => {{
            const pf = document.getElementById('vectrola-progress-fill');
            const ct = document.getElementById('vectrola-current-time');
            if (player.audio.duration && pf && ct) {{
                pf.style.width = (player.audio.currentTime / player.audio.duration) * 100 + '%';
                ct.textContent = formatTime(player.audio.currentTime);
            }}
        }});

        player.audio.addEventListener('loadedmetadata', () => {{
            const tt = document.getElementById('vectrola-total-time');
            if (tt) tt.textContent = formatTime(player.audio.duration);
        }});

        player.audio.addEventListener('ended', () => player.nextTrack());

        // Store UI references
        player.ui = {{ playerBar, trackTitleEl, trackArtistEl, playPauseBtn, shuffleBtn, progressFill, currentTimeEl, totalTimeEl }};
    }} else {{
        // Get existing UI elements
        trackTitleEl = document.getElementById('vectrola-track-title');
        trackArtistEl = document.getElementById('vectrola-track-artist');
        playPauseBtn = document.getElementById('vectrola-playpause-btn');
        shuffleBtn = document.getElementById('vectrola-shuffle-btn');
        progressFill = document.getElementById('vectrola-progress-fill');
        currentTimeEl = document.getElementById('vectrola-current-time');
        totalTimeEl = document.getElementById('vectrola-total-time');
    }}

    // Update highlight when page loads (in case current track is in this playlist)
    updateLocalHighlight();

    // Register this page's highlight updater globally so playTrack can call it
    if (!window.vectrolaHighlightUpdaters) {{
        window.vectrolaHighlightUpdaters = new Set();
    }}
    window.vectrolaHighlightUpdaters.add(updateLocalHighlight);

    // Cleanup when page unloads (Obsidian re-renders)
    const observer = new MutationObserver(() => {{
        if (!document.contains(trackListEl)) {{
            window.vectrolaHighlightUpdaters.delete(updateLocalHighlight);
            observer.disconnect();
        }}
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
}})();
```'''
        return script

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
