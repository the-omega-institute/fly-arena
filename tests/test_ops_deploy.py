import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import time

import pytest


def load_script(name):
    path = Path(__file__).parents[1] / "scripts" / name
    module_name = name.replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


sync_mac = load_script("sync_mac.py")
cleanup_deploy = load_script("cleanup_deploy.py")


def deployment_env(monkeypatch, tmp_path):
    values = {
        "ARENA_DEPLOY_HOST": "configured-host",
        "ARENA_DEPLOY_PATH": str(tmp_path / "remote-root"),
        "ARENA_DEPLOY_PRINCIPAL": "configured-principal",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_remote_retries_rate_limit_and_transient_5xx(monkeypatch, tmp_path):
    deployment_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ARENA_SYNC_MAX_RETRIES", "3")
    responses = iter([
        SimpleNamespace(returncode=1, stderr="", stdout=json.dumps({"error": "rate_limited", "error_code": 1005})),
        SimpleNamespace(returncode=1, stderr="", stdout=json.dumps({"status": 503, "error": "busy"})),
        SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"exit_code": 0, "stdout": "ok"})),
    ])
    calls = []
    sleeps = []

    def run(command, **kwargs):
        calls.append(command)
        return next(responses)

    monkeypatch.setattr(sync_mac.subprocess, "run", run)
    monkeypatch.setattr(sync_mac.random, "uniform", lambda lower, upper: 0.0)
    monkeypatch.setattr(sync_mac.time, "sleep", sleeps.append)

    assert sync_mac.remote("printf ok") == "ok"
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_sync_configuration_is_env_controlled(monkeypatch):
    monkeypatch.setenv("ARENA_SYNC_CHUNK_CHARS", "1234")
    monkeypatch.setenv("ARENA_SYNC_MAX_RETRIES", "4")
    monkeypatch.setenv("ARENA_SYNC_WORKERS", "3")

    assert sync_mac.sync_config() == {"chunk_chars": 1234, "max_retries": 4, "workers": 3}


def test_remote_gives_up_after_configured_retries(monkeypatch, tmp_path):
    deployment_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ARENA_SYNC_MAX_RETRIES", "2")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stderr="", stdout=json.dumps({"status": 429, "error": "busy"}))

    monkeypatch.setattr(sync_mac.subprocess, "run", run)
    monkeypatch.setattr(sync_mac.random, "uniform", lambda lower, upper: 0.0)
    monkeypatch.setattr(sync_mac.time, "sleep", lambda delay: None)

    with pytest.raises(RuntimeError, match="busy"):
        sync_mac.remote("printf ok")
    assert len(calls) == 3


def configure_sync_main(monkeypatch, tmp_path):
    deployment_env(monkeypatch, tmp_path)
    monkeypatch.delenv("ARENA_DEPLOY_PYTHON", raising=False)
    monkeypatch.setenv("ARENA_SYNC_WORKERS", "1")
    monkeypatch.setenv("ARENA_SYNC_CHUNK_CHARS", "6000")
    (tmp_path / "payload.txt").write_text("payload")
    monkeypatch.setattr(sync_mac, "ROOT", tmp_path)
    monkeypatch.setattr(sync_mac.sys, "argv", ["sync_mac.py", "payload.txt"])


def test_sync_cleans_stage_after_upload_failure(monkeypatch, tmp_path):
    configure_sync_main(monkeypatch, tmp_path)
    commands = []

    def remote(command):
        commands.append(command)
        if command.startswith("printf %s"):
            raise RuntimeError("upload failed")
        return ""

    monkeypatch.setattr(sync_mac, "remote", remote)

    with pytest.raises(RuntimeError, match="upload failed"):
        sync_mac.main()
    cleanup = [command for command in commands if command.startswith("rm -f --")]
    assert len(cleanup) == 1
    assert ".sync-" in cleanup[0]
    assert not any("Cleanup dry-run command:" in command for command in commands)


def test_sync_cleans_stage_after_success_and_prints_cleanup_command(monkeypatch, tmp_path, capsys):
    configure_sync_main(monkeypatch, tmp_path)
    commands = []
    monkeypatch.setattr(sync_mac, "remote", lambda command: commands.append(command) or "")

    sync_mac.main()

    cleanup_indexes = [index for index, command in enumerate(commands) if command.startswith("rm -f --")]
    extraction_indexes = [index for index, command in enumerate(commands) if " -c " in command]
    assert len(cleanup_indexes) == 1
    assert extraction_indexes and cleanup_indexes[0] > extraction_indexes[-1]
    output = capsys.readouterr().out
    assert "Cleanup dry-run command:" in output
    assert f"{tmp_path / 'remote-root'}/scripts/cleanup_deploy.py" in output
    assert "--root" in output


