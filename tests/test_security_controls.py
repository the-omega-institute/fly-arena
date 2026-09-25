import asyncio
import io
import importlib.util
import tarfile
from pathlib import Path

import httpx
import pytest

from flyarena.api import MAX_REQUEST_BYTES, create_app
from flyarena.auth import AuthConfig
from flyarena.store import Store


_sync_spec = importlib.util.spec_from_file_location("sync_mac", Path(__file__).parents[1] / "scripts/sync_mac.py")
sync_mac = importlib.util.module_from_spec(_sync_spec)
_sync_spec.loader.exec_module(sync_mac)
deployment_config = sync_mac.deployment_config
safe_extract = sync_mac.safe_extract


async def post_chunks(app, chunks):
    async def body():
        for chunk in chunks:
            yield chunk

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/identities", content=body(), headers={"content-type": "application/json"})


def test_chunked_request_limit_is_enforced_before_body_buffering(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    chunks = [b"x" * 1024 for _ in range(MAX_REQUEST_BYTES // 1024 + 1)]
    response = asyncio.run(post_chunks(app, chunks))
    assert response.status_code == 413
    assert response.json() == {"detail": "Request exceeds 8 MB limit"}


def test_chunked_request_body_is_replayed_to_fastapi(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    response = asyncio.run(post_chunks(app, [b'{"name":', b'"streamed"}']))
    assert response.status_code == 201
    assert response.json()["name"] == "streamed"


def archive_bytes(member):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        archive.addfile(member, io.BytesIO(b"payload") if member.isfile() else None)
    return stream.getvalue()


@pytest.mark.parametrize("member", [
    pytest.param(tarfile.TarInfo("../escape"), id="parent-traversal"),
    pytest.param(tarfile.TarInfo("/absolute"), id="absolute"),
    pytest.param(tarfile.TarInfo("link"), id="symlink"),
    pytest.param(tarfile.TarInfo("hard-link"), id="hardlink"),
    pytest.param(tarfile.TarInfo("device"), id="device"),
])
def test_safe_extract_rejects_unsafe_archive_members(tmp_path, member):
    if member.name == "link":
        member.type = tarfile.SYMTYPE
        member.linkname = "target"
    elif member.name == "hard-link":
        member.type = tarfile.LNKTYPE
        member.linkname = "target"
    elif member.name == "device":
        member.type = tarfile.CHRTYPE
    else:
        member.size = len(b"payload")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes(member)), mode="r:gz") as archive:
        with pytest.raises(ValueError, match="Unsafe archive"):
            safe_extract(archive, tmp_path / "extract")


def test_safe_extract_allows_regular_files(tmp_path):
    member = tarfile.TarInfo("nested/result.txt")
    member.size = len(b"payload")
    destination = tmp_path / "extract"
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes(member)), mode="r:gz") as archive:
        safe_extract(archive, destination)
    assert (destination / "nested/result.txt").read_text() == "payload"


def test_deployment_config_requires_all_environment_values(monkeypatch):
    for name in ("ARENA_DEPLOY_HOST", "ARENA_DEPLOY_PATH", "ARENA_DEPLOY_PRINCIPAL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="ARENA_DEPLOY_HOST"):
        deployment_config()


def test_deployment_config_reads_environment(monkeypatch):
    values = {
        "ARENA_DEPLOY_HOST": "configured-host",
        "ARENA_DEPLOY_PATH": "/srv/arena",
        "ARENA_DEPLOY_PRINCIPAL": "configured-principal",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert deployment_config() == tuple(values.values())
