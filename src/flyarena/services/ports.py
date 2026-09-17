"""Narrow application ports; no provider, authentication, or HTTP imports."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Capability:
    id: str
    available: bool
    capabilities: tuple[str, ...] = ()
    reason: str | None = None


@runtime_checkable
class ArtifactRepository(Protocol):
    def put_if_absent(self, content: bytes, sha256: str | None = None) -> str: ...
    def get_verified(self, sha256: str) -> bytes: ...


@runtime_checkable
class IdentityProvider(Protocol):
    def authorization_url(self, flow: dict) -> str: ...
    def exchange(self, code: str, flow: dict) -> dict: ...
    def close(self) -> None: ...


@runtime_checkable
class ExperimentExecutor(Protocol):
    def descriptor(self) -> Capability: ...
    def execute(self, fly: dict, probe_id: str, seed: int, duration_seconds: int, output: Path) -> dict: ...


@runtime_checkable
class ResearchRepository(Protocol):
    def get(self, ident: str) -> dict | None: ...
    def admit(self, owner, spec, subjects, conditions, key=None) -> dict: ...
    def claim(self) -> tuple[str, str, int] | None: ...
    def heartbeat(self, ident, lease, generation) -> None: ...
    def finish(self, ident, lease, generation, reports, comparison=None, error=None) -> None: ...


def require_capabilities(executor: ExperimentExecutor, required=()):
    descriptor = executor.descriptor()
    if not descriptor.available:
        raise ValueError(descriptor.reason or 'Executor unavailable')
    missing = set(required)-set(descriptor.capabilities)
    if missing:
        raise ValueError('Missing executor capabilities: '+', '.join(sorted(missing)))
    return descriptor
