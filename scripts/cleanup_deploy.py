"""Remove only explicitly allowlisted, completed deployment artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import fnmatch
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


STAGING_AGE_SECONDS = 60 * 60
DEFAULT_KEEP_RELEASES = 2
DEFAULT_IMPORT_AGE_DAYS = 7
DEFAULT_KEEP_BACKUPS = 5


@dataclass(frozen=True)
class CleanupItem:
    path: Path
    category: str
    size: int


def _absolute_without_following(path):
    return Path(os.path.abspath(os.fspath(path)))


def validate_root(root):
    root = _absolute_without_following(root)
    try:
        info = root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Deployment root does not exist: {root}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RuntimeError(f"Refusing symlink deployment root: {root}")
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"Deployment root is not a directory: {root}")
    return root


def _children(directory):
    try:
        return sorted(directory.iterdir(), key=lambda path: path.name)
    except FileNotFoundError:
        return []


def _regular_file(path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISREG(mode)


def _directory(path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISDIR(mode)


def _old_enough(path, cutoff):
    try:
        return path.lstat().st_mtime < cutoff
    except FileNotFoundError:
        return False


def _size_without_following(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return 0
    if stat.S_ISLNK(info.st_mode) or stat.S_ISREG(info.st_mode):
        return info.st_size
    if not stat.S_ISDIR(info.st_mode):
        return 0
    return sum(_size_without_following(child) for child in _children(path))


def _item(path, category):
    return CleanupItem(path=path, category=category, size=_size_without_following(path))


def _running_process_uses(path):
    """Return whether a live process has the candidate as cwd or a command argument."""
    candidate = _absolute_without_following(path)
    proc = Path("/proc")
    if proc.is_dir():
        for process in _children(proc):
            if not process.name.isdigit():
                continue
            try:
                cwd = Path(os.readlink(process / "cwd"))
                if cwd == candidate or candidate in cwd.parents:
                    return True
                command = (process / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
                if str(candidate) in command:
                    return True
            except (FileNotFoundError, PermissionError, OSError):
                continue
        return False
    try:
        result = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False)
    except OSError:
        result = None
    if result is not None and any(str(candidate) in line for line in result.stdout.splitlines()):
        return True
    try:
        cwd_result = subprocess.run(
            ["lsof", "-a", "-d", "cwd", "+D", str(candidate)],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return False
    return bool(cwd_result.stdout.strip())


def _candidate_names(root):
    return (f"{root.name}-candidate-*", "fly-arena-candidate-*")


def find_cleanup_items(root, *, now=None, keep_releases=DEFAULT_KEEP_RELEASES,
                       import_age_days=DEFAULT_IMPORT_AGE_DAYS, keep_backups=DEFAULT_KEEP_BACKUPS):
    root = validate_root(root)
    if now is None:
        now = time.time()
    if keep_releases < 0 or keep_backups < 0 or import_age_days < 0:
        raise ValueError("retention values must be nonnegative")

    items = []
    staging_cutoff = now - STAGING_AGE_SECONDS
    for path in _children(root):
        if path.name.startswith(".sync-") and _regular_file(path) and _old_enough(path, staging_cutoff):
            items.append(_item(path, "sync staging"))

    var = root / "var"
    if _directory(var):
        releases = var / "releases"
        if _directory(releases):
            release_dirs = [path for path in _children(releases) if _directory(path)]
            release_dirs.sort(key=lambda path: path.lstat().st_mtime_ns, reverse=True)
            items.extend(_item(path, "old release") for path in release_dirs[keep_releases:])

        import_cutoff = now - import_age_days * 24 * 60 * 60
        items.extend(
            _item(path, "completed import staging")
            for path in _children(var)
            if _directory(path) and fnmatch.fnmatch(path.name, "*-import-*") and _old_enough(path, import_cutoff)
        )

        backups = [
            path for path in _children(var)
            if _regular_file(path) and fnmatch.fnmatch(path.name, "arena-backup-*.sqlite3")
        ]
        backups.sort(key=lambda path: path.lstat().st_mtime_ns, reverse=True)
        items.extend(_item(path, "old SQLite backup") for path in backups[keep_backups:])

    parent = root.parent
    patterns = _candidate_names(root)
    for path in _children(parent):
        if path == root or not _directory(path) or not any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
            continue
        if not _running_process_uses(path):
            items.append(_item(path, "stale candidate checkout"))
    return items


def _remove_without_following(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        path.unlink()
        return
    for child in _children(path):
        _remove_without_following(child)
    path.rmdir()


def _format_size(size):
    return f"{size:,}"


def run(root, *, apply=False, keep_releases=DEFAULT_KEEP_RELEASES,
        import_age_days=DEFAULT_IMPORT_AGE_DAYS, keep_backups=DEFAULT_KEEP_BACKUPS, now=None, output=None):
    output = output or sys.stdout
    items = find_cleanup_items(
        root, now=now, keep_releases=keep_releases, import_age_days=import_age_days, keep_backups=keep_backups,
    )
    action = "delete" if apply else "dry-run"
    print(f"{'PATH':<60} {'CATEGORY':<28} {'SIZE':>12} ACTION", file=output)
    print(f"{'-' * 60} {'-' * 28} {'-' * 12} {'-' * 10}", file=output)
    total = 0
    for item in items:
        total += item.size
        print(f"{str(item.path):<60} {item.category:<28} {_format_size(item.size):>12} {action}", file=output)
        if apply:
            _remove_without_following(item.path)
    print(f"Total bytes: {_format_size(total)}", file=output)
    return items


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None,
                        help="deployment root; defaults to ARENA_DEPLOY_PATH")
    parser.add_argument("--apply", action="store_true", help="delete the allowlisted artifacts")
    parser.add_argument("--keep-releases", type=int, default=DEFAULT_KEEP_RELEASES)
    parser.add_argument("--import-age-days", type=int, default=DEFAULT_IMPORT_AGE_DAYS)
    parser.add_argument("--keep-backups", type=int, default=DEFAULT_KEEP_BACKUPS)
    args = parser.parse_args(argv)
    if args.root is None:
        configured = os.environ.get("ARENA_DEPLOY_PATH", "").strip()
        if not configured:
            parser.error("set ARENA_DEPLOY_PATH or pass --root")
        args.root = Path(configured)
    return args


def main(argv=None):
    args = parse_args(argv)
    run(args.root, apply=args.apply, keep_releases=args.keep_releases,
        import_age_days=args.import_age_days, keep_backups=args.keep_backups)


if __name__ == "__main__":
    main()
