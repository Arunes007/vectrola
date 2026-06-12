# Obsidian Wiki Generation

Vectrola generates an Obsidian-compatible wiki vault from your indexed music library. The wiki creates a visual knowledge graph connecting tracks, artists, moods, themes, and movies.

## What Gets Generated

```
wiki/
├── README.md              # Home page with stats
├── Tracks/
│   ├── Tum_Hi_Ho.md
│   ├── Ae_Dil_Hai_Mushkil.md
│   └── ...
├── Artists/
│   ├── Arijit_Singh.md
│   ├── Shreya_Ghoshal.md
│   └── ...
├── Moods/
│   ├── melancholic.md
│   ├── romantic.md
│   └── ...
├── Themes/
│   ├── love.md
│   ├── longing.md
│   └── ...
└── Movies/
    ├── Aashiqui_2.md
    ├── Ae_Dil_Hai_Mushkil.md
    └── ...
```

## Generate Wiki

```bash
vectrola wiki
```

This creates a `./wiki/` directory with markdown files.

## View in Obsidian

1. **Download Obsidian**: https://obsidian.md
2. **Open as Vault**: File → Open folder as vault → Select `wiki/` directory
3. **Enable Graph View**: Click graph icon or press `Cmd+G` (Mac) / `Ctrl+G` (Windows)

## Features

### Wikilinks

Pages are connected with `[[wikilinks]]`:

```markdown
# Tum Hi Ho

**Artists:** [[Arijit Singh]], [[Mithoon]]
**Movie:** [[Aashiqui 2]]
**Moods:** [[melancholic]], [[romantic]]
**Themes:** [[love]], [[longing]]
```

Clicking a wikilink navigates to that page.

### Graph View

Obsidian's graph view visualizes connections:

- **Nodes** = Pages (tracks, artists, moods, themes)
- **Edges** = Wikilinks between pages

**Clusters emerge naturally:**
- Romantic songs cluster together (via mood/theme)
- Arijit Singh songs form a network
- Movie soundtracks group by film

### Search

Obsidian provides powerful search:

```
# Search by mood tag
tag:#melancholic

# Search by artist
Arijit Singh

# Search in lyrics
path:Tracks/ "dil"
```

## Page Structure

### Track Pages

```markdown
---
artists: ["Arijit Singh"]
movie: "Aashiqui 2"
year: 2013
tags: [melancholic, romantic]
---

# Tum Hi Ho

**Artists:** [[Arijit Singh]], [[Mithoon]]
**Movie:** [[Aashiqui 2]]

## Credits
- **Music:** Mithoon
- **Lyrics:** Mithoon
- **Year:** 2013

## AI Semantic Analysis

> A deeply melancholic love song expressing complete devotion
> and the inability to exist without the beloved.

**Moods:** [[melancholic]], [[romantic]], [[introspective]]

**Themes:** [[love]], [[longing]], [[devotion]]

## Lyrics

```
Baatein teri yaadein teri
Sab seh lunga kyun ki
Tum hi ho...
```
```

### Artist Pages

Lists all tracks by an artist:

```markdown
# Arijit Singh

**Tracks:** 15

## Songs

- [[Tum Hi Ho]] - *melancholic, romantic*
- [[Ae Dil Hai Mushkil]] - *introspective, hopeful*
- [[Channa Mereya]] - *heartbroken, nostalgic*
...
```

### Mood Pages

Lists all tracks with a mood:

```markdown
# Melancholic

**Tracks:** 32

- [[Tum Hi Ho]] by Arijit Singh
- [[Bekhayali]] by Sachet Tandon
- [[Agar Tum Saath Ho]] by Alka Yagnik
...
```

### Theme Pages

Groups tracks by lyrical theme:

```markdown
# Love

**Tracks:** 45

- [[Tum Hi Ho]] by Arijit Singh
- [[Raabta]] by Arijit Singh
- [[Pehla Nasha]] by Udit Narayan
...
```

### Movie Pages

Complete soundtracks:

```markdown
# Aashiqui 2

**Year:** 2013
**Tracks:** 12

- [[Tum Hi Ho]] - Arijit Singh
- [[Sunn Raha Hai]] - Ankit Tiwari
- [[Bhula Dena]] - Arijit Singh
...
```

## Use Cases

### 1. Discover Similar Songs

Open a track → See connected moods/themes → Explore other tracks with same mood

### 2. Artist Deep Dive

Open artist page → See all their songs → Find their most common moods

### 3. Build Playlists

Search by mood → Collect tracks → Export to music player

### 4. Explore Bollywood Cinema

Browse Movies → See complete soundtracks → Discover era patterns

### 5. Lyrical Analysis

Search themes → Find songs about specific topics → Compare narratives

## Obsidian Plugins (Optional)

Enhance your wiki with plugins:

- **Dataview**: Query tracks (e.g., "all melancholic songs from 2013")
- **Graph Analysis**: Analyze mood/theme clusters
- **Daily Notes**: Track listening history
- **Kanban**: Organize playlists

## Regenerate Wiki

The wiki is static - changes to Qdrant won't auto-update.

To regenerate after ingesting new tracks:

```bash
vectrola wiki --output ./wiki
```

This **overwrites** existing pages. Obsidian will auto-reload.

## Customization

### Add Custom Pages

Create new markdown files in `wiki/`:

```markdown
# My Favorite Songs

- [[Tum Hi Ho]]
- [[Ae Dil Hai Mushkil]]
```