def set_mtime(path, timestamp):
    if not path.exists():
        path.touch()
    os.utime(path, (timestamp, timestamp))


def make_cleanup_tree(tmp_path):
    root = tmp_path / "fly-arena"
    root.mkdir()
    now = time.time()
    old = now - 8 * 24 * 60 * 60

    staging_old = root / ".sync-old.00000"
    set_mtime(staging_old, now - 2 * 60 * 60)
    staging_new = root / ".sync-new.00000"
    set_mtime(staging_new, now - 10)

    var = root / "var"
    releases = var / "releases"
    releases.mkdir(parents=True)
    release_paths = []
    for index in range(1, 4):
        path = releases / f"release-{index}"
        path.mkdir()
        set_mtime(path, now - (4 - index) * 60)
        release_paths.append(path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "untouched.txt").write_text("outside")
    (releases / "symlinked").symlink_to(outside, target_is_directory=True)

    old_import = var / "graph-import-old"
    old_import.mkdir(parents=True)
    set_mtime(old_import, old)
    new_import = var / "graph-import-new"
    new_import.mkdir()
    set_mtime(new_import, now - 10)

    backup_paths = []
    for index in range(1, 7):
        path = var / f"arena-backup-{index}.sqlite3"
        set_mtime(path, now - index * 60)
        backup_paths.append(path)

    protected = [
        var / "arena.sqlite3",
        root / "data" / "connectome.bin",
        root / "logs" / "service.log",
        root / ".venv" / "bin",
        root / "deploy" / "service.plist",
        root / "var" / "research" / "record.json",
        root / "var" / "runs" / "run.log",
        root / "var" / "artifacts" / "artifact.bin",
    ]
    for path in protected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("protected")

    candidate = root.parent / "fly-arena-candidate-old"
    candidate.mkdir()
    (candidate / "checkout.txt").write_text("candidate")
    active_candidate = root.parent / "fly-arena-candidate-active"
    active_candidate.mkdir()
    return {
        "root": root,
        "now": now,
        "staging_old": staging_old,
        "staging_new": staging_new,
        "release_paths": release_paths,
        "old_import": old_import,
        "new_import": new_import,
        "backup_paths": backup_paths,
        "protected": protected,
        "candidate": candidate,
        "active_candidate": active_candidate,
        "outside": outside,
    }


def test_cleanup_dry_run_is_default_and_lists_categories(tmp_path, monkeypatch, capsys):
    tree = make_cleanup_tree(tmp_path)
    monkeypatch.setenv("ARENA_DEPLOY_PATH", str(tree["root"]))
    monkeypatch.setattr(cleanup_deploy, "_running_process_uses", lambda path: path == tree["active_candidate"])

    cleanup_deploy.main([])

    output = capsys.readouterr().out
    assert "sync staging" in output
    assert "old release" in output
    assert "completed import staging" in output
    assert "old SQLite backup" in output
    assert "stale candidate checkout" in output
    assert "dry-run" in output
    assert "Total bytes:" in output
    assert tree["staging_old"].exists()
    assert tree["candidate"].exists()


def test_cleanup_apply_removes_only_allowlisted_items(tmp_path, monkeypatch):
    tree = make_cleanup_tree(tmp_path)
    monkeypatch.setattr(cleanup_deploy, "_running_process_uses", lambda path: path == tree["active_candidate"])
    output = io.StringIO()

    cleanup_deploy.run(tree["root"], apply=True, now=tree["now"], output=output)

    assert not tree["staging_old"].exists()
    assert tree["staging_new"].exists()
    assert not tree["release_paths"][0].exists()
    assert tree["release_paths"][1].exists()
    assert tree["release_paths"][2].exists()
    assert not tree["old_import"].exists()
    assert tree["new_import"].exists()
    assert all(path.exists() for path in tree["backup_paths"][:5])
    assert not tree["backup_paths"][5].exists()
    assert not tree["candidate"].exists()
    assert tree["active_candidate"].exists()
    assert tree["outside"].exists()
    assert all(path.exists() for path in tree["protected"])
    assert (tree["root"] / "var" / "releases" / "symlinked").is_symlink()


def test_cleanup_rejects_symlink_root(tmp_path):
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    symlink_root = tmp_path / "root-link"
    symlink_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink deployment root"):
        cleanup_deploy.find_cleanup_items(symlink_root)
