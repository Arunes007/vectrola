"""Google Drive integration for Vectrola.

Provides OAuth authentication and file operations for syncing music to Google Drive.
"""

from .auth import (
    authenticate,
    is_authenticated,
    get_credentials,
    logout,
)
from .client import DriveClient

__all__ = [
    "authenticate",
    "is_authenticated",
    "get_credentials",
    "logout",
    "DriveClient",
]