These won't be overwritten by regeneration.

### Modify Templates

Edit `vectrola/storage/wiki.py` to customize:
- Page layout
- Frontmatter fields
- Wikilink format

## Tips

1. **Use Tags**: Frontmatter tags enable `tag:#mood` search
2. **Graph Filters**: Filter graph by tags to see mood clusters
3. **Local Graph**: Right-click track → Open local graph (shows immediate connections)
4. **Link Hover**: Hover over wikilink to preview page
5. **Backlinks**: See which pages link to current page (right sidebar)

## Limitations

- **Manual Sync**: Wiki doesn't auto-update when Qdrant changes
- **Static Content**: No dynamic queries (use Dataview plugin for that)
- **Desktop Only for Playback**: Audio player uses `file://` protocol, works only on desktop Obsidian

## Audio Player (Day 6)

Mood and theme pages now include an **interactive audio player**! Click 🎵 to play tracks directly from your local music library.

### Requirements

1. **Dataview Plugin**: Install and enable the Dataview community plugin
2. **Enable JavaScript**: In Dataview settings, turn on "Enable JavaScript Queries"
3. **Desktop Obsidian**: Audio playback requires desktop app (not mobile)

### Features

- **Track Play Buttons**: Click 🎵 next to any track to play
- **Player Bar**: Fixed bottom bar with:
  - ▶/⏸ Play/Pause
  - ⏮ Previous / ⏭ Next
  - 🔀 Shuffle mode
  - Progress bar with seeking
  - Current/total time display
- **Track Highlighting**: Currently playing track is highlighted
- **Auto-advance**: Plays next track when current ends
- **Shuffle Memory**: Remembers history in shuffle mode for "previous" navigation

### How It Works

The wiki generator embeds:
1. Hidden JSON playlist data
2. HTML track list with play buttons
3. DataviewJS script for the player

The player uses HTML5 Audio API with `file://` protocol to play local MP3s.

### Troubleshooting

**"No playback / silence"**
- Verify Dataview plugin is installed and JavaScript queries enabled
- Check that file paths in Qdrant are correct
- Use desktop Obsidian (mobile doesn't support `file://`)

**"Player bar doesn't appear"**
- Enable JavaScript queries in Dataview settings
- Check browser console for errors (press Cmd+Option+I)

**"Tracks won't play"**
- Ensure MP3 files exist at the stored paths
- Some browsers block `file://` access; Obsidian's Electron shell allows it

## Example Workflows

### Find Mood Matches

1. Open a track you like
2. Note its moods (e.g., melancholic, romantic)
3. Click mood wikilink
4. Browse other tracks with same mood

### Explore Artist Evolution

1. Open artist page
2. Sort tracks by year (edit page, add years)
3. See mood/theme changes over time

### Build Themed Playlist

1. Search theme: `path:Themes/ love`
2. Open love theme page
3. Collect tracks
4. Copy to playlist

## Privacy

The wiki is **local-only** by default - markdown files on your disk. Use `--sync` to upload to your Google Drive for cross-device access.

---

## Cross-Device Sync

Sync your wiki to Google Drive so it's available on all your devices. The wiki is uploaded to your personal Drive using the secure `drive.file` scope (Vectrola can only access files it creates).

### Prerequisites

1. **Google Drive authentication**: Run `vectrola gdrive auth` first
2. **Re-authenticate if needed**: If you previously authenticated with read-only scope, you must re-authenticate:
   ```bash
   vectrola gdrive auth --logout
   vectrola gdrive auth
   ```

### Generate & Sync

```bash
# Generate wiki locally AND upload to Google Drive
vectrola wiki --sync

# Custom Drive folder location
vectrola wiki --sync --drive-path "/My Music/wiki"
```

**Default location:** `/Vectrola/wiki/` in your Google Drive root

### What Gets Synced

```
My Drive/
└── Vectrola/
    └── wiki/
        ├── README.md           # Home page
        ├── Tracks/             # Individual songs
        ├── Artists/            # Artist indexes
        ├── Moods/              # Mood collections
        ├── Themes/             # Theme collections
        ├── Movies/             # Soundtrack collections
        └── Eras/               # Decade-based collections
```

### Sync Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Device A (has music files)                                 │
│                                                             │
│  vectrola ingest ~/Music     # Index your library           │
│  vectrola wiki --sync        # Generate & upload to GDrive  │
│                                                             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  Google Drive   │
              │  /Vectrola/wiki │
              └────────┬────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌───────────────────┐      ┌───────────────────┐
│  Device B         │      │  Device C         │
│  (Obsidian)       │      │  (Obsidian)       │
│                   │      │                   │
│  Pull via plugin  │      │  Pull via plugin  │
│  Browse & play    │      │  Browse & play    │
└───────────────────┘      └───────────────────┘
```

### Obsidian Plugin

For the best cross-device experience, install the **Vectrola Sync** Obsidian plugin:

- **Auto-pull**: Downloads wiki from Drive when vault opens
- **Auto-sync**: Periodic background sync (configurable)
- **Push changes**: Upload edits back to Drive

See [Obsidian Plugin Documentation](obsidian-plugin.md) for setup instructions.

### Manual Sync (Without Plugin)

If you prefer not to use the plugin:

1. Access Google Drive in your browser
2. Navigate to `/Vectrola/wiki/`
3. Download the folder
4. Open in Obsidian

**Note:** This requires manual re-download after each `vectrola wiki --sync`.
