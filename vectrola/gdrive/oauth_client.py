"""OAuth client for vectrola-oauth.up.railway.app server.

Uses local HTTP callback server for automatic token capture (like gcloud, gh CLI).
"""

import hashlib
import secrets
import base64
import webbrowser
import json
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Tuple, Optional
from urllib.parse import urlencode, urlparse, parse_qs
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


# =============================================================================
# Local Callback Server (like gcloud, gh CLI)
# =============================================================================

class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to receive OAuth callback with tokens."""

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

    def do_GET(self):
        """Handle GET request from OAuth server redirect."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Extract tokens from query params
        access_token = params.get('access_token', [None])[0]
        refresh_token = params.get('refresh_token', [''])[0]
        expires_in = params.get('expires_in', ['3600'])[0]
        error = params.get('error', [None])[0]

        # Store on server instance
        self.server.tokens = None
        self.server.error = None

        if error:
            self.server.error = error
        elif access_token:
            self.server.tokens = (access_token, refresh_token, int(expires_in))

        # Respond with auto-close HTML
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

        if error:
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Authentication Failed</title>
</head>
<body style="font-family: -apple-system, sans-serif; text-align: center; padding: 50px;">
    <h1 style="color: #dc3545;">&#10060; Authentication Failed</h1>
    <p>{error}</p>
    <p style="color: #666;">Please close this tab and try again.</p>
</body>
</html>"""
        else:
            html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Authentication Complete</title>
</head>
<body style="font-family: -apple-system, sans-serif; text-align: center; padding: 50px;">
    <h1 style="color: #28a745;">&#10004; Authentication Successful!</h1>
    <p>You can close this tab now.</p>
    <p style="color: #666;">Returning to terminal...</p>
    <script>setTimeout(() => window.close(), 1500);</script>
</body>
</html>"""

        self.wfile.write(html.encode())

        # Signal that we received a response
        self.server.received_callback.set()


def find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_callback_server(timeout: int = 120) -> Optional[Tuple[str, str, int]]:
    """Start local HTTP server and wait for OAuth callback.

    Args:
        timeout: Seconds to wait for callback before timing out

    Returns:
        Tuple of (access_token, refresh_token, expires_in) or None if failed
    """
    port = find_free_port()
    server = HTTPServer(('127.0.0.1', port), CallbackHandler)
    server.tokens = None
    server.error = None
    server.received_callback = threading.Event()

    # Get the callback URL
    callback_url = f"http://127.0.0.1:{port}/callback"

    # Run server in background thread
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.daemon = True
    server_thread.start()

    return server, port, callback_url


def wait_for_callback(server: HTTPServer, timeout: int = 120) -> Optional[Tuple[str, str, int]]:
    """Wait for callback server to receive tokens.

    Args:
        server: HTTPServer instance from start_callback_server
        timeout: Seconds to wait

    Returns:
        Tuple of (access_token, refresh_token, expires_in) or None
    """
    # Wait for callback with timeout
    received = server.received_callback.wait(timeout=timeout)

    if not received:
        console.print("[red]Authentication timed out. Please try again.[/red]")
        return None

    if server.error:
        console.print(f"[red]Authentication failed: {server.error}[/red]")
        return None

    return server.tokens


# =============================================================================
# OAuth Flow Functions
# =============================================================================

def start_auth_flow(state: str, code_verifier: str, callback_url: str) -> bool:
    """Register auth flow with OAuth server.

    Args:
        state: Unique state identifier
        code_verifier: PKCE verifier
        callback_url: Local callback URL (e.g., http://127.0.0.1:8000/callback)

    Returns:
        True if successful
    """
    try:
        response = requests.post(
            f"{OAUTH_SERVER_URL}/auth/start",
            json={
                "state": state,
                "code_verifier": code_verifier,
                "client_type": "cli",
                "callback_url": callback_url,
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
    webbrowser.open(auth_url)


def save_tokens(token_path: Path, access_token: str, refresh_token: str, expires_in: int) -> None:
    """Save tokens to disk.

    Args:
        token_path: Path to token file
        access_token: Google access token
        refresh_token: Google refresh token
        expires_in: Token expiry in seconds
    """
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
    """Complete OAuth flow with automatic token capture.

    Uses a local HTTP callback server (like gcloud, gh CLI) to automatically
    receive tokens after browser authentication - no manual copy/paste needed.

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

    # Start local callback server FIRST (to get port)
    server, port, callback_url = start_callback_server()

    console.print(f"\n[bold cyan]Starting Google Drive authentication...[/bold cyan]")
    console.print(f"[dim]Callback server listening on port {port}[/dim]\n")

    # Register with OAuth server (include callback_url)
    if not start_auth_flow(state, code_verifier, callback_url):
        return False

    # Open browser
    console.print("[bold]Opening browser for Google authentication...[/bold]")
    open_auth_url(state, code_challenge)

    # Wait for callback (blocking with spinner)
    console.print("\n[cyan]Waiting for authentication... (press Ctrl+C to cancel)[/cyan]")

    tokens = wait_for_callback(server, timeout=120)

    if not tokens:
        return False

    access_token, refresh_token, expires_in = tokens

    # Save tokens
    save_tokens(token_path, access_token, refresh_token, expires_in)

    console.print(f"\n[green]✅ Successfully authenticated with Google Drive![/green]")
    console.print(f"[dim]Tokens saved to {token_path}[/dim]")

    return True
