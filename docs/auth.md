# Authentication & User Management

Vectrola supports two user modes:

1. **Anonymous Mode** - Single device, no login required (default)
2. **Logged-in Mode** - Syncs library across devices

## Quick Start

```bash
# Check current user status
vectrola whoami

# Login to sync across devices
vectrola login

# Logout (return to anonymous)
vectrola logout
```

## User Modes

### Anonymous Mode (Default)

When you first use Vectrola, you're automatically assigned an anonymous user ID:

```bash
$ vectrola whoami
Anonymous user: anon_df80fcbd31b7
(Single device only. Run 'vectrola login' to sync across devices.)
```

**Characteristics:**
- Auto-generated ID like `anon_abc123def456`
- Stored in `~/.config/vectrola/anon_id`
- Works immediately, no setup required
- **Single device only** - different devices get different IDs

**Best for:**
- Trying out Vectrola
- Personal use on one device
- Privacy-conscious users

### Logged-in Mode

Login with your email/username to sync your library across devices:

```bash
$ vectrola login
Email or username: arunesh@example.com
✅ Logged in as arunesh@example.com
   Your library will now sync across devices.

$ vectrola whoami
Logged in as: arunesh@example.com
```

**Characteristics:**
- Your email/username becomes your user ID
- Stored in `~/.config/vectrola/session.json`
- Same library accessible from any device
- Can switch between users with logout/login

**Best for:**
- Multi-device usage (laptop + phone)
- Shared family/team setups
- Future SaaS features

## Commands

### `vectrola login`

Login to sync your library across devices.

```bash
$ vectrola login
Email or username: your-email@example.com
✅ Logged in as your-email@example.com
   Your library will now sync across devices.
```

If already logged in:
```bash
$ vectrola login
Already logged in as: your-email@example.com
Run 'vectrola logout' first to switch users.
```

### `vectrola logout`

Logout and return to anonymous mode.

```bash
$ vectrola logout
✅ Logged out. Switched to anonymous mode.

Wiki was generated for 'alice@example.com'. Regenerating for anonymous user...
```

Your library data remains on the server but won't be accessible until you login again.

**Options:**

| Flag | Description |
|------|-------------|
| `--purge-wiki` | Delete the wiki folder instead of regenerating (for privacy) |

```bash
# Delete wiki completely on logout (for privacy)
$ vectrola logout --purge-wiki
✅ Logged out. Switched to anonymous mode.
🗑️  Wiki deleted.
```

### `vectrola whoami`

Show current user status.

```bash
# When logged in
$ vectrola whoami
Logged in as: arunesh@example.com

# When anonymous
$ vectrola whoami
Anonymous user: anon_df80fcbd31b7
(Single device only. Run 'vectrola login' to sync across devices.)
```

### `vectrola library stats`

Shows user info along with library statistics:

```bash
$ vectrola library stats
📊 Library Statistics

 User           arunesh@example.com (logged in)
 Total Tracks   121
 ☁️ GDrive only  0
 💾 Local only  121
 ☁️ + 💾 Both    0
```

## Storage

User data is stored in `~/.config/vectrola/`:

```
~/.config/vectrola/
├── session.json    # Current logged-in user (if any)
├── anon_id         # Anonymous user ID (generated once)
├── library.json    # Track mappings for current user
└── gdrive_token.json  # Google Drive OAuth token
```

### session.json (when logged in)

```json
{
  "user_id": "arunesh@example.com",
  "logged_in_at": "2026-06-12T12:00:00Z"
}
```

### anon_id (for anonymous users)

```
anon_a1b2c3d4e5f6
```

## Multi-Tenant Mode

By default, multi-tenant filtering is **OFF** - all searches return all tracks.

To enable user-scoped searches (only see your own tracks):

```bash
# In .env file
VECTROLA_MULTI_TENANT=true

# Or as environment variable
export VECTROLA_MULTI_TENANT=true
```

When enabled:
- `vectrola search` only returns tracks in your library
- `vectrola library list` shows only your tracks
- Tracks are shared in the global catalog but filtered by user

## Migrating Existing Data

### Using `migrate-user` Command (Recommended)

If you started with anonymous mode and want to migrate to a logged-in account:

```bash
# 1. Login first
vectrola login
# Enter: your-email@example.com

# 2. Preview what will be migrated
vectrola migrate-user --dry-run

# 3. Run the migration
vectrola migrate-user
```

**Security:** For protection, you can only migrate from **this device's anonymous user**. You cannot migrate someone else's tracks.

**Example output:**
```
Migration Plan
  From: anon_df80fcbd31b7
  To:   your-email@example.com

Found 47 tracks to migrate.

Migrate 47 tracks from 'anon_df80fcbd31b7' to 'your-email@example.com'? [y/N]: y
Migrating tracks... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 47/47

✅ Migrated 47/47 tracks successfully!

Remove anonymous ID file? (You're now using the logged-in account) [y/N]: y
Removed ~/.config/vectrola/anon_id

Next steps:
  • Run 'vectrola library list' to see your migrated tracks
  • Run 'vectrola wiki' to regenerate your wiki
```

### `migrate-user` Options

```bash
# Migrate current anon to logged-in user (most common)
vectrola migrate-user

# Preview without making changes
vectrola migrate-user --dry-run

# Specify target user explicitly
vectrola migrate-user --to my_new_user
```

**Note:** The `--from` option is restricted to this device's anonymous user for security.

### Using Migration Script (Advanced)

For bulk operations or custom migrations:

```bash
# Login first
vectrola login
# Enter your email

# Run migration to update track ownership
python scripts/migrate_to_multitenancy.py
```

This updates all tracks in Qdrant to be owned by your current user.

## Priority Order

User ID is resolved in this order:

1. `VECTROLA_USER_ID` environment variable (for testing/CI)
2. `~/.config/vectrola/session.json` (logged-in user)
3. `~/.config/vectrola/anon_id` (anonymous user, auto-generated if missing)

## Multiple Users on Same Device

```bash
# User 1 logs in
$ vectrola login
Email: alice@example.com
✅ Logged in as alice@example.com

$ vectrola ingest /alice-music/
# Tracks added to Alice's library

# Switch to User 2
$ vectrola logout
$ vectrola login
Email: bob@example.com
✅ Logged in as bob@example.com

$ vectrola ingest /bob-music/
# Tracks added to Bob's library

# Alice's tracks are still there, just not visible to Bob
# (when multi-tenant mode is ON)
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VECTROLA_USER_ID` | Override user ID (for testing/CI) | Not set |
| `VECTROLA_MULTI_TENANT` | Enable user-scoped filtering | `false` |

## Troubleshooting

### "My searches return no results"

If multi-tenant is ON but your tracks have a different user_id:

```bash
# Check current user
vectrola whoami

# Check what user_ids tracks have
python -c "
from vectrola.storage.qdrant import get_db
db = get_db()
tracks = db.list_all(limit=3)
for t in tracks:
    print(f'{t.payload.get(\"title\")}: {t.payload.get(\"user_ids\")}')
"

# If mismatched, run migration
vectrola login  # with correct email
python scripts/migrate_to_multitenancy.py
```

### "I want to reset to anonymous"

```bash
vectrola logout
rm ~/.config/vectrola/anon_id  # Optional: get new anon ID
vectrola whoami  # New anon ID generated
```
