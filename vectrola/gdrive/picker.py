"""Google Drive Picker for folder selection.

Serves a local web page with Google's Picker UI so users can select
which folders to grant access to. Uses Google Identity Services (GIS)
for authentication.
"""

import http.server
import json
import os
import socketserver
import threading
import webbrowser
from pathlib import Path
from typing import Optional

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# HTML template for the picker page using Google Identity Services
PICKER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Vectrola - Select Google Drive Folders</title>
    <meta charset="UTF-8">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 500px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
        }
        p {
            color: #666;
            margin-bottom: 30px;
        }
        button {
            background: #4285f4;
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.3s;
        }
        button:hover {
            background: #3367d6;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 8px;
            display: none;
        }
        .status.success {
            display: block;
            background: #d4edda;
            color: #155724;
        }
        .status.error {
            display: block;
            background: #f8d7da;
            color: #721c24;
        }
        .status.info {
            display: block;
            background: #cce5ff;
            color: #004085;
        }
        .selected-folders {
            text-align: left;
            margin-top: 20px;
        }
        .folder-item {
            padding: 10px;
            background: #f5f5f5;
            margin: 5px 0;
            border-radius: 4px;
        }
        #signInDiv {
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Vectrola</h1>
        <p>Select the Google Drive folders containing your music.<br>
        Vectrola will only have access to the folders you choose.</p>

        <div id="signInDiv"></div>

        <button id="pickBtn" onclick="openPicker()" style="display:none;">Select Folders</button>

        <div id="status" class="status"></div>

        <div id="selectedFolders" class="selected-folders" style="display:none;">
            <h3>Selected Folders:</h3>
            <div id="folderList"></div>
            <button onclick="confirmSelection()" style="margin-top: 15px; background: #28a745;">
                Confirm & Continue
            </button>
        </div>
    </div>

    <!-- Google Identity Services -->
    <script src="https://accounts.google.com/gsi/client"></script>
    <!-- Google Picker API -->
    <script src="https://apis.google.com/js/api.js"></script>

    <script>
        const CLIENT_ID = '{{CLIENT_ID}}';
        const API_KEY = '{{API_KEY}}';
        const APP_ID = '{{APP_ID}}';
        const SCOPES = 'https://www.googleapis.com/auth/drive.readonly';

        let accessToken = null;
        let pickerLoaded = false;
        let selectedFolders = [];

        // Load the Picker API
        function loadPickerApi() {
            gapi.load('picker', () => {
                pickerLoaded = true;
                console.log('Picker API loaded');
            });
        }
        loadPickerApi();

        // Initialize Google Identity Services
        function initTokenClient() {
            const tokenClient = google.accounts.oauth2.initTokenClient({
                client_id: CLIENT_ID,
                scope: SCOPES,
                callback: (response) => {
                    if (response.error) {
                        showStatus('error', 'Authentication failed: ' + response.error);
                        return;
                    }
                    accessToken = response.access_token;
                    console.log('Got access token');
                    showStatus('info', 'Signed in! Click "Select Folders" to continue.');
                    document.getElementById('pickBtn').style.display = 'inline-block';
                    document.getElementById('signInDiv').style.display = 'none';
                },
            });
            return tokenClient;
        }

        // Create Sign-In button
        window.onload = function() {
            const tokenClient = initTokenClient();

            // Render custom sign-in button
            const signInDiv = document.getElementById('signInDiv');
            const signInBtn = document.createElement('button');
            signInBtn.textContent = '🔐 Sign in with Google';
            signInBtn.onclick = () => {
                tokenClient.requestAccessToken();
            };
            signInDiv.appendChild(signInBtn);
        };

        function openPicker() {
            if (!pickerLoaded) {
                showStatus('error', 'Picker API not loaded yet. Please wait...');
                return;
            }
            if (!accessToken) {
                showStatus('error', 'Please sign in first.');
                return;
            }

            const picker = new google.picker.PickerBuilder()
                .setAppId(APP_ID)
                .setOAuthToken(accessToken)
                .setDeveloperKey(API_KEY)
                .addView(new google.picker.DocsView()
                    .setIncludeFolders(true)
                    .setSelectFolderEnabled(true)
                    .setMimeTypes('application/vnd.google-apps.folder'))
                .setCallback(pickerCallback)
                .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
                .setTitle('Select folders containing your music')
                .build();

            picker.setVisible(true);
        }

        function pickerCallback(data) {
            if (data.action === google.picker.Action.PICKED) {
                selectedFolders = data.docs.map(doc => ({
                    id: doc.id,
                    name: doc.name
                }));

                // Show selected folders
                const folderList = document.getElementById('folderList');
                folderList.innerHTML = selectedFolders.map(f =>
                    `<div class="folder-item">📁 ${f.name}</div>`
                ).join('');

                document.getElementById('selectedFolders').style.display = 'block';
                document.getElementById('pickBtn').textContent = 'Change Selection';
                document.getElementById('status').style.display = 'none';
            }
        }

        function confirmSelection() {
            if (selectedFolders.length === 0) {
                showStatus('error', 'Please select at least one folder.');
                return;
            }

            // Disable buttons while processing
            document.getElementById('pickBtn').disabled = true;
            document.querySelector('#selectedFolders button').disabled = true;
            showStatus('info', 'Saving selection...');

            // Send selected folders to our local server
            fetch('/callback', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    folders: selectedFolders,
                    access_token: accessToken
                })
            }).then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show big success state
                    document.querySelector('.container').innerHTML = `
                        <div style="text-align: center;">
                            <h1 style="color: #28a745; font-size: 48px; margin-bottom: 10px;">✅</h1>
                            <h2 style="color: #333;">Success!</h2>
                            <p style="color: #666; margin: 20px 0;">
                                Vectrola now has access to:<br>
                                <strong>${selectedFolders.map(f => f.name).join(', ')}</strong>
                            </p>
                            <p style="color: #999; font-size: 14px;">
                                You can close this window and return to the terminal.
                            </p>
                        </div>
                    `;
                } else {
                    showStatus('error', 'Error: ' + data.error);
                    document.getElementById('pickBtn').disabled = false;
                    document.querySelector('#selectedFolders button').disabled = false;
                }
            }).catch(err => {
                showStatus('error', 'Failed to save selection: ' + err);
                document.getElementById('pickBtn').disabled = false;
                document.querySelector('#selectedFolders button').disabled = false;
            });
        }

        function showStatus(type, message) {
            const status = document.getElementById('status');
            status.className = 'status ' + type;
            status.textContent = message;
        }
    </script>
