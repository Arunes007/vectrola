"""Google Drive API client for listing and downloading audio files."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn


@dataclass
class DriveFile:
    """Represents an audio file in Google Drive."""

    id: str
    name: str
    mime_type: str
    size_bytes: int
    parent_path: str  # e.g., "/Music/Bollywood"
    modified_time: Optional[str] = None

    @property
    def extension(self) -> str:
        """Get file extension based on mime type."""
        mime_to_ext = {
            "audio/mpeg": ".mp3",
            "audio/flac": ".flac",
            "audio/x-flac": ".flac",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/ogg": ".ogg",
            "audio/webm": ".webm",
            "video/webm": ".webm",
        }
        return mime_to_ext.get(self.mime_type, "")

    @property
    def size_mb(self) -> float:
        """File size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    @property
    def is_folder(self) -> bool:
        """Check if this is a folder."""
        return self.mime_type == "application/vnd.google-apps.folder"


class DriveClient:
    """Google Drive API client for audio file operations."""

    # Mime types we consider audio files
    AUDIO_MIMETYPES = {
        "audio/mpeg",      # .mp3
        "audio/flac",      # .flac
        "audio/x-flac",    # .flac (alternative)
        "audio/wav",       # .wav
        "audio/x-wav",     # .wav (alternative)
        "audio/mp4",       # .m4a
        "audio/x-m4a",     # .m4a (alternative)
        "audio/ogg",       # .ogg
        "audio/webm",      # .webm (audio)
        "video/webm",      # .webm (often audio-only from YouTube)
    }

    def __init__(self, credentials=None):
        """Initialize Drive client.

        Args:
            credentials: google.oauth2.credentials.Credentials
                        If None, loads from saved credentials.
        """
        self._credentials = credentials
        self._service = None

    @property
    def service(self):
        """Lazy-load Drive service."""
        if self._service is None:
            from googleapiclient.discovery import build

            if self._credentials is None:
                from .auth import get_credentials

                self._credentials = get_credentials()
                if self._credentials is None:
                    raise RuntimeError(
                        "Not authenticated with Google Drive. "
                        "Run 'vectrola gdrive auth' first."
                    )

            self._service = build("drive", "v3", credentials=self._credentials)

        return self._service

    def resolve_path(self, path: str) -> Optional[str]:
        """Convert a Drive path to folder ID.

        Args:
            path: Drive path like "/Music/Bollywood" or "root"

        Returns:
            Folder ID or None if path not found
        """
        if path in ("/", "", "root"):
            return "root"

        # Normalize path
        path = path.strip("/")
        parts = [p for p in path.split("/") if p]

        current_id = "root"

        for part in parts:
            # Search for folder with this name in current parent
            query = (
                f"name = '{part}' and "
                f"'{current_id}' in parents and "
                f"trashed = false"
            )

            response = (
                self.service.files()
                .list(q=query, spaces="drive", fields="files(id, mimeType)")
                .execute()
            )

            files = response.get("files", [])
            if not files:
                return None

            current_id = files[0]["id"]

        return current_id

    def list_contents(
        self,
        path: str = "/",
    ) -> Iterator[DriveFile]:
        """List folders and audio files in a Drive folder (non-recursive).

        Args:
            path: Drive path to list (e.g., "/Music")

        Yields:
            DriveFile objects for folders and audio files (folders first)
        """
        folder_id = self.resolve_path(path)
        if folder_id is None:
            raise FileNotFoundError(f"Drive path not found: {path}")

        query = f"'{folder_id}' in parents and trashed = false"

        folders = []
        files = []

        page_token = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                    pageToken=page_token,
                    pageSize=100,
                )
                .execute()
            )

            for item in response.get("files", []):
                mime_type = item.get("mimeType", "")
                normalized_path = path.strip("/")

                if mime_type == "application/vnd.google-apps.folder":
                    folders.append(DriveFile(
                        id=item["id"],
                        name=item["name"],
                        mime_type=mime_type,
                        size_bytes=0,
                        parent_path=normalized_path,
                        modified_time=item.get("modifiedTime"),
                    ))
                elif mime_type in self.AUDIO_MIMETYPES:
                    files.append(DriveFile(
                        id=item["id"],
                        name=item["name"],
                        mime_type=mime_type,
                        size_bytes=int(item.get("size", 0)),
                        parent_path=normalized_path,
                        modified_time=item.get("modifiedTime"),
                    ))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        # Yield folders first, then files (both sorted by name)
        for folder in sorted(folders, key=lambda x: x.name.lower()):
            yield folder
        for file in sorted(files, key=lambda x: x.name.lower()):
            yield file

    def list_files(
        self,
        path: str = "/",
        recursive: bool = True,
    ) -> Iterator[DriveFile]:
        """List audio files in a Drive folder.

        Args:
            path: Drive path to list (e.g., "/Music/Bollywood")
            recursive: If True, include files in subfolders

        Yields:
            DriveFile objects for each audio file found
        """
        folder_id = self.resolve_path(path)
        if folder_id is None:
            raise FileNotFoundError(f"Drive path not found: {path}")

        yield from self._list_folder(folder_id, path.strip("/"), recursive)

    def _list_folder(
        self,
        folder_id: str,
        path: str,
        recursive: bool,
    ) -> Iterator[DriveFile]:
        """Recursively list folder contents."""
        query = f"'{folder_id}' in parents and trashed = false"

        page_token = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                    pageToken=page_token,
                    pageSize=100,
                )
                .execute()
            )

            for item in response.get("files", []):
                mime_type = item.get("mimeType", "")

                # Handle folders (recursive)
                if mime_type == "application/vnd.google-apps.folder":
                    if recursive:
                        subfolder_path = f"{path}/{item['name']}" if path else item["name"]
                        yield from self._list_folder(item["id"], subfolder_path, recursive)

                # Handle audio files
                elif mime_type in self.AUDIO_MIMETYPES:
                    yield DriveFile(
                        id=item["id"],
                        name=item["name"],
                        mime_type=mime_type,
                        size_bytes=int(item.get("size", 0)),
                        parent_path=path,
                        modified_time=item.get("modifiedTime"),
                    )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def download_file(
        self,
        file: DriveFile,
        dest_dir: Path,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Path:
        """Download a file from Drive.

        Args:
            file: DriveFile to download
            dest_dir: Directory to save the file
            progress_callback: Optional callback(progress_fraction)

        Returns:
            Path to downloaded file
        """
        from googleapiclient.http import MediaIoBaseDownload
        import io

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file.name

        request = self.service.files().get_media(fileId=file.id)

        with open(dest_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False

            while not done:
                status, done = downloader.next_chunk()
                if progress_callback and status:
                    progress_callback(status.progress())

        return dest_path

    def download_file_with_progress(
        self,
        file: DriveFile,
        dest_dir: Path,
    ) -> Path:
        """Download a file with Rich progress bar.

        Args:
            file: DriveFile to download
            dest_dir: Directory to save the file

        Returns:
            Path to downloaded file
        """
        from googleapiclient.http import MediaIoBaseDownload

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file.name

        request = self.service.files().get_media(fileId=file.id)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(f"Downloading {file.name}", total=file.size_bytes)

            with open(dest_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False

                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress.update(task, completed=int(status.progress() * file.size_bytes))

        return dest_path

    def get_quota(self) -> dict:
        """Get storage quota information.

        Returns:
            Dict with 'limit', 'usage', 'usageInDrive' in bytes
        """
        about = self.service.about().get(fields="storageQuota").execute()
        return about.get("storageQuota", {})

    def get_user_info(self) -> dict:
        """Get current user information.

        Returns:
            Dict with 'user' containing 'displayName', 'emailAddress'
        """
        about = self.service.about().get(fields="user").execute()
        return about.get("user", {})
