"""Ordinary verified matches expose the actual contestant's bounded brain graph."""
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.compiler import Compiler
from flyarena.connectome import CIRCUITS
from flyarena.contracts import FlySpec, MatchRequest
from flyarena.store import Store
from test_core import graph

@pytest.fixture
def live_replay(tmp_path,monkeypatch):
    g=graph();g.ids=np.array([101,102,103]);g.signs=np.array([1,-1,1],dtype=np.float32);g.path=tmp_path/'connectome';g.path.mkdir()
    (g.path/'neurons.json').write_text(json.dumps([{'id':str(i),'class':'test'} for i in g.ids]))
    for key,*_ in CIRCUITS:g.groups.setdefault(key,np.array([],dtype=np.int32))
    monkeypatch.setattr('flyarena.api.Connectome',lambda:g)
    compiler=Compiler(g);store=Store(tmp_path/'arena');owner=store.identity('designer');flies=[]
    for scale in [1,1.1]:
        spec=FlySpec(name=f'fly{scale}',connectome_sha256='a'*64,weight_mutations=[{'selector':'olfactory','scale':scale}])
        report=compiler.compile(spec,publish=True,root=store.root);flies.append(store.add_fly(owner['id'],spec.model_dump(),report))
    match=store.add_match(owner['id'],MatchRequest(fly_ids=[f['id'] for f in flies],mode='contest').model_dump(),'fixture')
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        yield client,store,match,flies


def test_live_match_binds_snapshots_and_weights_to_each_recorded_slot(live_replay):
    client,store,match,flies=live_replay;path=f"/api/v1/matches/{match['id']}"
    assert client.get(path+'/brain/0',params={'ids':'101'}).status_code==409
    mid,lease,_=store.claim();store.finish(mid,lease,{'status':'verified','scores':[0,0]})
    saved=client.get(path).json();listing=client.get('/api/v1/matches').json()[0]
    assert saved['participants']==listing['participants']
    assert [p['id'] for p in saved['participants']]==[f['id'] for f in flies]
    assert all('owner' not in p and 'token' not in p for p in saved['participants'])
    graphs=[client.get(path+f'/brain/{slot}',params={'ids':'101'}).json() for slot in [0,1]]
    for slot,design in enumerate(graphs):
        assert design['artifact_id']==flies[slot]['artifact_id']
        edge=next(e for e in design['circuits']['olfactory']['edges'] if e['edge']==0)
        assert edge['multiplier']==pytest.approx([1,1.1][slot])
        assert edge['weight']==pytest.approx(.275*[1,1.1][slot])
        assert edge['baseline_weight']==pytest.approx(.275)
        assert all('activity' not in node for node in design['circuits']['olfactory']['neurons'])
    assert client.get(path+'/brain/2',params={'ids':'101'}).status_code==404
    assert client.get(path+'/brain/0',params={'ids':'101,101'}).status_code==422
    # A database mismatch cannot substitute a different brain for the admitted fly.
    with store.db() as db:db.execute('UPDATE flies SET artifact_id=? WHERE id=?',('f'*64,flies[1]['id']))
    assert client.get(path+'/brain/1',params={'ids':'101'}).status_code==409
    assert len(client.get(path).json()['participants'])==1


def test_graph_requests_reuse_bounded_snapshot_for_reordered_samples(live_replay,monkeypatch):
    client,store,match,_=live_replay
    mid,lease,_=store.claim();store.finish(mid,lease,{'status':'verified','scores':[0,0]})
    import flyarena.brain_graph as module
    original=module.build;calls=[]
    def counted(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(module,'build',counted)
    path=f"/api/v1/matches/{match['id']}/brain/1"
    first=client.get(path,params={'ids':'101,102'});second=client.get(path,params={'ids':'102,101'})
    assert first.status_code==second.status_code==200
    assert first.json()==second.json() and len(calls)==1
