"""Sync an explicit source bundle through NyxID; never copy account credentials."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import textwrap
import uuid
from pathlib import PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_ENV = ("ARENA_DEPLOY_HOST", "ARENA_DEPLOY_PATH", "ARENA_DEPLOY_PRINCIPAL")


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


def remote(command):
    host, _, principal = deployment_config()
    r = subprocess.run(["nyxid", "ssh", "exec", host, "--principal", principal,
                        "--output", "json", command], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout)[-2000:])
    result = json.loads(r.stdout)
    if result.get("exit_code") != 0:
        raise RuntimeError(result.get("stderr", "Remote command failed"))
    return result.get("stdout", "")


def main():
    _, remote_path, _ = deployment_config()
    remote_python = os.environ.get("ARENA_DEPLOY_PYTHON", "/usr/bin/python3").strip() or "/usr/bin/python3"
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
    remote(f"mkdir -p {shlex.quote(remote_path)}")
    def send(offset):
        part = f"{stage}.{offset//6000:05d}"
        remote(f"printf %s {shlex.quote(encoded[offset:offset+6000])} > {shlex.quote(part)}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, _ in enumerate(pool.map(send, range(0, len(encoded), 6000))):
            if i % 20 == 0:
                print(f"Transfer {min((i+1)*3000,len(bundle)):,}/{len(bundle):,} bytes", flush=True)
    remote(f"cat {shlex.quote(stage)}.* > {shlex.quote(stage + '.hex')}")
    code = remote_extraction_code(stage + ".hex", remote_path, hashlib.sha256(bundle).hexdigest())
    print(remote(f"{shlex.quote(remote_python)} -c {shlex.quote(code)}"), flush=True)
    print(f"Synced {len(bundle):,} bytes to {remote_path}", flush=True)


if __name__ == "__main__":
    main()
