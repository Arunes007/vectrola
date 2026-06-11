"""Google Drive integration for Vectrola.

Provides OAuth authentication and file operations for ingesting music from Google Drive.
"""

from .auth import (
    authenticate,
    is_authenticated,
    get_credentials,
    logout,
    setup_custom_credentials,
    get_allowed_folders,
    add_allowed_folder,
    remove_allowed_folder,
    clear_allowed_folders,
    is_folder_allowed,
    is_path_allowed,
)
from .client import DriveClient

__all__ = [
    "authenticate",
    "is_authenticated",
    "get_credentials",
    "logout",
    "setup_custom_credentials",
    "get_allowed_folders",
    "add_allowed_folder",
    "remove_allowed_folder",
    "clear_allowed_folders",
    "is_folder_allowed",
    "is_path_allowed",
    "DriveClient",
]
