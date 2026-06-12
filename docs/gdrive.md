# Google Drive Integration

Vectrola can ingest music directly from your Google Drive. This guide covers authentication, folder permissions, and all available commands.

## Quick Start

```bash
# 1. Install Google Drive support
pip install vectrola[gdrive]

# 2. Authenticate (opens browser)
vectrola gdrive auth

# 3. (Optional) Select folders to restrict access
vectrola gdrive select

# 4. Browse your Drive
vectrola gdrive list /

# 5. Ingest music
vectrola gdrive ingest "/Music/Bollywood"
```

## Authentication

### Browser Flow (Default)

When you run `vectrola gdrive auth`:

1. A browser window opens to Google's sign-in page
2. Sign in with your Google account
3. Click "Allow" to grant Vectrola read-only access to your Drive
4. The browser shows "Authentication successful!" - you can close it
5. Your credentials are saved locally to `~/.config/vectrola/gdrive_token.json`

### Console Fallback (Headless/Proxy)

If the browser flow fails (corporate proxy, headless server, SSH session):

1. Vectrola prints an authorization URL
2. Open the URL manually in any browser (even on another device)
3. Sign in and authorize Vectrola
4. Copy the authorization code shown
5. Paste it into the terminal

```bash
$ vectrola gdrive auth
Opening browser for Google Drive authentication...
(If browser doesn't open, see the URL below)

[!] Browser authentication failed: ...
Switching to manual verification...

1. Open this URL in your browser:

   https://accounts.google.com/o/oauth2/auth?...

2. Sign in and authorize Vectrola
3. Copy the authorization code shown

Enter authorization code: 4/0AY0e...
```

### Logout

```bash
vectrola gdrive auth --logout
```

## Folder Permissions

By default, Vectrola can access your entire Google Drive (read-only). You can restrict access to specific folders for additional security.

### Using Google Picker (Recommended)

The `select` command opens Google's native folder picker UI:

```bash
vectrola gdrive select
```

This opens a browser window where you can visually select folders. Selected folders replace any previous restrictions.

**Requirements:**
- `GOOGLE_PICKER_CLIENT_ID` - Web App OAuth client ID
- `GOOGLE_API_KEY` - API key for Google Picker

### Manual Folder Management

#### Show Allowed Folders

```bash
vectrola gdrive allowed
```

Example output:
```
Allowed folders:
  📁 /songs
  📁 /Music/Bollywood

2 folder(s) allowed
```

If no restrictions are set:
```
No folder restrictions set.
Vectrola can access your entire Google Drive.
Use 'vectrola gdrive allow <path>' to restrict access.
```

#### Allow a Folder

```bash
vectrola gdrive allow /songs
vectrola gdrive allow "/Music/Bollywood"
```

Once you allow at least one folder, Vectrola will **only** be able to access those folders and their subfolders.

#### Remove a Folder

```bash
vectrola gdrive disallow /songs
```

#### Clear All Restrictions

```bash
vectrola gdrive disallow --all
```

This removes all folder restrictions, allowing Vectrola to access your entire Drive again.

## Commands Reference

### `vectrola gdrive auth`

Authenticate with Google Drive.

```bash
# Sign in (opens browser)
vectrola gdrive auth

# Sign out (removes stored credentials)
vectrola gdrive auth --logout
```

### `vectrola gdrive status`

Show account information and storage quota.

```bash
vectrola gdrive status
```

Example output:
```
✓ Authenticated with Google Drive

Account    user@gmail.com
Name       John Doe
Storage    12.3 GB / 15.0 GB (82%)
```

### `vectrola gdrive select`

Open Google Picker to select folders interactively.

```bash
vectrola gdrive select
```

Requires `GOOGLE_PICKER_CLIENT_ID` and `GOOGLE_API_KEY` environment variables.

### `vectrola gdrive allowed`

Show folders that Vectrola is allowed to access.

```bash
vectrola gdrive allowed
```

### `vectrola gdrive allow <path>`

Add a folder to the allowed list.

```bash
vectrola gdrive allow /songs
vectrola gdrive allow "/Music/Bollywood"
```

### `vectrola gdrive disallow <path>`

Remove a folder from the allowed list.

```bash
# Remove specific folder
vectrola gdrive disallow /songs

# Clear all restrictions
vectrola gdrive disallow --all
```

### `vectrola gdrive list [path]`

Browse Google Drive folders and audio files.

