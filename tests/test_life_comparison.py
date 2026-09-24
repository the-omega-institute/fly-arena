"""Comparison evidence remains conditional; traversal never discloses private IDs."""
import json
import pytest
from fastapi.testclient import TestClient
from flyarena.common import digest
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.services.life import LifeLedger
from flyarena.services.life_comparison import LifeComparison, comparison_reasons, CONDITIONS
from test_training import lab, create
from test_life_lineage import _child


def evaluation(**condition):
    return {'status':'verified','scores':[0],'condition':dict.fromkeys(CONDITIONS,'recorded')|condition}


def test_comparable_requires_every_condition_and_preserves_zero():
    left=evaluation(seed=0,slots=[0],opponents=[],silence_output=False)
    assert comparison_reasons(left,left)==[]
    for field in CONDITIONS:
        right=evaluation(**left['condition'])
        right['condition'][field]=None
        assert {'field':field,'code':'missing'} in comparison_reasons(left,right)
        right['condition'][field]='different'
        assert {'field':field,'code':'different'} in comparison_reasons(left,right)
    assert comparison_reasons(left,left|{'status':'failed','scores':None})==[
        {'field':'status','code':'unverified'},{'field':'scores','code':'missing'}]


def recorded(store, owner, fly, *, seed=0, motor='motor-a', runtime='runtime-a', status='verified', score=0):
    request={'fly_ids':[fly['id']],'map_id':'orchard','seed':seed,'duration_seconds':2,
             'mode':'forage','bridge_profile':'legacy-v1','sensory_profile':'odor-only-v1'}
    frozen={'sources':{'runner.py':runtime,'body.py':motor}}
    receipt={'request':request,'runtime':frozen,'silence_output':False}
    receipt['sha256']=digest(receipt)
    match=store.add_match(owner,request,digest(frozen))
    with store.db() as db:
        db.execute('UPDATE matches SET status=?,result=? WHERE id=?',
                   (status,json.dumps({'scores':[score],'receipt_sha256':receipt['sha256']}),match['id']))
    match=store.match(match['id']);folder=store.result_folder(match);folder.mkdir(parents=True,exist_ok=True)
    (folder/'receipt.json').write_text(json.dumps(receipt))
    return match


def test_parent_and_child_outcomes_are_bound_and_incomparability_is_explicit(lab):
    store,_,user,parent=lab;child=_child(lab,parent,neuron_parameters={'tau_scale':1.1})
    a=recorded(store,user['id'],parent,score=0)
    b=recorded(store,user['id'],child,score=2)
    recorded(store,user['id'],child,seed=9,score=3)
    recorded(store,user['id'],child,motor='motor-b',score=4)
    recorded(store,user['id'],child,status='failed')
    service=LifeComparison(LifeLedger(store))
    result=service.get(child['id'],user['id'],relative=parent['id'])['comparison']
    assert result['delta']['changed_parameters'][0]['child']==pytest.approx(1.1)
    comparable=[p for p in result['pairs'] if not p['reasons']]
    assert len(comparable)==1
    assert result['left'][comparable[0]['left']]['match_id']==b['id']
    assert result['right'][0]['scores']==[0]
    assert {'field':'seed','code':'different'} in [r for p in result['pairs'] for r in p['reasons']]
    assert {'field':'motor','code':'different'} in [r for p in result['pairs'] for r in p['reasons']]
    assert result['left'][0]['status']=='failed' and result['left'][0]['scores'] is None
    reverse=service.get(parent['id'],user['id'],relative=child['id'])['comparison']
    assert reverse['relation']=='child' and reverse['delta']==result['delta']
    # A receipt altered after verification cannot establish comparability.
    path=store.result_folder(a)/'receipt.json';receipt=json.loads(path.read_text());receipt['silence_output']=True;path.write_text(json.dumps(receipt))
    result=service.get(child['id'],user['id'],relative=parent['id'])['comparison']
    assert all(p['reasons'] for p in result['pairs'])


def test_missing_receipts_private_relatives_and_unrelated_comparisons(lab):
    store,_,user,parent=lab;run=create(lab)
    private=_child(lab,parent,training=(run['id'],0,0));child=_child(lab,parent)
    ledger=LifeLedger(store);service=LifeComparison(ledger)
    assert service.get(private['id']) is None
    public=service.get(parent['id'])
    assert private['id'] not in json.dumps(public)
    assert service.get(parent['id'],relative=private['id']) is None
    assert service.get(child['id'],user['id'],relative=private['id']) is None
    a=recorded(store,user['id'],parent);b=recorded(store,user['id'],child)
    (store.result_folder(a)/'receipt.json').unlink()
    pair=service.get(child['id'],relative=parent['id'])['comparison']['pairs'][0]
    assert {'field':'motor','code':'missing'} in pair['reasons']
    assert b['id']
    assert {f['id'] for f in ledger.saved(user['id'])}=={parent['id'],child['id']}
    assert ledger.saved(None)==[] and ledger.saved('stranger')==[]


def test_slices_traverse_all_breadth_and_ancestors_without_private_ids(lab):
    store,_,user,parent=lab;run=create(lab)
    children=[_child(lab,parent) for _ in range(55)]
    private=_child(lab,parent,training=(run['id'],0,0))
    ledger=LifeLedger(store)
    first=ledger.lineage(parent['id'],depth=1)
    marker=next(n for n in first['nodes'] if n.get('marker'))
    assert marker['continuation'].endswith('direction=descendants&offset=50')
    second=ledger.lineage_slice(parent['id'],offset=50)
    assert {c['id'] for c in children}<={n['id'] for n in first['nodes']+second['nodes']}
    assert private['id'] not in json.dumps(second)
    siblings=ledger.lineage(children[0]['id'],depth=1)
    assert any(n.get('continuation','').endswith('direction=siblings&offset=50') for n in siblings['nodes'])
    sibling_page=ledger.lineage_slice(children[0]['id'],direction='siblings',offset=50)
    assert children[0]['id'] in {n['id'] for n in sibling_page['nodes']}
    chain=[parent]
    for _ in range(8):chain.append(_child(lab,chain[-1]))
    tree=ledger.lineage(chain[-1]['id'],depth=3)
    marker=next(n for n in tree['nodes'] if n.get('direction')=='ancestors')
    assert marker['continuation'].endswith('direction=ancestors&offset=3')
    page=ledger.lineage_slice(chain[-1]['id'],direction='ancestors',offset=3)
    assert chain[-5]['id'] in {n['id'] for n in page['nodes']}
    assert not any(e['to']==chain[-1]['id'] for e in page['edges'])  # No invented immediate parent link.


def test_comparison_and_slice_api_visibility_and_bounds(lab,monkeypatch):
    store,service,user,parent=lab;child=_child(lab,parent)
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        path='/api/v1/life/'+parent['id']
        assert client.get(path+'/comparison').status_code==200
        assert client.get(path+'/comparison',params={'relative':child['id']}).json()['comparison']['relation']=='child'
        assert client.get(path+'/slice').status_code==200
        assert client.get(path+'/slice?offset=-1').status_code==422
        assert client.get(path+'/slice?direction=other').status_code==422
        assert client.get('/api/v1/life/missing/comparison').status_code==404
        assert client.get('/api/v1/lives/saved').json()==[]
        client.headers['Authorization']='Bearer '+user['token']
        assert len(client.get('/api/v1/lives/saved').json())==2
