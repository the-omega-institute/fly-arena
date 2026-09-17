"""Remote execution transport: stable jobs, interrupted transfers and runtime identity."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import zlib

import pytest

from flyarena.common import canonical
from flyarena.services.node import Node
from flyarena.services import node_runner

CONFIG={'service':'test-node','principal':'arena','root':'/srv/arena','data':'/srv/arena/data'}
JOB='a'*32


def parts(path, request):
    (path/'part-0').write_text(base64.b64encode(zlib.compress(canonical(request))).decode())


def test_node_start_is_idempotent_across_uncertain_submission(tmp_path, monkeypatch):
    monkeypatch.setattr(node_runner,'VAR',tmp_path)
    spawned=[]
    def spawn(command, **kwargs):
        spawned.append(command)
        return type('Process',(),{'pid':os.getpid()})()
    monkeypatch.setattr(node_runner.subprocess,'Popen',spawn)
    path=node_runner.folder(JOB)
    parts(path,{'match':{'seed':42}})
    first=node_runner.start(JOB,1)
    assert node_runner.start(JOB,1)==first
    assert spawned==[[node_runner.sys.executable,'-m','flyarena.services.node_runner','run',JOB]]
    parts(path,{'match':{'seed':43}})
    with pytest.raises(ValueError,match='another request'):node_runner.start(JOB,1)
    assert len(spawned)==1


def test_missing_node_process_is_terminal_and_not_restarted(tmp_path, monkeypatch):
    (tmp_path/'status.json').write_text(json.dumps({'status':'running','pid':987654,'progress':.5}))
    def gone(pid, signal):raise ProcessLookupError
    monkeypatch.setattr(node_runner.os,'kill',gone)
    result=node_runner.state(tmp_path)
    assert result['status']=='failed' and 'stopped' in result['error']
    assert json.loads((tmp_path/'status.json').read_text())==result


def test_runtime_freezes_actual_node_platform_but_rejects_different_science(monkeypatch):
    local={'sources':{'runner.py':'science'},'platform':'local'}
    monkeypatch.setattr('flyarena.runner.runtime_manifest',lambda **kw:local)
    node=Node(CONFIG)
    remote=local|{'platform':'linux-node','python':'3.12.3'}
    monkeypatch.setattr(node,'call',lambda *args:remote)
    assert node.runtime('legacy-v1') is remote
    node._runtime.clear()
    remote=remote|{'sources':{'runner.py':'other-science'}}
    with pytest.raises(ValueError,match='synchronization'):node.runtime('legacy-v1')


def test_process_exit_after_final_write_does_not_replace_completed_result(tmp_path,monkeypatch):
    path=tmp_path/'status.json'
    path.write_text(json.dumps({'status':'running','pid':987654,'progress':.9}))
    complete={'status':'complete','pid':987654,'progress':1.,'bytes':123}
    def finished(pid,signal):
        path.write_text(json.dumps(complete))
        raise ProcessLookupError
    monkeypatch.setattr(node_runner.os,'kill',finished)
    assert node_runner.state(tmp_path)==complete
    assert json.loads(path.read_text())==complete


def archive(member='frames.json'):
    result=io.BytesIO()
    with tarfile.open(fileobj=result,mode='w:gz') as tar:
        info=tarfile.TarInfo(member);data=b'["actual payload"]';info.size=len(data)
        tar.addfile(info,io.BytesIO(data))
    return result.getvalue()


def test_transfer_retries_same_remote_job_and_offset_keeps_lease(tmp_path,monkeypatch):
    node=Node(CONFIG);blob=archive();calls=[];heartbeats=[];failed=set()
    monkeypatch.setattr('flyarena.services.node.time.sleep',lambda _:None)
    def call(action,*args):
        calls.append((action,*args))
        if action in {'start','read'} and action not in failed:
            failed.add(action);raise subprocess.TimeoutExpired('ssh',60)
        if action=='put':return {'stored':int(args[1])}
        if action=='start':return {'status':'running','progress':.2}
        if action=='status':return {'status':'complete','progress':1.,'bytes':len(blob)}
        assert action=='read'
        return {'data':base64.b64encode(blob[int(args[1]):]).decode()}
    monkeypatch.setattr(node,'call',call)
    node.execute({'id':JOB,'request':{'seed':42},'runtime_hash':'remote'},[],tmp_path,heartbeats.append)
    assert (tmp_path/'frames.json').read_bytes()==b'["actual payload"]'
    assert [c for c in calls if c[0]=='start']==[('start',JOB,'1')]*2
    assert [c for c in calls if c[0]=='read']==[('read',JOB,'0')]*2
    assert len(heartbeats)>=6
    assert not (tmp_path/'node-evidence.tar.gz').exists()


def test_node_command_errors_are_not_retried_as_network_outages(monkeypatch):
    result=type('Result',(),{'returncode':0,'stdout':'{"command_error":"Runtime changed"}','stderr':''})()
    monkeypatch.setattr('flyarena.services.node.subprocess.run',lambda *a,**k:result)
    with pytest.raises(ValueError,match='Runtime changed'):Node(CONFIG).call('status',JOB)


def test_archive_cannot_escape_result_directory(tmp_path,monkeypatch):
    node=Node(CONFIG);blob=archive('../outside.json')
    def call(action,*args):
        if action=='put':return {'stored':0}
        if action=='start':return {'status':'complete','progress':1.,'bytes':len(blob)}
        return {'data':base64.b64encode(blob).decode()}
    monkeypatch.setattr(node,'call',call)
    with pytest.raises(ValueError,match='archive entry'):
        node.execute({'id':JOB,'request':{},'runtime_hash':'remote'},[],tmp_path,lambda _:None)
    assert not (tmp_path.parent/'outside.json').exists()
