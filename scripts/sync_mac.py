"""Sync an explicit source bundle through NyxID; never copy account credentials."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import sys
import tarfile
import textwrap
import time
import uuid
from pathlib import PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_ENV = ("ARENA_DEPLOY_HOST", "ARENA_DEPLOY_PATH", "ARENA_DEPLOY_PRINCIPAL")
DEFAULT_SYNC_CHUNK_CHARS = 6000
MAX_SYNC_CHUNK_CHARS = 6000
DEFAULT_SYNC_MAX_RETRIES = 8
DEFAULT_SYNC_WORKERS = 1


def deployment_config():
    values = tuple(os.environ.get(name, "").strip() for name in DEPLOYMENT_ENV)
    missing = [name for name, value in zip(DEPLOYMENT_ENV, values) if not value]
    if missing:
        raise RuntimeError("Set " + ", ".join(missing) + " before running scripts/sync_mac.py")
    return values


def validate_archive_member(member):
    name = member.name
    posix = PurePosixPath(name)
    windows = PureWindowsPath(name)
    if (not name or posix.is_absolute() or windows.is_absolute() or windows.drive or
            ".." in posix.parts or ".." in windows.parts):
        raise ValueError(f"Unsafe archive path: {name!r}")
    if (member.issym() or member.islnk() or member.isdev() or member.isfifo() or
            not (member.isdir() or member.isfile())):
        raise ValueError(f"Unsafe archive member type: {name!r}")
    return member


def _confine_archive_member(member, destination):
    member = validate_archive_member(member)
    root = Path(destination).resolve()
    target = (root / member.name).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Unsafe archive path: {member.name!r}")
    return member


def safe_archive_filter(member, destination):
    member = _confine_archive_member(member, destination)
    data_filter = getattr(tarfile, "data_filter", None)
    if data_filter:
        try:
            return data_filter(member, destination)
        except tarfile.FilterError as exc:
            raise ValueError(f"Unsafe archive member: {member.name!r}") from exc
    return member


def safe_extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    members = [safe_archive_filter(member, destination) for member in archive.getmembers()]
    if "filter" in inspect.signature(archive.extractall).parameters:
        archive.extractall(destination, members=members, filter=safe_archive_filter)
    else:
        archive.extractall(destination, members=members)


def remote_extraction_code(archive_path, destination, bundle_sha256):
    """Return the Python 3.9+ extractor executed on the configured host."""
    return textwrap.dedent(f"""
        import hashlib
        import io
        import pathlib
        import tarfile

        archive_path = pathlib.Path({str(archive_path)!r})
        bundle = bytes.fromhex(archive_path.read_text())
        if hashlib.sha256(bundle).hexdigest() != {bundle_sha256!r}:
            raise RuntimeError("Source bundle checksum mismatch")
        destination = pathlib.Path({str(destination)!r})
        destination.mkdir(parents=True, exist_ok=True)

        def safe(member, root):
            posix = pathlib.PurePosixPath(member.name)
            windows = pathlib.PureWindowsPath(member.name)
            if (not member.name or posix.is_absolute() or windows.is_absolute() or
                    windows.drive or ".." in posix.parts or ".." in windows.parts or
                    member.issym() or member.islnk() or member.isdev() or member.isfifo() or
                    not (member.isdir() or member.isfile())):
                raise RuntimeError("Unsafe archive member: " + member.name)
            root = root.resolve()
            target = (root / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise RuntimeError("Unsafe archive path: " + member.name)
            data_filter = getattr(tarfile, "data_filter", None)
            if data_filter is not None:
                try:
                    member = data_filter(member, root)
                except Exception as exc:
                    raise RuntimeError("Unsafe archive member: " + member.name) from exc
            return member

        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
            members = [safe(member, destination) for member in archive.getmembers()]
            if getattr(tarfile, "data_filter", None) is not None:
                archive.extractall(destination, members=members, filter=safe)
            else:
                archive.extractall(destination, members=members)
        archive_path.unlink()
        print("Source bundle verified and synchronized")
    """).strip()


def _env_int(name, default, minimum=0, maximum=None):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bound = f" between {minimum} and {maximum}" if maximum is not None else f" >= {minimum}"
        raise RuntimeError(f"{name} must be an integer{bound}")
    return value


def sync_config():
    chunk_chars = _env_int(
        "ARENA_SYNC_CHUNK_CHARS", DEFAULT_SYNC_CHUNK_CHARS, minimum=1, maximum=MAX_SYNC_CHUNK_CHARS,
    )
    return {
        "chunk_chars": chunk_chars,
        "max_retries": _env_int("ARENA_SYNC_MAX_RETRIES", DEFAULT_SYNC_MAX_RETRIES, minimum=0),
        "workers": _env_int("ARENA_SYNC_WORKERS", DEFAULT_SYNC_WORKERS, minimum=1),
    }


def _status_from_payload(value):
    if isinstance(value, dict):
        if value.get("error_code") == 1005:
            return 429
        for key in ("status", "status_code", "http_status", "httpStatus", "code"):
            status = value.get(key)
            if isinstance(status, int):
                return status
        for nested in value.values():
            status = _status_from_payload(nested)
            if status is not None:
                return status
    elif isinstance(value, list):
        for nested in value:
            status = _status_from_payload(nested)
            if status is not None:
                return status
    return None


def _remote_status(stdout, stderr):
    for raw in (stdout, stderr):
        try:
            status = _status_from_payload(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            status = None
        if status is not None:
            return status
        if "error_code=1005" in raw or '"error_code":1005' in raw.replace(" ", ""):
            return 429
    return None


def _is_transient_status(status):
    return status == 429 or (status is not None and 500 <= status <= 599)


def _remote_error(result):
    output = ((result.stderr or "") + (result.stdout or ""))[-2000:]
    status = _remote_status(result.stdout, result.stderr)
    if result.returncode:
        return status, output
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("NyxID returned invalid JSON: " + output) from exc
    if _is_transient_status(status):
        return status, output
    if payload.get("exit_code") != 0:
        status = _status_from_payload(payload) or payload.get("exit_code")
        return status, str(payload.get("stderr") or payload.get("error") or output)[-2000:]
    return None, None


def remote(command):
    host, _, principal = deployment_config()
    max_retries = sync_config()["max_retries"]
    for attempt in range(max_retries + 1):
        r = subprocess.run(["nyxid", "ssh", "exec", host, "--principal", principal,
                            "--output", "json", command], capture_output=True, text=True)
        status, error = _remote_error(r)
        if error is None:
            result = json.loads(r.stdout)
            return result.get("stdout", "")
        if not _is_transient_status(status) or attempt >= max_retries:
            raise RuntimeError(error or "Remote command failed")
        delay = min(30.0, 0.5 * (2 ** min(attempt, 6)))
        delay += random.uniform(0.0, delay * 0.25)
        print(f"Remote transient failure ({status}); retry {attempt + 1}/{max_retries} in {delay:.2f}s",
              file=sys.stderr, flush=True)
        time.sleep(delay)


def cleanup_stage(stage):
    remote(f"rm -f -- {shlex.quote(stage)}.*")


def cleanup_command(remote_python, remote_path):
    script = f"{remote_path.rstrip('/')}/scripts/cleanup_deploy.py"
    return f"{shlex.quote(remote_python)} {shlex.quote(script)} --root {shlex.quote(remote_path)}"


def main():
    _, remote_path, _ = deployment_config()
    remote_python = os.environ.get("ARENA_DEPLOY_PYTHON", "/usr/bin/python3").strip() or "/usr/bin/python3"
    config = sync_config()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        for item in (sys.argv[1:] or ["src", "scripts", "docs", "web/dist", "deploy", "README.md", "pyproject.toml", "uv.lock"]):
            path = ROOT / item
            if not path.exists():
                continue
            if path.is_file():
                tar.add(path, arcname=item)
            else:
                for p in sorted(path.rglob("*")):
                    if p.is_file() and not any(part in {"__pycache__", "node_modules", ".venv"} for part in p.parts):
                        tar.add(p, arcname=str(p.relative_to(ROOT)))
    bundle = stream.getvalue()
    # Hex is an unambiguous binary transport alphabet for this command-only API.
    # It cannot be mistaken for shell keywords by the broker's lexical filter.
    encoded = bundle.hex()
    stage = f"{remote_path}/.sync-{uuid.uuid4().hex}"
    operation_error = None
    try:
        remote(f"mkdir -p {shlex.quote(remote_path)}")

        def send(chunk_number):
            offset = chunk_number * config["chunk_chars"]
            part = f"{stage}.{chunk_number:05d}"
            remote(f"printf %s {shlex.quote(encoded[offset:offset + config['chunk_chars']])} > {shlex.quote(part)}")

        offsets = range((len(encoded) + config["chunk_chars"] - 1) // config["chunk_chars"])
        total_chunks = len(offsets)
        print(f"Transfer 0/{total_chunks} chunks (0/{len(bundle):,} bytes)", flush=True)
        with ThreadPoolExecutor(max_workers=config["workers"]) as pool:
            for completed, _ in enumerate(pool.map(send, offsets), start=1):
                if (completed == 1 or completed == total_chunks or
                        completed % max(1, total_chunks // 20) == 0):
                    sent = min(len(bundle), (completed * config["chunk_chars"]) // 2)
                    print(f"Transfer {completed}/{total_chunks} chunks ({sent:,}/{len(bundle):,} bytes)",
                          flush=True)
        remote(f"cat {shlex.quote(stage)}.* > {shlex.quote(stage + '.hex')}")
        code = remote_extraction_code(stage + ".hex", remote_path, hashlib.sha256(bundle).hexdigest())
        extraction_output = remote(f"{shlex.quote(remote_python)} -c {shlex.quote(code)}")
    except BaseException as exc:
        operation_error = exc
        raise
    finally:
        try:
            cleanup_stage(stage)
        except Exception as cleanup_error:
            print(f"Warning: could not remove sync staging files: {cleanup_error}",
                  file=sys.stderr, flush=True)
            if operation_error is None:
                raise
    print(extraction_output, flush=True)
    print(f"Synced {len(bundle):,} bytes to {remote_path}", flush=True)
    print(f"Cleanup dry-run command: {cleanup_command(remote_python, remote_path)}", flush=True)


if __name__ == "__main__":
    main()
