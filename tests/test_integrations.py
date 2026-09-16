"""Offline integration fixtures exercise real local ports and HTTP wire adapters."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from flyarena.auth import AuthConfig, NyxIDClient
from flyarena.integrations.chrono_bucket import ChronoBucketRepository
from flyarena.integrations.designer import OrnnPackageReference, CMATriggerDescriptor
from flyarena.integrations.descriptors import integration_descriptors
from flyarena.integrations.unavailable import UnavailableExecutor, preflight
from flyarena.services.executor import LocalProbeExecutor
from flyarena.services.ports import ArtifactRepository, IdentityProvider, ExperimentExecutor, ResearchRepository
from flyarena.services.experiments import ExperimentRepository
from flyarena.storage.local import LocalArtifactRepository
from flyarena.store import Store


def test_local_repository_atomic_digest_checked_and_pinned_package(tmp_path):
    repo=LocalArtifactRepository(tmp_path)
    assert isinstance(repo,ArtifactRepository)
    payload=b'local skill fixture; no external installation'
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(repo.put_if_absent,[payload]*20))
    assert len(set(ids))==1 and repo.get_verified(ids[0])==payload
    pin=OrnnPackageReference(skill_id='fly-designer',version='1.2',sha256=ids[0])
    assert pin.resolve_local(repo)==payload
    with pytest.raises(ValueError):OrnnPackageReference(skill_id='x',version='latest',sha256=ids[0])
    with pytest.raises(ValueError):OrnnPackageReference(skill_id='x',version='1.2',sha256=ids[0],sdk_package='ornn-sdk>=0.7')
    with pytest.raises(ValueError):repo.put_if_absent(payload,'0'*64)
    with pytest.raises(ValueError):repo.get_verified('../secrets')
    (tmp_path/ids[0]).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='digest'):repo.get_verified(ids[0])
    with pytest.raises(ValueError,match='digest'):repo.put_if_absent(payload)
    assert (tmp_path/ids[0]).read_bytes()==b'corrupt'  # never overwrites even corrupt content


def test_chrono_bucket_real_fenced_wire_and_verified_download():
    objects={};calls=[]
    def respond(request):
        calls.append(request)
        key=request.url.params['key']
        if request.method=='POST':
            assert request.url.path=='/buckets/research/objects'
            assert request.url.params['mutationGeneration']=='1'
            assert request.url.params['contentSha256']==hashlib.sha256(request.content).hexdigest()==key
            assert not any(k.lower().startswith('x-chrono-') for k in request.headers)
            assert 'allowRecreate' not in request.url.params
            objects.setdefault(key,request.content)
            return httpx.Response(200,json={'data':{'generation':1,'key':key},'error':None})
        assert request.url.path=='/buckets/research/objects/download'
        return httpx.Response(200,content=objects[key])
    client=httpx.Client(transport=httpx.MockTransport(respond))
    adapter=ChronoBucketRepository('https://bucket.example','research',client)
    assert isinstance(adapter,ArtifactRepository) and calls==[]
    with pytest.raises(RuntimeError,match='unavailable'):adapter.put_if_absent(b'body')
    adapter.enabled=True
    sha=adapter.put_if_absent(b'body')
    assert adapter.put_if_absent(b'body',sha)==sha
    assert adapter.get_verified(sha)==b'body'
    objects[sha]=b'wrong'
    with pytest.raises(ValueError,match='digest'):adapter.get_verified(sha)
    assert len([r for r in calls if r.method=='POST'])==2


def test_chrono_conflict_and_malformed_response_never_succeed():
    for response in [httpx.Response(409,json={'error':{'code':'STALE_GENERATION'}}),
                     httpx.Response(200,json={'error':'broken','data':None}),
                     httpx.Response(200,json={'error':None,'data':{'url':'https://legacy.example'}})]:
        client=httpx.Client(transport=httpx.MockTransport(lambda req:response))
        adapter=ChronoBucketRepository('https://bucket.example','research',client,enabled=True)
        with pytest.raises((httpx.HTTPStatusError,ValueError)):adapter.put_if_absent(b'fixture')


def test_cma_requires_deliberate_launch_and_preserves_server_link():
    url='https://cma.example/api/v1/triggers/public/pub_example/open/plc_readme'
    descriptor=CMATriggerDescriptor(public_url=url,badge_url='https://cma.example/api/v1/triggers/public/pub_example/badge.svg',
        label_text='Open in CMA',revision=3,content_sha256='a'*64)
    with pytest.raises(ValueError,match='explicit'):descriptor.launch_link(user_requested=False)
    assert descriptor.launch_link(user_requested=True)==url
    with pytest.raises(ValueError):CMATriggerDescriptor(**(descriptor.model_dump()|{'public_url':'javascript:alert(1)'}))


def test_ports_and_disabled_preflight_have_no_external_side_effects(tmp_path,monkeypatch):
    provider=NyxIDClient(AuthConfig(),httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('No live auth'))))
    assert isinstance(provider,IdentityProvider)
    provider.close()
    assert isinstance(ExperimentRepository(Store(tmp_path)),ResearchRepository)
    assert isinstance(LocalProbeExecutor(),ExperimentExecutor)
    unavailable=UnavailableExecutor('talos','Browser operator; no simulation capability')
    assert isinstance(unavailable,ExperimentExecutor)
    with pytest.raises(ValueError,match='Browser'):preflight(unavailable,['whole-trial'])
    with pytest.raises(RuntimeError,match='unavailable'):unavailable.execute({},'gradient-v2',42,3,tmp_path)
    assert all(not d['available'] for d in integration_descriptors())
    # Execute the real local adapter with an injected scientific boundary, not a fake adapter badge.
    from flyarena.experiments import probes
    calls=[]
    monkeypatch.setattr(probes,'profile_manifest',lambda **kwargs:{'ready':True})
    monkeypatch.setattr(probes,'run_probe',lambda *args,**kwargs:calls.append((args,kwargs)) or {'fixture':True})
    adapter=LocalProbeExecutor(data=tmp_path/'data',var=tmp_path/'var')
    assert preflight(adapter,['whole-trial','cpu']).available
    assert adapter.execute({'id':'fixture'},'gradient-v2',42,3,tmp_path/'output')=={'fixture':True}
    assert calls[0][1]=={'data':tmp_path/'data','var':tmp_path/'var'}
    monkeypatch.setattr(probes,'profile_manifest',lambda **kwargs:{'ready':False})
    with pytest.raises(ValueError,match='unavailable'):adapter.execute({},'gradient-v2',42,3,tmp_path)
