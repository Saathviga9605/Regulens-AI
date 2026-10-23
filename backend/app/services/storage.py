"""Private local document storage.

Layout under the configured root (never inside frontend/, never served statically):

    <root>/<key[0:2]>/<key>.pdf   stored documents (key = server-generated 32-char hex)
    <root>/.incoming/<uuid>.part  uploads being received (removed on any failure)
    <root>/.trash/<key>.pdf       files isolated during deletion until the DB commit succeeds

User-supplied filenames are never used in paths. Every resolved path is checked to stay under the root.
"""

import logging
import os
import re
import uuid
from pathlib import Path

logger = logging.getLogger("regulens.storage")

_KEY = re.compile(r"^[0-9a-f]{32}$")


class StorageError(Exception):
    pass


class DocumentStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.incoming = self.root / ".incoming"
        self.trash = self.root / ".trash"

    def ensure_dirs(self) -> None:
        for directory in (self.root, self.incoming, self.trash):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_key() -> str:
        return uuid.uuid4().hex

    def _inside_root(self, path: Path) -> Path:
        resolved = path.resolve()
        if self.root not in resolved.parents:
            raise StorageError("Resolved path escapes the storage root.")
        return resolved

    def path_for(self, key: str) -> Path:
        if not _KEY.fullmatch(key or ""):
            raise StorageError("Invalid storage key.")
        return self._inside_root(self.root / key[:2] / f"{key}.pdf")

    def new_temp_path(self) -> Path:
        self.incoming.mkdir(parents=True, exist_ok=True)
        return self._inside_root(self.incoming / f"{uuid.uuid4().hex}.part")

    def commit_temp(self, temp: Path, key: str) -> Path:
        destination = self.path_for(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp, destination)
        return destination

    def open_path(self, key: str | None) -> Path | None:
        """Existing file path for a key, or None if the key is invalid or the file is missing."""
        if key is None:
            return None
        try:
            path = self.path_for(key)
        except StorageError:
            return None
        return path if path.is_file() else None

    def isolate(self, key: str) -> Path | None:
        """Move a stored file to the trash area; None if it was already missing."""
        source = self.open_path(key)
        if source is None:
            return None
        self.trash.mkdir(parents=True, exist_ok=True)
        target = self._inside_root(self.trash / f"{key}.pdf")
        os.replace(source, target)
        return target

    def restore(self, key: str, isolated: Path) -> None:
        destination = self.path_for(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(isolated, destination)

    @staticmethod
    def discard(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove file from storage", extra={"error_type": type(exc).__name__})
