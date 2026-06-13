"""Google Drive OAuth authentication with browser-first, console fallback.

Follows the rclone pattern:
1. Bundled credentials for instant "just works" experience
2. Browser OAuth with localhost redirect (primary)
3. Manual code entry fallback (for proxied/headless environments)
4. BYOC (Bring Your Own Credentials) for power users
"""

import json
import os
from pathlib import Path
from typing import Optional

# Load .env at import time to ensure env vars are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",  # Read existing files
    "https://www.googleapis.com/auth/drive.file",      # Create/upload files (wiki sync)
]

# Token storage location (XDG-compliant)
TOKEN_DIR = Path.home() / ".config" / "vectrola"
TOKEN_PATH = TOKEN_DIR / "gdrive_token.json"
CUSTOM_CREDS_PATH = TOKEN_DIR / "gdrive_custom_credentials.json"
ALLOWED_FOLDERS_PATH = TOKEN_DIR / "gdrive_allowed_folders.json"


def _get_bundled_credentials() -> tuple[str, str]:
    """Get bundled credentials from environment variables."""
    return (
        os.getenv("GOOGLE_CLIENT_ID", ""),
        os.getenv("GOOGLE_CLIENT_SECRET", ""),
    )


def _get_client_config() -> dict:
    """Get OAuth client configuration (custom or bundled)."""
    # Check for custom credentials first
    if CUSTOM_CREDS_PATH.exists():
        with open(CUSTOM_CREDS_PATH) as f:
            custom = json.load(f)
            return {
                "installed": {
                    "client_id": custom["client_id"],
                    "client_secret": custom["client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }

    # Check environment variables (loaded from .env)
    client_id, client_secret = _get_bundled_credentials()

    if client_id and client_secret:
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    # No credentials found
    raise RuntimeError(
        "Google Drive credentials not configured.\n\n"
        "Options:\n"
        "1. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env\n"
        "2. Run: vectrola gdrive setup --client-id YOUR_ID --client-secret YOUR_SECRET\n"
        "3. See docs/gdrive.md for setup instructions"
    )


def setup_custom_credentials(client_id: str, client_secret: str) -> None:
    """Save custom OAuth credentials for BYOC users.

    This allows power users to use their own Google Cloud project,
    avoiding the unverified app warning and 100-user limit.
    """
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    credentials = {
        "client_id": client_id,
        "client_secret": client_secret,
    }

    with open(CUSTOM_CREDS_PATH, "w") as f:
        json.dump(credentials, f, indent=2)

    # Secure file permissions (Unix only)
    try:
        CUSTOM_CREDS_PATH.chmod(0o600)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod

    # Clear existing token so user re-authenticates with new credentials
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def is_authenticated() -> bool:
    """Check if valid credentials exist."""
    try:
        creds = get_credentials()
        return creds is not None and creds.valid
    except Exception:
        return False


def get_credentials():
    """Load and auto-refresh saved credentials.

    Returns:
        google.oauth2.credentials.Credentials or None if not authenticated
    """
    if not TOKEN_PATH.exists():
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(creds)

        return creds if creds and creds.valid else None

    except Exception:
        return None


def authenticate(force: bool = False) -> "Credentials":
    """Run OAuth flow to authenticate with Google Drive.

    Uses browser-based flow by default, with console fallback for
    environments where localhost redirect doesn't work.

    Args:
        force: If True, re-authenticate even if valid credentials exist

    Returns:
        google.oauth2.credentials.Credentials

    Raises:
        RuntimeError: If credentials not configured
        Exception: If authentication fails
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Check if already authenticated
    if not force:
        creds = get_credentials()
        if creds:
            return creds

    client_config = _get_client_config()
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    try:
        # Primary: Browser flow with random port
        print("Opening browser for Google Drive authentication...")
        print("(If browser doesn't open, see the URL below)\n")

        credentials = flow.run_local_server(
            port=0,  # Random available port
            timeout_seconds=120,
            success_message="Authentication successful! You can close this tab.",
            open_browser=True,
        )

    except Exception as e:
        # Fallback: Manual console flow
        print(f"\n[!] Browser authentication failed: {e}")
        print("Switching to manual verification...\n")

        auth_url, _ = flow.authorization_url(prompt="consent")

        print("1. Open this URL in your browser:\n")
        print(f"   {auth_url}\n")
        print("2. Sign in and authorize Vectrola")
        print("3. Copy the authorization code shown\n")

        code = input("Enter authorization code: ").strip()

        if not code:
            raise RuntimeError("No authorization code provided")

        flow.fetch_token(code=code)
        credentials = flow.credentials

    _save_credentials(credentials)
    print("\n✅ Successfully authenticated with Google Drive!")

    return credentials


def _save_credentials(credentials) -> None:
    """Save credentials to file with secure permissions."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    with open(TOKEN_PATH, "w") as f:
        f.write(credentials.to_json())

    # Secure file permissions (Unix only)
    try:
        TOKEN_PATH.chmod(0o600)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod


def logout() -> bool:
    """Remove stored credentials and allowed folders list.

    Returns:
        True if anything was removed, False if nothing existed
    """
    removed = False

    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        removed = True

    if ALLOWED_FOLDERS_PATH.exists():
        ALLOWED_FOLDERS_PATH.unlink()
        removed = True

    return removed


# =============================================================================
# Allowed Folders Management
# =============================================================================


def get_allowed_folders() -> dict[str, str]:
    """Get the list of folders user has allowed access to.

    Returns:
        Dict mapping folder_id to folder_path (e.g., {"abc123": "/songs"})
    """
    if not ALLOWED_FOLDERS_PATH.exists():
        return {}

    try:
        with open(ALLOWED_FOLDERS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def add_allowed_folder(folder_id: str, folder_path: str) -> None:
    """Add a folder to the allowed list.

    Args:
        folder_id: Google Drive folder ID
        folder_path: Human-readable path (e.g., "/songs")
    """
    folders = get_allowed_folders()
    folders[folder_id] = folder_path

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALLOWED_FOLDERS_PATH, "w") as f:
        json.dump(folders, f, indent=2)

    try:
        ALLOWED_FOLDERS_PATH.chmod(0o600)
    except (OSError, AttributeError):
        pass


def remove_allowed_folder(folder_id: str) -> bool:
    """Remove a folder from the allowed list.

    Returns:
        True if folder was removed, False if it wasn't in the list
    """
    folders = get_allowed_folders()
    if folder_id not in folders:
        return False

    del folders[folder_id]

    with open(ALLOWED_FOLDERS_PATH, "w") as f:
        json.dump(folders, f, indent=2)

    return True


def clear_allowed_folders() -> int:
    """Remove all allowed folders.

    Returns:
        Number of folders that were removed
    """
    folders = get_allowed_folders()
    count = len(folders)

    if ALLOWED_FOLDERS_PATH.exists():
        ALLOWED_FOLDERS_PATH.unlink()

    return count


def is_folder_allowed(folder_id: str) -> bool:
    """Check if a folder is in the allowed list.

    Args:
        folder_id: Google Drive folder ID to check

    Returns:
        True if folder is allowed (or if no restrictions set)
    """
    folders = get_allowed_folders()

    # If no folders are configured, allow all (backward compatible)
    if not folders:
        return True

    return folder_id in folders


def is_path_allowed(path: str, resolve_func) -> bool:
    """Check if a path is within an allowed folder.

    Args:
        path: Drive path like "/songs/subfolder"
        resolve_func: Function to resolve path to folder ID

    Returns:
        True if path is allowed
    """
    folders = get_allowed_folders()

    # If no folders configured, allow all
    if not folders:
        return True

    # Check if path starts with any allowed path
    normalized_path = "/" + path.strip("/")
    for folder_id, allowed_path in folders.items():
        normalized_allowed = "/" + allowed_path.strip("/")
        if normalized_path.startswith(normalized_allowed):
            return True

    return False