```bash
# List root
vectrola gdrive list /

# List specific folder
vectrola gdrive list "/Music/Bollywood"

# Find all audio files recursively
vectrola gdrive list "/Music" --recursive
```

Example output:
```
📁 /Music/Bollywood
┌────────────────────────────┬────────┬──────────┐
│ Name                       │  Type  │     Size │
├────────────────────────────┼────────┼──────────┤
│ 📁 2020s                   │ folder │        - │
│ 📁 90s Classics            │ folder │        - │
│ 🎵 Tum Hi Ho.mp3           │ mp3    │  8.2 MB  │
│ 🎵 Channa Mereya.flac      │ flac   │ 32.1 MB  │
└────────────────────────────┴────────┴──────────┘

2 folders, 2 audio files
```

### `vectrola gdrive ingest <path>`

Ingest audio files from Drive into the knowledge graph.

```bash
# Ingest a folder (recursively by default)
vectrola gdrive ingest "/Music/Bollywood"

# Ingest without subfolders
vectrola gdrive ingest "/Music" --no-recursive

# Fast mode (skip Demucs stem separation)
vectrola gdrive ingest "/Music" --fast
```

Files are downloaded temporarily, processed through the full pipeline (metadata, lyrics, embeddings), then cleaned up.

### `vectrola gdrive setup`

Configure custom OAuth credentials (for BYOC - see below).

```bash
vectrola gdrive setup \
  --client-id "YOUR_ID.apps.googleusercontent.com" \
  --client-secret "YOUR_SECRET"
```

## Environment Variables

Vectrola requires OAuth credentials to access Google Drive. Configure these in your `.env` file:

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | Desktop App OAuth client ID (for CLI authentication) |
| `GOOGLE_CLIENT_SECRET` | Yes | Desktop App OAuth client secret |
| `GOOGLE_PICKER_CLIENT_ID` | For `select` | Web App OAuth client ID (for Google Picker UI) |
| `GOOGLE_API_KEY` | For `select` | API key for Google Picker API |

Example `.env`:
```bash
# CLI Authentication (Desktop App)
GOOGLE_CLIENT_ID=123456-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxx

# Google Picker (Web App - optional)
GOOGLE_PICKER_CLIENT_ID=123456-xyz.apps.googleusercontent.com
GOOGLE_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxx
```

**Note:** The Picker requires a separate **Web Application** OAuth client (not Desktop App) because it runs in the browser.

## Bring Your Own Credentials (BYOC)

By default, Vectrola uses credentials from your `.env` file. You can also set up your own Google Cloud project for a dedicated quota and no "unverified app" warning.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Create Project"
3. Name it something like "My Vectrola"

### Step 2: Enable APIs

