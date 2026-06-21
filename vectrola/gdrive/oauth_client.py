"""OAuth client for vectrola-oauth.up.railway.app server."""

import hashlib
import secrets
import base64
import webbrowser
import json
from typing import Tuple, Optional
import requests
from pathlib import Path

from rich.console import Console

console = Console()

# OAuth server URL
OAUTH_SERVER_URL = "https://vectrola-oauth.up.railway.app"
GOOGLE_CLIENT_ID = "212647824656-9h9gchm0msibletsog338miabe9qtbe1.apps.googleusercontent.com"


def generate_pkce() -> Tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge.

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate 128-character random verifier
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(96)).decode('utf-8').rstrip('=')

    # Compute SHA256 challenge
    challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

    return code_verifier, code_challenge


def start_auth_flow(state: str, code_verifier: str) -> bool:
    """Register auth flow with OAuth server.

    Args:
        state: Unique state identifier
        code_verifier: PKCE verifier

    Returns:
        True if successful
    """
    try:
        response = requests.post(
            f"{OAUTH_SERVER_URL}/auth/start",
            json={
                "state": state,
                "code_verifier": code_verifier,
                "client_type": "cli"
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("ok", False)
    except Exception as e:
        console.print(f"[red]Failed to start auth flow: {e}[/red]")
        return False


def open_auth_url(state: str, code_challenge: str) -> None:
    """Open browser to Google OAuth URL.

    Args:
        state: Unique state identifier
        code_challenge: PKCE challenge
    """
    from urllib.parse import urlencode

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{OAUTH_SERVER_URL}/callback",
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent"
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    console.print("\n[bold cyan]Opening browser for Google authentication...[/bold cyan]")
    webbrowser.open(auth_url)


def prompt_for_tokens() -> Optional[Tuple[str, str, int]]:
    """Prompt user to paste tokens from browser.

    Returns:
        Tuple of (access_token, refresh_token, expires_in) or None if cancelled
    """
    console.print("\n[bold green]✅ Authentication page opened in browser![/bold green]")
    console.print("\n[yellow]After authenticating, you'll see a page with two tokens.[/yellow]")
    console.print("[yellow]Please copy and paste them below:[/yellow]\n")

    try:
        access_token = console.input("[bold]Access Token:[/bold] ").strip()
        if not access_token:
            console.print("[red]Access token is required[/red]")
            return None

        refresh_token = console.input("[bold]Refresh Token:[/bold] ").strip()
        if not refresh_token:
            console.print("[red]Refresh token is required[/red]")
            return None

        # Default to 3600 seconds (1 hour) if not provided
        expires_in = 3600

        return access_token, refresh_token, expires_in

    except KeyboardInterrupt:
        console.print("\n[yellow]Authentication cancelled[/yellow]")
        return None


def save_tokens(token_path: Path, access_token: str, refresh_token: str, expires_in: int) -> None:
    """Save tokens to disk.

    Args:
        token_path: Path to token file
        access_token: Google access token
        refresh_token: Google refresh token
        expires_in: Token expiry in seconds
    """
    import time

    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "token_expiry": time.time() + expires_in
    }

    # Create parent directory if needed
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Write with secure permissions (owner read/write only)
    token_path.write_text(json.dumps(token_data, indent=2))

    # Set permissions (Unix only)
    try:
        import os
        os.chmod(token_path, 0o600)
    except Exception:
        pass  # Windows doesn't support chmod

    console.print(f"\n[green]✅ Tokens saved to {token_path}[/green]")


def refresh_access_token(refresh_token: str) -> Optional[Tuple[str, int]]:
    """Refresh access token using refresh token.

    Args:
        refresh_token: Google refresh token

    Returns:
        Tuple of (new_access_token, expires_in) or None if failed
    """
    try:
        response = requests.post(
            f"{OAUTH_SERVER_URL}/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        return data["access_token"], data["expires_in"]

    except Exception as e:
        console.print(f"[red]Failed to refresh token: {e}[/red]")
        return None


def authenticate(token_path: Path, force: bool = False) -> bool:
    """Complete OAuth flow and save tokens.

    Args:
        token_path: Path to save tokens
        force: Force re-authentication even if tokens exist

    Returns:
        True if successful
    """
    import uuid

    # Generate PKCE parameters
    state = str(uuid.uuid4())
    code_verifier, code_challenge = generate_pkce()

    # Register with OAuth server
    if not start_auth_flow(state, code_verifier):
        return False

    # Open browser
    open_auth_url(state, code_challenge)

    # Prompt for tokens
    result = prompt_for_tokens()
    if not result:
        return False

    access_token, refresh_token, expires_in = result

    # Save tokens
    save_tokens(token_path, access_token, refresh_token, expires_in)

    return True
