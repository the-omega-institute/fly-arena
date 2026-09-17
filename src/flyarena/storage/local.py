"""Atomic content-addressed local storage. Existing bytes are never replaced."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import tempfile


def validate_digest(value):
    if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid SHA-256 digest')
    return value


class LocalArtifactRepository:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put_if_absent(self, content: bytes, sha256: str | None = None) -> str:
        actual = hashlib.sha256(content).hexdigest()
        if sha256 is not None and actual != validate_digest(sha256):
            raise ValueError('Artifact content digest mismatch')
        destination = self.root / actual
        fd, name = tempfile.mkstemp(prefix='.object-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(name, destination)
            except FileExistsError:
                pass
            self.get_verified(actual)
        finally:
            os.unlink(name)
        return actual

    def get_verified(self, sha256: str) -> bytes:
        path = self.root / validate_digest(sha256)
        if path.is_symlink():
            raise ValueError('Artifact symlinks are forbidden')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != sha256:
            raise ValueError('Stored artifact digest mismatch')
        return content