1. In your project, go to **APIs & Services > Library**
2. Search for and enable:
   - **Google Drive API** (required)
   - **Google Picker API** (for folder selection)

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Select **External** user type
3. Fill in required fields:
   - App name: "My Vectrola"
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue**
5. Skip scopes (we'll request them at auth time)
6. Add yourself as a test user
7. Complete the wizard

### Step 4: Create OAuth Credentials

You need two OAuth credentials:

#### Desktop App (for CLI auth)

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Application type: **Desktop app**
4. Name: "Vectrola CLI"
5. Click **Create**
6. Copy the **Client ID** and **Client Secret**

#### Web Application (for Picker - optional)

1. Click **Create Credentials > OAuth client ID** again
2. Application type: **Web application**
3. Name: "Vectrola Picker"
4. Under **Authorized JavaScript origins**, add:
   - `http://localhost:8765`
5. Click **Create**
6. Copy the **Client ID** (no secret needed for web apps with Picker)

### Step 5: Create API Key

1. Click **Create Credentials > API key**
2. Copy the API key
3. (Optional) Click **Restrict Key** and limit it to Google Picker API

### Step 6: Configure Vectrola

**Option A: Environment variables** (recommended)

Add to your `.env` file:
```bash
# CLI auth (Desktop App)
GOOGLE_CLIENT_ID=your_desktop_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret

# Picker (Web App)
GOOGLE_PICKER_CLIENT_ID=your_web_client_id.apps.googleusercontent.com
GOOGLE_API_KEY=your_api_key
```

**Option B: CLI setup command** (Desktop credentials only)

```bash
vectrola gdrive setup \
  --client-id "your_client_id.apps.googleusercontent.com" \
  --client-secret "your_client_secret"
```

Then re-authenticate:
```bash
vectrola gdrive auth
```

## Security Notes

- **Read-only access by default**: For music ingestion, Vectrola uses `drive.readonly` scope - it cannot modify or delete your files
- **Write access for sync**: Wiki sync uses `drive.file` scope - Vectrola can only access files it creates
- **Local storage**: OAuth tokens are stored in `~/.config/vectrola/` with secure file permissions (600)
- **No server**: Authentication happens entirely locally - no data sent to Vectrola servers
- **Token refresh**: Access tokens auto-refresh using the stored refresh token
- **Folder restrictions**: When you set allowed folders, Vectrola enforces these locally (your Drive remains fully accessible through other apps)

---

## Write Operations (Wiki Sync)

When you use `vectrola wiki --sync`, Vectrola needs write access to upload the wiki to Google Drive. This uses the `drive.file` scope instead of `drive.readonly`.

### Scope Comparison

| Scope | Access Level | Use Case |
|-------|--------------|----------|
| `drive.readonly` | Read any file | Ingest music from Drive |
| `drive.file` | Read/write files created by app only | Wiki sync |

**Note:** `drive.file` is more restrictive than `drive.readonly` in some ways - Vectrola can only access files it creates, not your entire Drive.

### Re-Authentication Required

If you previously authenticated with read-only scope, you must re-authenticate to enable sync:

```bash
vectrola gdrive auth --logout
vectrola gdrive auth
```

The new authentication grants both read access (for music ingestion) and write access (for wiki sync), but only to Vectrola-created files.

### Upload Methods

The DriveClient provides these methods for wiki sync:

| Method | Description |
|--------|-------------|
| `create_folder(name, parent_id)` | Create a folder |
| `find_or_create_folder(path)` | Create nested folders (e.g., `/Vectrola/wiki`) |
| `upload_file(local_path, parent_id)` | Upload a new file |
| `update_file(file_id, local_path)` | Update existing file |
| `find_file(name, parent_id)` | Find file by name |
| `upload_or_update_file(local_path, parent_id)` | Smart upload (creates or updates) |

### Folder Structure

Wiki sync creates this structure in your Drive:

```
My Drive/
└── Vectrola/              (created by app)
    └── wiki/              (created by app)
        ├── README.md
        ├── Tracks/
        ├── Artists/
        ├── Moods/
        ├── Themes/
        ├── Movies/
        └── Eras/
```

All folders and files are created by Vectrola, so they fall under the `drive.file` scope.

## Troubleshooting

### "Not authenticated" error

Run `vectrola gdrive auth` to sign in.

### "Google Drive support not installed"

Install the gdrive extras:
```bash
pip install vectrola[gdrive]
```

### "GOOGLE_CLIENT_ID not set" / "Credentials not configured"

Vectrola needs OAuth credentials. Either:
1. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in your `.env` file
2. Run `vectrola gdrive setup` with your credentials
3. Follow the BYOC setup above

### Browser doesn't open

This can happen on headless servers, in SSH sessions, or behind corporate proxies. Vectrola automatically falls back to the console flow:
1. Copy the URL printed in the terminal
2. Open it in a browser on any device
3. Complete sign-in and copy the code
4. Paste it back into the terminal

### "Unverified app" warning

This is normal when using credentials that haven't been verified by Google. Click **Advanced > Go to [App Name] (unsafe)** to proceed.

To avoid this warning:
- Set up your own credentials (BYOC) and add yourself as a test user
- Or submit your app for Google verification (for public distribution)

### "Access denied" when listing/ingesting

You're trying to access a folder outside your allowed list. Check your restrictions:
```bash
# See what's allowed
vectrola gdrive allowed

# Add the folder you need
vectrola gdrive allow /path/to/folder

# Or clear all restrictions
vectrola gdrive disallow --all
```

### "GOOGLE_PICKER_CLIENT_ID not set" error

The `select` command requires additional credentials:
1. Create a **Web Application** OAuth client (not Desktop)
2. Create an API key
3. Set `GOOGLE_PICKER_CLIENT_ID` and `GOOGLE_API_KEY` in your `.env`

Or skip the Picker and use manual folder management:
```bash
vectrola gdrive allow /Music
```

### Rate limits / quota errors

If you hit Google API limits:
1. Wait a few minutes and retry
2. Consider setting up your own credentials (BYOC) for a dedicated quota
3. Process files in smaller batches

### Token expired / invalid

Re-authenticate:
```bash
vectrola gdrive auth --logout
vectrola gdrive auth
```
