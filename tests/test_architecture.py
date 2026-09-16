"""Architecture guards and compatible versioned ranking projection."""
import ast
from pathlib import Path
from flyarena.services.ranking import rank, POLICY_ID


def test_scientific_core_cannot_import_providers_auth_or_http():
    root=Path(__file__).parents[1]/'src/flyarena'
    forbidden={'auth','api','integrations','httpx','requests','fastapi','urllib','nyxid','ornn','talos'}
    files=[root/name for name in ('neural.py','body.py','backend.py','judge.py','compiler.py','contracts.py','research.py')]
    files+=list((root/'experiments').glob('*.py'))
    for path in files:
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules=[]
            if isinstance(node,ast.Import):modules=[a.name for a in node.names]
            if isinstance(node,ast.ImportFrom):modules=[node.module or '']
            assert not any(forbidden.intersection(module.split('.')) for module in modules),(path,modules)


def test_http_handlers_do_not_execute_simulation_and_store_does_not_rank():
    root=Path(__file__).parents[1]/'src/flyarena'
    api=ast.parse((root/'api.py').read_text())
    for node in ast.walk(api):
        if isinstance(node,ast.Call):
            name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
            assert name not in {'run_probe','execute_claim'},name
    store=(root/'store.py').read_text()
    assert 'from .services.ranking import rank' in store
    assert 'winner_slot' not in store[store.index('    def leaderboard'):store.index('    def add_tournament')]


def test_ranking_never_aggregates_incompatible_runtime_scenario_mode_season():
    flies=[{'id':'a'},{'id':'b'}]
    def match(runtime,scenario,mode,created,season='genesis-alpha'):
        return {'status':'verified','runtime_hash':runtime,'created':created,
                'request':{'fly_ids':['a','b'],'map_id':scenario,'mode':mode,'season_id':season},
                'result':{'scores':[2,1],'winner_slot':0}}
    sessions=[match('v1','orchard','contest',1),match('v1','maze','contest',2),
              match('v1','orchard','sumo',3),match('v2','orchard','contest',4),
              match('v2','orchard','contest',5,'future')]
    rows=rank(flies,sessions)
    assert rows[0]['matches']==1 and rows[0]['points']==3 and rows[0]['ranking_policy']==POLICY_ID
    assert rows[0]['scope']==['genesis-alpha','v2','orchard','contest','legacy-v1']
    old=rank(flies,sessions,runtime_hash='v1',scenario_id='orchard',mode='contest')
    assert old[0]['matches']==1 and old[0]['scope'][1]=='v1'
    assert all(r['matches']==0 for r in rank(flies,sessions,runtime_hash='unknown'))


def test_tournament_projection_rejects_mixed_scopes():
    from flyarena.services.ranking import tournament_projection
    matches=[{'status':'verified','runtime_hash':runtime,'created':i,
              'request':{'fly_ids':['a','b'],'map_id':'orchard','mode':'contest'},
              'result':{'winner_slot':0,'scores':[2,1]}} for i,runtime in enumerate(['v1','v2'])]
    result=tournament_projection(matches,['a','b'])
    assert result['status']=='incomplete' and result['ranking_error']
    assert all(r['played']==0 for r in result['standings'])
    matches[1]['runtime_hash']='v1'
    result=tournament_projection(matches,['a','b'])
    assert result['status']=='complete' and result['standings'][0]['points']==6
