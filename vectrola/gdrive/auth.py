"""Google Drive OAuth authentication via vectrola-oauth.up.railway.app.

New architecture:
- Uses centralized OAuth server for token exchange
- Only requires drive.file scope (app-created folders only)
- No picker, no folder selection - vectrola creates /Vectrola/ folder
- PKCE flow with manual token copy/paste from browser
"""

import json
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

from .oauth_client import authenticate as oauth_authenticate

console = Console()

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # App-created files only
]

# Token storage location (XDG-compliant)
TOKEN_DIR = Path.home() / ".config" / "vectrola"
TOKEN_PATH = TOKEN_DIR / "gdrive_token.json"


def is_authenticated() -> bool:
    """Check if valid credentials exist."""
    if not TOKEN_PATH.exists():
        return False

    try:
        token_data = json.loads(TOKEN_PATH.read_text())
        token_expiry = token_data.get("token_expiry", 0)

        # Check if token is still valid (with 5-minute buffer)
        return time.time() < (token_expiry - 300)

    except Exception:
        return False


def get_credentials():
    """Load saved credentials and auto-refresh if needed.

    Returns:
        google.oauth2.credentials.Credentials or None if not authenticated
    """
    if not TOKEN_PATH.exists():
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        token_data = json.loads(TOKEN_PATH.read_text())

        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,  # Server handles refresh
            client_secret=None,
            scopes=SCOPES
        )

        # Check if token needs refresh
        if time.time() >= token_data.get("token_expiry", 0):
            # Refresh via OAuth server
            from .oauth_client import refresh_access_token

            result = refresh_access_token(token_data["refresh_token"])
            if result:
                new_access_token, expires_in = result

                # Update token file
                token_data["access_token"] = new_access_token
                token_data["expires_in"] = expires_in
                token_data["token_expiry"] = time.time() + expires_in

                TOKEN_PATH.write_text(json.dumps(token_data, indent=2))

                # Update credentials object
                creds.token = new_access_token
            else:
                console.print("[red]Failed to refresh token. Please re-authenticate.[/red]")
                return None

        return creds

    except Exception as e:
        console.print(f"[red]Failed to load credentials: {e}[/red]")
        return None


def authenticate(force: bool = False) -> Optional["Credentials"]:
    """Run OAuth flow via vectrola-oauth.up.railway.app.

    Args:
        force: If True, re-authenticate even if valid credentials exist

    Returns:
        google.oauth2.credentials.Credentials or None if failed
    """
    # Check if already authenticated
    if not force:
        creds = get_credentials()
        if creds:
            return creds

    # Run OAuth flow
    success = oauth_authenticate(TOKEN_PATH, force)

    if not success:
        console.print("[red]Authentication failed[/red]")
        return None

    # Load the newly saved credentials
    return get_credentials()


def logout() -> bool:
    """Remove stored credentials.

    Returns:
        True if anything was removed, False if nothing existed
    """
    removed = False

    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
        removed = True
        console.print("[green]✅ Logged out of Google Drive[/green]")

    return removed

