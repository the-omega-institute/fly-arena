import asyncio
import ast
import hashlib
import io
import importlib.util
import json
from types import SimpleNamespace
import subprocess
import sys
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


async def post_chunks_with_headers(app, chunks, headers):
    async def body():
        for chunk in chunks:
            yield chunk

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/identities", content=body(), headers=headers)


def test_chunked_request_limit_is_enforced_before_body_buffering(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    chunks = [b"x" * MAX_REQUEST_BYTES, b"x"]
    response = asyncio.run(post_chunks(app, chunks))
    assert response.status_code == 413
    assert response.json() == {"detail": "Request exceeds 8 MB limit"}


def identity_payload(size):
    prefix = b'{"name":"boundary"}'
    assert len(prefix) <= size
    return prefix + b" " * (size - len(prefix))


def test_exact_chunked_request_limit_is_accepted(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    response = asyncio.run(post_chunks(app, [identity_payload(MAX_REQUEST_BYTES)]))
    assert response.status_code == 201
    assert response.json()["name"] == "boundary"


def test_exact_content_length_request_limit_is_accepted(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    response = asyncio.run(post_chunks_with_headers(
        app, [identity_payload(MAX_REQUEST_BYTES)],
        {"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES)},
    ))
    assert response.status_code == 201
    assert response.json()["name"] == "boundary"


def test_content_length_over_limit_is_rejected_before_body_read(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    response = asyncio.run(post_chunks_with_headers(
        app, [b'{"name":"small"}'],
        {"content-type": "application/json", "content-length": str(MAX_REQUEST_BYTES + 1)},
    ))
    assert response.status_code == 413


def test_content_length_smaller_than_streamed_body_is_rejected(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    response = asyncio.run(post_chunks_with_headers(
        app, [b'{"name":"streamed"}'],
        {"content-type": "application/json", "content-length": "2"},
    ))
    assert response.status_code == 413


def test_chunked_request_body_is_replayed_to_fastapi(tmp_path):
    app = create_app(with_worker=False, store=Store(tmp_path / "store"), auth_config=AuthConfig())
    response = asyncio.run(post_chunks(app, [b'{"name":', b'"streamed"}']))
    assert response.status_code == 201
    assert response.json()["name"] == "streamed"


def archive_bytes(*members):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for member in members:
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


def test_safe_extract_rejects_preexisting_destination_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "extract"
    destination.mkdir()
    (destination / "nested").symlink_to(outside, target_is_directory=True)
    member = tarfile.TarInfo("nested/result.txt")
    member.size = len(b"payload")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes(member)), mode="r:gz") as archive:
        with pytest.raises(ValueError, match="Unsafe archive"):
            safe_extract(archive, destination)
    assert not (outside / "result.txt").exists()


def test_generated_remote_extractor_compiles_and_extracts(tmp_path):
    member = tarfile.TarInfo("nested/result.txt")
    member.size = len(b"payload")
    archive = archive_bytes(member)
    stage = tmp_path / "bundle.hex"
    stage.write_text(archive.hex())
    destination = tmp_path / "remote"
    code = sync_mac.remote_extraction_code(stage, destination, hashlib.sha256(archive).hexdigest())
    ast.parse(code, "<remote-extractor>", feature_version=(3, 9))
    compile(code, "<remote-extractor>", "exec")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (destination / "nested/result.txt").read_text() == "payload"
    assert not stage.exists()


@pytest.mark.parametrize("kind", ["absolute", "traversal", "symlink", "hardlink", "device", "fifo"])
def test_generated_remote_extractor_rejects_unsafe_members(tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    names = {
        "absolute": str(outside / "absolute.txt"),
        "traversal": "../traversal.txt",
        "symlink": "link",
        "hardlink": "hard-link",
        "device": "device",
        "fifo": "fifo",
    }
    member = tarfile.TarInfo(names[kind])
    if kind == "symlink":
        member.type = tarfile.SYMTYPE
        member.linkname = "../outside/linked.txt"
    elif kind == "hardlink":
        member.type = tarfile.LNKTYPE
        member.linkname = "../outside/linked.txt"
    elif kind == "device":
        member.type = tarfile.CHRTYPE
    elif kind == "fifo":
        member.type = tarfile.FIFOTYPE
    else:
        member.size = len(b"payload")
    before = tarfile.TarInfo("before.txt")
    before.size = len(b"payload")
    archive = archive_bytes(before, member)
    stage = tmp_path / "bundle.hex"
    stage.write_text(archive.hex())
    destination = tmp_path / "remote"
    code = sync_mac.remote_extraction_code(stage, destination, hashlib.sha256(archive).hexdigest())
    ast.parse(code, "<remote-extractor>", feature_version=(3, 9))
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert not (destination / "before.txt").exists()
    assert not any(outside.iterdir())


def test_generated_remote_extractor_rejects_preexisting_symlink_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "remote"
    destination.mkdir()
    (destination / "nested").symlink_to(outside, target_is_directory=True)
    member = tarfile.TarInfo("nested/result.txt")
    member.size = len(b"payload")
    archive = archive_bytes(member)
    stage = tmp_path / "bundle.hex"
    stage.write_text(archive.hex())
    code = sync_mac.remote_extraction_code(stage, destination, hashlib.sha256(archive).hexdigest())
    ast.parse(code, "<remote-extractor>", feature_version=(3, 9))
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert not (outside / "result.txt").exists()


def test_remote_wires_configured_host_and_principal(monkeypatch):
    values = {
        "ARENA_DEPLOY_HOST": "configured-host",
        "ARENA_DEPLOY_PATH": "/srv/arena",
        "ARENA_DEPLOY_PRINCIPAL": "configured-principal",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"exit_code": 0, "stdout": "ok"}))

    monkeypatch.setattr(sync_mac.subprocess, "run", run)
    assert sync_mac.remote("printf ok") == "ok"
    assert calls[0][0] == [
        "nyxid", "ssh", "exec", "configured-host", "--principal", "configured-principal",
        "--output", "json", "printf ok",
    ]


@pytest.mark.parametrize("missing", sync_mac.DEPLOYMENT_ENV)
def test_deployment_config_rejects_partial_environment(monkeypatch, missing):
    for name in sync_mac.DEPLOYMENT_ENV:
        monkeypatch.setenv(name, "configured-" + name.removeprefix("ARENA_DEPLOY_"))
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
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


def test_sync_main_uses_configured_deployment_path(monkeypatch, tmp_path):
    monkeypatch.delenv("ARENA_DEPLOY_PYTHON", raising=False)
    for name, value in {
        "ARENA_DEPLOY_HOST": "configured-host",
        "ARENA_DEPLOY_PATH": str(tmp_path / "remote-root"),
        "ARENA_DEPLOY_PRINCIPAL": "configured-principal",
    }.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "payload.txt").write_text("payload")
    monkeypatch.setattr(sync_mac, "ROOT", tmp_path)
    monkeypatch.setattr(sync_mac.sys, "argv", ["sync_mac.py", "payload.txt"])
    commands = []
    monkeypatch.setattr(sync_mac, "remote", lambda command: commands.append(command) or "")

    sync_mac.main()

    assert any(command.startswith("mkdir -p") and str(tmp_path / "remote-root") in command for command in commands)
    assert any("/usr/bin/python3 -c" in command and str(tmp_path / "remote-root") in command for command in commands)


def test_sync_main_uses_configured_remote_python(monkeypatch, tmp_path):
    for name, value in {
        "ARENA_DEPLOY_HOST": "configured-host",
        "ARENA_DEPLOY_PATH": str(tmp_path / "remote-root"),
        "ARENA_DEPLOY_PRINCIPAL": "configured-principal",
        "ARENA_DEPLOY_PYTHON": "/opt/arena/.venv/bin/python",
    }.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "payload.txt").write_text("payload")
    monkeypatch.setattr(sync_mac, "ROOT", tmp_path)
    monkeypatch.setattr(sync_mac.sys, "argv", ["sync_mac.py", "payload.txt"])
    commands = []
    monkeypatch.setattr(sync_mac, "remote", lambda command: commands.append(command) or "")

    sync_mac.main()

    assert any("/opt/arena/.venv/bin/python -c" in command for command in commands)