</body>
</html>
"""


class PickerHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler for the picker page."""

    selected_folders = None
    access_token = None
    server_should_stop = False

    def __init__(self, *args, client_id: str, api_key: str, **kwargs):
        self.client_id = client_id
        self.api_key = api_key
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/' or self.path == '/picker':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Extract project number from client ID for APP_ID
            app_id = self.client_id.split('-')[0] if self.client_id else ''

            html = PICKER_HTML.replace('{{CLIENT_ID}}', self.client_id)
            html = html.replace('{{API_KEY}}', self.api_key or '')
            html = html.replace('{{APP_ID}}', app_id)

            self.wfile.write(html.encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/callback':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            try:
                data = json.loads(post_data.decode())
                PickerHandler.selected_folders = data.get('folders', [])
                PickerHandler.access_token = data.get('access_token')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())

                # Signal server to stop
                PickerHandler.server_should_stop = True

            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # Suppress logging


class StoppableServer(socketserver.TCPServer):
    """TCP Server that can be stopped from a request handler."""
    allow_reuse_address = True

    def serve_until_stopped(self):
        while not PickerHandler.server_should_stop:
            self.handle_request()


def open_folder_picker(client_id: str, api_key: Optional[str] = None) -> tuple[list[dict], str]:
    """Open Google Picker for folder selection.

    Args:
        client_id: Google OAuth Web App client ID
        api_key: Google API key (for Picker API)

    Returns:
        Tuple of (selected_folders, access_token)
        selected_folders is a list of dicts with 'id' and 'name' keys

    Raises:
        RuntimeError: If user cancels or an error occurs
    """
    # Reset state
    PickerHandler.selected_folders = None
    PickerHandler.access_token = None
    PickerHandler.server_should_stop = False

    # Create handler factory with credentials
    def handler_factory(*args, **kwargs):
        return PickerHandler(*args, client_id=client_id, api_key=api_key or '', **kwargs)

    # Find available port (must match authorized JavaScript origins in Google Console)
    server = None
    for port in [8080, 8081]:
        try:
            server = StoppableServer(('localhost', port), handler_factory)
            break
        except OSError:
            continue

    if server is None:
        raise RuntimeError("Could not start server on port 8080 or 8081. Make sure they're not in use.")

    # Open browser
    url = f'http://localhost:{port}/'
    print(f"Opening folder picker in browser...")
    print(f"(If browser doesn't open, visit: {url})\n")
    webbrowser.open(url)

    # Serve until callback received
    try:
        server.serve_until_stopped()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    if PickerHandler.selected_folders is None:
        raise RuntimeError("Folder selection cancelled or failed")

    return PickerHandler.selected_folders, PickerHandler.access_token
