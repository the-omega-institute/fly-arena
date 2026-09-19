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


def test_sensory_profiles_are_forwarded_and_cached_separately(monkeypatch):
    from flyarena.experiments.embodied_sensor import PROFILE
    def manifest(bridge_profile='legacy-v1', sensory_profile='odor-only-v1'):
        return {'sources': {'runner.py': 'science'}, 'sensory_profile':
                dict(PROFILE) if sensory_profile == PROFILE['id'] else {'id': sensory_profile}}
    monkeypatch.setattr('flyarena.runner.runtime_manifest', manifest)
    node = Node(CONFIG); calls = []
    def call(action, bridge, sensory='odor-only-v1'):
        calls.append((action, bridge, sensory))
        return manifest(bridge, sensory) | {'platform': 'linux-node'}
    monkeypatch.setattr(node, 'call', call)
    odor = node.runtime('legacy-v1')
    multimodal = node.runtime('legacy-v1', PROFILE['id'])
    assert odor['sensory_profile'] == {'id': 'odor-only-v1'}
    assert multimodal['sensory_profile'] == PROFILE
    assert multimodal['platform'] == 'linux-node'
    assert node.runtime('legacy-v1') is odor
    assert node.runtime('legacy-v1', PROFILE['id']) is multimodal
    assert calls == [('describe', 'legacy-v1', 'odor-only-v1'), ('describe', 'legacy-v1', PROFILE['id'])]
    with pytest.raises(ValueError, match='Unknown sensory profile'):
        node.runtime('legacy-v1', 'unknown')
    assert len(calls) == 2


def test_old_node_cannot_silently_downgrade_multimodal_input(monkeypatch):
    from flyarena.experiments.embodied_sensor import PROFILE
    monkeypatch.setattr('flyarena.runner.runtime_manifest', lambda **kw: {'sensory_profile': PROFILE})
    node = Node(CONFIG)
    monkeypatch.setattr(node, 'call', lambda *args: {'sensory_profile': {'id': 'odor-only-v1'}})
    with pytest.raises(ValueError, match='synchronization: sensory_profile'):
        node.runtime('legacy-v1', PROFILE['id'])
    assert not node._runtime


@pytest.mark.parametrize('sensory', [None, 'engineered-multimodal-v1', 'engineered-multimodal-v2', 'engineered-touch-response-v1'])
def test_node_describe_uses_requested_sensory_profile(monkeypatch, capsys, sensory):
    calls = []
    def manifest(**kwargs):
        calls.append(kwargs)
        return kwargs
    monkeypatch.setattr('flyarena.runner.runtime_manifest', manifest)
    monkeypatch.setattr(node_runner.sys, 'argv', ['node_runner', 'describe', 'legacy-v1'] + ([sensory] if sensory else []))
    node_runner.main()
    assert json.loads(capsys.readouterr().out) == {
        'bridge_profile': 'legacy-v1', 'sensory_profile': sensory or 'odor-only-v1'}
    assert len(calls) == 1


@pytest.mark.parametrize('endpoint', ['matches', 'tournaments'])
def test_api_routes_multimodal_to_configured_node_without_local_fallback(tmp_path, monkeypatch, endpoint):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    from flyarena.common import digest
    from flyarena.contracts import FlySpec
    from flyarena.experiments.embodied_sensor import PROFILE
    from flyarena.store import Store
    store = Store(tmp_path); owner = store.identity('tester')
    flies = [store.add_fly(owner['id'], FlySpec(name=name, connectome_sha256='a'*64).model_dump(),
                           {'artifact_id': str(i)*64}) for i, name in enumerate(('WT', 'Nectar'))]
    calls = []; offline = False
    runtime = {'platform': 'linux-node', 'sensory_profile': PROFILE}
    def node_runtime(bridge, sensory):
        calls.append((bridge, sensory))
        if offline: raise ConnectionError('offline')
        return runtime
    monkeypatch.setattr('flyarena.services.node.configured_node', lambda: SimpleNamespace(runtime=node_runtime))
    def no_local(**kwargs): raise AssertionError('must not fall back to local runtime')
    monkeypatch.setattr('flyarena.api.runtime_manifest', no_local)
    payload = {'fly_ids': [f['id'] for f in flies], 'mode': 'contest', 'duration_seconds': 1,
               'sensory_profile': PROFILE['id']}
    if endpoint == 'tournaments': payload['name'] = 'Multimodal series'
    with TestClient(create_app(with_worker=False, store=store, auth_config=AuthConfig())) as client:
        client.headers['Authorization'] = 'Bearer ' + owner['token']
        url = '/api/v1/' + endpoint
        response = client.post(url, json=payload, headers={'Idempotency-Key': 'first'})
        assert response.status_code == 202, response.text
        admitted = response.json()
        assert calls == [('legacy-v1', PROFILE['id'])]
        assert all(m['runtime_hash'] == digest(runtime) and m['request']['sensory_profile'] == PROFILE['id']
                   for m in store.matches())
        count = len(store.matches()); offline = True
        # Reading the admitted request after a lost reply does not enqueue a second job.
        retry = client.post(url, json=payload, headers={'Idempotency-Key': 'first'})
        assert retry.status_code == 202 and retry.json()['id'] == admitted['id']
        assert len(calls) == 1
        assert client.post(url, json=payload, headers={'Idempotency-Key': 'new'}).status_code == 503
        assert len(store.matches()) == count


def test_job_uses_configured_node_even_when_runtime_matches_local(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from flyarena import job
    from flyarena.common import digest
    from flyarena.contracts import FlySpec, MatchRequest
    from flyarena.store import Store
    store = Store(tmp_path)
    fly = store.add_fly('owner', FlySpec(name='fixture', connectome_sha256='a'*64).model_dump(),
                        {'artifact_id': 'b'*64})
    request = MatchRequest(fly_ids=[fly['id']], mode='forage', duration_seconds=1,
                           sensory_profile='engineered-multimodal-v1').model_dump()
    runtime = {'sensory_profile': request['sensory_profile'], 'platform': 'same-host'}
    match = store.add_match('owner', request, digest(runtime))
    ident, lease, generation = store.claim()
    monkeypatch.setattr(job.sys, 'argv', ['job', ident, lease, str(generation), str(tmp_path)])
    monkeypatch.setattr(job, 'runtime_manifest', lambda **kw: runtime)
    executed = []
    def execute(record, flies, destination, heartbeat):
        executed.append(record['request'])
        heartbeat(1)
    monkeypatch.setattr('flyarena.services.node.configured_node', lambda: SimpleNamespace(execute=execute))
    def no_local(*args, **kwargs): raise AssertionError('Configured node must receive this job')
    monkeypatch.setattr(job, 'simulate', no_local)
    # This test covers dispatch only; the real node protocol smoke verifies evidence.
    verdict = {'status': 'verified', 'scores': [0], 'winner_slot': None}
    monkeypatch.setattr(job, 'verify', lambda *args, **kwargs: verdict)
    job.main()
    assert executed == [request]
    assert store.match(match['id'])['result'] == verdict
