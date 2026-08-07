"""Local filesystem artifact storage for raw FDA source artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

from apps.api.settings import get_settings


@dataclass(frozen=True)
class ArtifactWriteResult:
    """Metadata returned after writing an immutable source artifact."""

    object_key: str
    path: Path
    content_type: str
    sha256: str
    size_bytes: int


class LocalArtifactStore:
    """Path-safe local artifact store using atomic file replacement."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def ensure_store(self) -> None:
        """Create the root artifact directory when missing."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self,
        object_key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ArtifactWriteResult:
        """Write bytes under a relative artifact key and return source metadata."""
        destination = self.resolve_key(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Path | None = None
        with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as temp_file:
            temp_file.write(data)
            temp_path = Path(temp_file.name)

        try:
            os.replace(temp_path, destination)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

        return ArtifactWriteResult(
            object_key=object_key,
            path=destination,
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def read_bytes(self, object_key: str) -> bytes:
        """Read artifact bytes for a relative artifact key."""
        return self.resolve_key(object_key).read_bytes()

    def exists(self, object_key: str) -> bool:
        """Return whether an artifact exists for a relative artifact key."""
        return self.resolve_key(object_key).exists()

    def delete(self, object_key: str) -> None:
        """Delete an artifact by safe relative key when it exists."""
        path = self.resolve_key(object_key)
        if path.exists():
            path.unlink()

    def resolve_key(self, object_key: str) -> Path:
        """Resolve a POSIX-style artifact key below the configured base path."""
        key = PurePosixPath(object_key)
        if key.is_absolute() or not key.parts or any(part in {"", ".", ".."} for part in key.parts):
            raise ValueError(f"Artifact object_key must be a safe relative path: {object_key!r}")

        base_path = self.base_path.resolve()
        destination = (base_path / Path(*key.parts)).resolve()
        if not destination.is_relative_to(base_path):
            raise ValueError(f"Artifact object_key escapes base path: {object_key!r}")
        return destination


@lru_cache
def get_artifact_store() -> LocalArtifactStore:
    """Return the configured local artifact store."""
    settings = get_settings()
    if settings.object_store_backend != "local":
        raise ValueError("Only OBJECT_STORE_BACKEND=local is supported in the MVP")
    return LocalArtifactStore(settings.object_store_base_path)


def get_object_store_client() -> LocalArtifactStore:
    """Return the local artifact store for legacy client-factory imports."""
    return get_artifact_store()


def ensure_bucket(bucket_name: str | None = None) -> None:
    """Create the local artifact store root when it does not exist."""
    del bucket_name
    get_artifact_store().ensure_store()


def put_object_bytes(
    object_key: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
    bucket_name: str | None = None,
) -> ArtifactWriteResult:
    """Write bytes to local artifact storage under a relative artifact key."""
    del bucket_name
    return get_artifact_store().put_bytes(
        object_key,
        data,
        content_type=content_type,
    )