"""Trusted compute-node entry point. No user code is executed by this transport."""
from __future__ import annotations

import base64
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import traceback
import zlib

from ..common import VAR, canonical, digest, write_json


def folder(ident: str) -> Path:
    if not re.fullmatch(r'[0-9a-f]{32}', ident):
        raise ValueError('Invalid node job ID')
    path = VAR / 'node-jobs' / ident
    path.mkdir(parents=True, exist_ok=True)
    return path


def state(path: Path) -> dict:
    status = json.loads((path/'status.json').read_text())
    if status['status'] in {'queued', 'running'}:
        try:
            os.kill(status['pid'], 0)
        except ProcessLookupError:
            # The worker may have published its result between our read and exit.
            status = json.loads((path/'status.json').read_text())
            if status['status'] in {'complete', 'failed'}:
                return status
            status.update(status='failed', error='Node process stopped before producing a result')
            write_json(path/'status.json', status)
    return status


def start(ident: str, parts: int) -> dict:
    path = folder(ident)
    with (path/'control.lock').open('a') as control:
        fcntl.flock(control, fcntl.LOCK_EX)
        raw = zlib.decompress(base64.b64decode(''.join((path/f'part-{i}').read_text() for i in range(parts))))
        request = json.loads(raw)
        if (path/'request.json').exists():
            if json.loads((path/'request.json').read_text()) != request:
                raise ValueError('Node job ID was already used for another request')
        else:
            write_json(path/'request.json', request)
        if (path/'status.json').exists():
            return state(path)
        with (path/'worker.log').open('a') as log:
            child = subprocess.Popen([sys.executable, '-m', 'flyarena.services.node_runner', 'run', ident],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     start_new_session=True)
        status = {'status': 'queued', 'progress': 0, 'pid': child.pid}
        write_json(path/'status.json', status)
        return status


def run(ident: str):
    path = folder(ident)
    with (path/'control.lock').open('a') as control:
        fcntl.flock(control, fcntl.LOCK_EX)
        status = json.loads((path/'status.json').read_text())
    try:
        # All heavy jobs on this node share one lock, including operator experiments.
        with Path(os.environ.get('ARENA_NODE_LOCK', '/tmp/fly-arena-gpu.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            from ..compiler import Compiler
            from ..connectome import Connectome
            from ..contracts import FlySpec, MatchRequest
            from ..runner import runtime_manifest, simulate
            request = json.loads((path/'request.json').read_text())
            match = MatchRequest.model_validate(request['match'])
            if digest(runtime_manifest(bridge_profile=match.bridge_profile)) != request['runtime_hash']:
                raise ValueError('Node runtime changed after admission; submit under the current runtime')
            flies = request['flies']
            if [f['id'] for f in flies] != match.fly_ids:
                raise ValueError('Node contestant IDs differ from the admitted match')
            compiler = Compiler(Connectome())
            for fly in flies:
                report = compiler.compile(FlySpec.model_validate(fly['spec']), publish=True, root=VAR)
                if report['artifact_id'] != fly['artifact_id']:
                    raise ValueError('Node compiled a different contestant artifact')
            def progress(value):
                status.update(status='running', progress=value)
                write_json(path/'status.json', status)
            progress(0)
            simulate(match, flies, path/'evidence', progress, var=VAR)
            with tarfile.open(path/'evidence.tar.gz', 'w:gz') as archive:
                for entry in (path/'evidence').iterdir():
                    archive.add(entry, arcname=entry.name)
            status.update(status='complete', progress=1, bytes=(path/'evidence.tar.gz').stat().st_size)
    except BaseException as exc:
        traceback.print_exc()
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    write_json(path/'status.json', status)


def main():
    action, *args = sys.argv[1:]
    if action == 'describe':
        from ..runner import runtime_manifest
        result = runtime_manifest(bridge_profile=args[0])
    elif action == 'put':
        ident, index, chunk = args
        index = int(index)
        if not 0 <= index < 4000 or len(chunk) > 5000 or not re.fullmatch(r'[A-Za-z0-9+/=]*', chunk):
            raise ValueError('Invalid node upload part')
        target = folder(ident)/f'part-{index}'
        temporary = target.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(chunk)
        temporary.replace(target)
        result = {'stored': index}
    elif action == 'start':
        parts = int(args[1])
        if not 1 <= parts <= 4000:
            raise ValueError('Invalid node upload size')
        result = start(args[0], parts)
    elif action == 'status':
        result = state(folder(args[0]))
    elif action == 'read':
        path = folder(args[0])
        offset = int(args[1])
        if state(path)['status'] != 'complete' or offset < 0:
            raise ValueError('Node result is not ready')
        with (path/'evidence.tar.gz').open('rb') as source:
            source.seek(offset)
            result = {'data': base64.b64encode(source.read(512*1024)).decode()}
    elif action == 'run':
        run(args[0])
        return
    else:
        raise ValueError('Unknown node action')
    print(canonical(result).decode())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(canonical({'command_error': f'{type(exc).__name__}: {exc}'}).decode())
