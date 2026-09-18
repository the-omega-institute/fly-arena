"""Optional NyxID transport for the trusted serial match executor.

Identity/SSH stays outside neural dynamics. The API freezes the node's runtime,
and the receiving app verifies returned evidence against that admitted runtime.
"""
from __future__ import annotations

import base64
from functools import lru_cache
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
import zlib

from ..common import canonical


class Node:
    def __init__(self, config: dict):
        self.config = config
        for key in ('service', 'principal', 'root', 'data'):
            if not isinstance(config.get(key), str) or not config[key]:
                raise ValueError('Node configuration requires '+key)
        if not all(Path(config[key]).is_absolute() for key in ('root', 'data')):
            raise ValueError('Node root and data must be absolute paths')
        self._runtime: dict[str, tuple[float, dict]] = {}

    def call(self, action: str, *args: str) -> dict:
        c = self.config
        root = Path(c['root'])
        command = shlex.join(['env', 'OMP_NUM_THREADS=1', 'OPENBLAS_NUM_THREADS=1',
            'NUMBA_NUM_THREADS=1', 'MPLBACKEND=Agg', 'MUJOCO_GL=disable',
            'PYTHONPATH='+str(root/'src'), 'ARENA_DATA='+c['data'], 'ARENA_VAR='+str(root/'var'),
            str(root/'.venv/bin/python'), '-m', 'flyarena.services.node_runner', action, *args])
        result = subprocess.run([c.get('nyxid', 'nyxid'), 'ssh', 'exec', c['service'],
            '--principal', c['principal'], command], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise ConnectionError('Compute node command failed: '+result.stderr[-500:])
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ConnectionError('Compute node returned an incomplete response') from exc
        if 'command_error' in response:
            raise ValueError(response['command_error'])
        return response

    def runtime(self, profile: str) -> dict:
        cached = self._runtime.get(profile)
        if cached and time.monotonic()-cached[0] < 30:
            return cached[1]
        remote = self.call('describe', profile)
        from ..runner import runtime_manifest
        local = runtime_manifest(bridge_profile=profile)
        # Platform/Python may differ. Scientific sources, graph, rules and readout must match.
        if profile != 'legacy-v1':
            raise ValueError('Remote execution currently supports legacy-v1 matches only')
        for key in ('sources', 'lock_sha256', 'model', 'models', 'rules', 'replay_policy',
                    'connectome_sha256', 'readout_weights_sha256'):
            if remote.get(key) != local.get(key):
                raise ValueError('Compute node needs synchronization: '+key)
        self._runtime[profile] = (time.monotonic(), remote)
        return remote

    def execute(self, match: dict, flies: list[dict], destination: Path, heartbeat):
        ident = match['id']
        payload = base64.b64encode(zlib.compress(canonical({
            'match': match['request'], 'runtime_hash': match['runtime_hash'], 'flies': flies,
        }))).decode()
        chunks = [payload[i:i+4500] for i in range(0, len(payload), 4500)]
        # Retrying submission uses the same job ID, so an uncertain SSH response
        # never starts another simulation. Node evidence is retained for reattachment.
        def retry(action, *args):
            while True:
                heartbeat(progress)
                try:
                    return self.call(action, *args)
                except (ConnectionError, subprocess.TimeoutExpired):
                    time.sleep(5)
        progress = 0.
        for index, chunk in enumerate(chunks):
            retry('put', ident, str(index), chunk)
        status = retry('start', ident, str(len(chunks)))
        while status['status'] not in {'complete', 'failed'}:
            progress = float(status.get('progress', 0))
            heartbeat(progress)
            time.sleep(5)
            status = retry('status', ident)
        if status['status'] == 'failed':
            raise ValueError(status['error'])
        progress = 1.
        archive_path = destination/'node-evidence.tar.gz'
        with archive_path.open('wb') as output:
            while output.tell() < status['bytes']:
                chunk = base64.b64decode(retry('read', ident, str(output.tell()))['data'], validate=True)
                if not chunk or len(chunk) > status['bytes']-output.tell():
                    raise ValueError('Incomplete compute-node result archive')
                output.write(chunk)
        with tarfile.open(archive_path) as archive:
            for entry in archive.getmembers():
                if not entry.isfile() or Path(entry.name).name != entry.name:
                    raise ValueError('Unexpected compute-node archive entry')
            archive.extractall(destination, filter='data')
        archive_path.unlink()


@lru_cache(maxsize=1)
def configured_node() -> Node | None:
    path = os.environ.get('ARENA_NODE_CONFIG')
    return Node(json.loads(Path(path).read_text())) if path else None
