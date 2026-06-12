# Vectrola Sync - Obsidian Plugin

Sync your Vectrola music wiki with Google Drive across devices. This plugin allows you to access your music knowledge graph from any device with Obsidian.

## Features

- **Pull from Drive**: Download latest wiki from Google Drive to your vault
- **Push to Drive**: Upload your vault changes to Google Drive
- **Auto-sync on open**: Automatically pull from Drive when vault opens
- **Periodic sync**: Background sync at configurable intervals
- **OAuth 2.0**: Secure authentication with Google Drive

## Installation

### Manual Installation

1. Download the latest release files:
   - `main.js`
   - `manifest.json`
   - `styles.css`

2. Create the plugin folder:
   ```
   <your-vault>/.obsidian/plugins/vectrola-sync/
   ```

3. Copy the downloaded files into that folder

4. Open Obsidian Settings → Community Plugins → Enable "Vectrola Sync"

### Build from Source

```bash
cd obsidian-vectrola-sync
npm install
npm run build
```

Copy `main.js`, `manifest.json`, and `styles.css` to your vault's plugin folder.

---

## Google OAuth Setup

The plugin requires your own Google OAuth credentials to access Drive.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Create Project"
3. Name it something like "My Vectrola Sync"

### Step 2: Enable Google Drive API

1. In your project, go to **APIs & Services → Library**
2. Search for "Google Drive API"
3. Click **Enable**

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. Select **External** user type
3. Fill in required fields:
   - App name: "Vectrola Sync"
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue**
5. Skip scopes (we request them at auth time)
6. Add yourself as a test user
7. Complete the wizard

### Step 4: Create OAuth Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: "Vectrola Obsidian Plugin"
5. Click **Create**
6. Copy the **Client ID** and **Client Secret**

---

## Configuration

### Step 1: Enter Credentials

1. Open Obsidian Settings → Vectrola Sync
2. Enter your **Client ID** and **Client Secret**
3. Click **Save**

### Step 2: Authenticate

1. Click the **Authenticate** button
2. A browser window opens to Google's sign-in page
3. Sign in with your Google account
4. Click "Allow" to grant Vectrola access
5. Copy the authorization code shown
6. Paste it into the dialog in Obsidian
7. You should see "✅ Authenticated with Google Drive"

### Step 3: Configure Sync Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Drive Folder Path | Where wiki is stored in Drive | `/Vectrola/wiki` |
| Auto-sync on open | Pull from Drive when vault opens | On |
| Sync interval | Auto-sync frequency in minutes (0 = disabled) | 5 |

**Note:** The Drive Folder Path should match what the CLI uses. If you ran `vectrola wiki --sync --drive-path "/My Music/wiki"`, set the same path here.

---

## Usage

### Commands

Access via Command Palette (Cmd/Ctrl + P):

| Command | Description |
|---------|-------------|
| `Vectrola Sync: Pull wiki from Google Drive` | Download latest wiki |
| `Vectrola Sync: Push wiki to Google Drive` | Upload current vault |
| `Vectrola Sync: Authenticate with Google Drive` | Connect to Google account |

### Ribbon Icon

Click the sync icon (🔄) in the left ribbon to pull the latest wiki from Drive.

### Auto-Sync

When enabled, the plugin will:
1. **On vault open**: Pull latest wiki from Drive (3 second delay)
2. **Periodically**: Check for updates at the configured interval

---

## Sync Flow

### CLI → Obsidian (Primary Flow)

```
Device A (has music files)
├── vectrola ingest ~/Music
├── vectrola wiki --sync
└── Uploads to GDrive: /Vectrola/wiki/

        ↓ Google Drive ↓

Device B (Obsidian only)
├── Opens vault
├── Plugin auto-pulls
└── Wiki appears in Obsidian
```

### Obsidian → CLI (Push Flow)

If you make edits in Obsidian (custom pages, notes):

```
Device B (Obsidian)
├── Create/edit files
├── Plugin pushes to GDrive
└── Changes saved to Drive

        ↓ Google Drive ↓

Device A
├── Manual download from Drive
└── Or: Obsidian plugin pulls
```

**Note:** The CLI (`vectrola wiki --sync`) always overwrites the wiki. Your custom pages in Obsidian are preserved if they're outside the auto-generated folders (Tracks/, Artists/, etc.).

---

## Conflict Resolution

The plugin uses **last-write-wins** based on modification time:

- **Pull**: Remote file is newer → Download and overwrite local
- **Pull**: Local file is newer → Skip (keep local)
- **Push**: Upload all local files, overwriting remote

For best results, use a single "source of truth" device for wiki generation, and treat other devices as read-only browsers.

---

## Troubleshooting

### "Not authenticated" error

1. Go to Settings → Vectrola Sync
2. Click "Authenticate"
3. Follow the OAuth flow

### "Invalid credentials" error

1. Verify your Client ID and Client Secret are correct
2. Make sure you created a **Desktop app** OAuth client (not Web app)
3. Try creating new credentials

### Files not syncing

1. Check that Drive Folder Path matches the CLI path
2. Verify you're authenticated (Settings shows "✅ Authenticated")
3. Try manual Pull to see error messages

### Token expired

The plugin auto-refreshes tokens. If issues persist:
1. Go to Settings → Vectrola Sync
2. Click "Authenticate" to re-authenticate

### "App not verified" warning

This is normal for personal OAuth credentials. Click:
1. **Advanced**
2. **Go to [App Name] (unsafe)**

To avoid this, add yourself as a test user in Google Cloud Console.

### Plugin not loading

1. Check that `main.js`, `manifest.json`, and `styles.css` are in the plugin folder
2. Restart Obsidian
3. Make sure the plugin is enabled in Settings → Community Plugins

---

## Privacy & Security

- **drive.file scope**: Plugin can only access files it creates - not your entire Drive
- **Local tokens**: OAuth tokens stored locally via Obsidian's secure storage
- **No server**: Authentication happens entirely between you and Google
- **Your wiki, your Drive**: Files stored in your personal Google Drive (counts toward your 15GB quota)

---

## Compatibility

- **Obsidian**: 1.0.0 or later
- **Platform**: Desktop only (Windows, macOS, Linux)
- **Mobile**: Not supported (OAuth flow requires desktop browser)

---

## Related Documentation

- [Wiki Generation](wiki.md) - How the wiki is generated
- [Google Drive Integration](gdrive.md) - CLI-side GDrive setup
- [Multi-Tenancy](multitenancy.md) - User library and playback sources
