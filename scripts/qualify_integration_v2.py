#!/usr/bin/env python3
"""Real held-out body qualification, durable HTTP experiment and arena job verification.

Uses a fresh independent state root; does not bind a socket or activate live auth.
Never recalibrates or rewrites prepared readouts. Every scientific run is full graph.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.common import DATA, ROOT, digest, file_sha, write_json
from flyarena.compiler import Compiler
from flyarena.connectome import Connectome
from flyarena.contracts import MatchRequest
from flyarena.experiments.probes import profile_manifest, run_probe, verify_evidence
from flyarena.experiments.qualification import CASES, build_qualification, verify_qualification
from flyarena.judge import verify
from flyarena.research import PhenotypeReport
from flyarena.runner import runtime_manifest, simulate
from flyarena.services.research_service import ResearchService
from flyarena.store import Store


def qualification(root, wt, state):
    profile=profile_manifest()
    reports={}
    for name,probe,seed,seconds,options in CASES:
        print('START',name,flush=True)
        reports[name]=r=run_probe(wt,probe,seed,seconds,root/name,var=state,**options)
        PhenotypeReport.model_validate(r);verify_evidence(root/name,r)
        assert digest(r['profile'])==digest(profile), 'sources changed during qualification'
        print('DONE',name,json.dumps(r['metrics']),flush=True)
    result=build_qualification(root,profile)
    write_json(root/'qualification.json',result)
    verify_qualification(root/'qualification.json',profile)
    print('QUALIFICATION',json.dumps(result['checks']),flush=True)
    return result


def http_trials(root,store,compiler,service,qualified):
    app=create_app(with_worker=False,store=store,auth_config=AuthConfig(),research_service=service)
    client=TestClient(app)
    identity=store.identity('Independent integration QA')
    client.headers['Authorization']='Bearer '+identity['token']
    annotations=client.get('/api/v1/connectome/annotations?field=class').json()
    assert {'olfactory','ALPN','ALLN','Kenyon_Cell'} <= {v['value'] for v in annotations['items']}
    write_json(root/'annotations.json',annotations)
    response=client.post('/api/v1/flies',json={'name':'Integration neural design','color':'violet',
        'connectome_sha256':compiler.graph.manifest['sha256'],
        'interventions':[{'selector':{'pre':{'class':'olfactory'}},'scale':1.06}],
        'neuron_parameters':{'tau_scale':1.02,'threshold_shift_mv':.3}},headers={'X-Arena-Submission-Channel':'web'})
    assert response.status_code==201,response.text
    design=response.json();write_json(root/'design.json',design)
    assert design['submission_channel']=='web' and design['reference_kind']=='user'
    if not qualified:
        rejected=client.post('/api/v1/matches',json={'fly_ids':[design['id']],'mode':'forage','bridge_profile':'sensorimotor-research-v2'})
        assert rejected.status_code==422 and 'Bridge unavailable' in rejected.text
        season=client.get('/api/v1/season').json()
        assert season['default_bridge_profile']=='legacy-v1' and season['match_profiles'][1]['ready'] is False
        write_json(root/'admission.json',{'rejected_status':rejected.status_code,'rejected_body':rejected.json(),'season_profiles':season['match_profiles']})
    experiment_id=design['experiment_id'];assert experiment_id and design['experiment_status']=='queued'
    claim=service.repository.claim();assert claim[0]==experiment_id
    with (root/'experiment-job.log').open('w') as log:
        subprocess.run([sys.executable,'-m','flyarena.services.research_job',str(store.root),claim[0],claim[1],str(claim[2])],stdout=log,stderr=subprocess.STDOUT,check=True)
    experiment=client.get('/api/v1/experiments/'+experiment_id).json()
    write_json(root/'experiment.json',experiment)
    assert experiment['status']=='complete',experiment['error']
    assert len(experiment['reports'])==3 and len({r['condition_key'] for r in experiment['reports']})==1
    for report in experiment['reports']: PhenotypeReport.model_validate(report)
    assert [s['role'] for s in experiment['subjects']]==['wildtype','official','design']
    assert experiment['owner']==identity['id']
    print('EXPERIMENT',experiment_id,'complete',flush=True)
    refs=service.references();matches={}
    for name,mode,ids in [('solo','forage',[refs['wildtype']['id']]),('dual','contest',[refs['wildtype']['id'],design['id']])]:
        request=MatchRequest(fly_ids=ids,mode=mode,duration_seconds=3,seed=10042,bridge_profile='sensorimotor-research-v2')
        runtime=digest(runtime_manifest(bridge_profile=request.bridge_profile))
        if qualified:
            response=client.post('/api/v1/matches',json=request.model_dump())
            assert response.status_code==202,response.text
            match=response.json();assert match['runtime_hash']==runtime
            claim=store.claim();assert claim[0]==match['id']
            with (root/(name+'-job.log')).open('w') as log:
                subprocess.run([sys.executable,'-m','flyarena.job',claim[0],claim[1],str(claim[2]),str(store.root)],stdout=log,stderr=subprocess.STDOUT,check=True)
            match=client.get('/api/v1/matches/'+match['id']).json();assert match['status']=='verified',match['error']
            folder=store.result_folder(match)
            for artifact in ['scene','frames','events','receipt']:
                r=client.get('/api/v1/matches/'+match['id']+'/'+artifact);assert r.status_code==200
                assert r.json()==json.loads((folder/(artifact+'.json')).read_text())
        else:
            folder=root/(name+'-unqualified-diagnostic')
            flies=[store.fly(i) for i in ids]
            simulate(request,flies,folder,var=store.root)
            match={'request':request.model_dump(),'artifacts':[f['artifact_id'] for f in flies],
                   'runtime_hash':runtime,'admission':'unqualified internal diagnostic; not API admitted'}
        verdict=verify(folder,expected_request=match['request'],expected_artifacts=match['artifacts'],expected_runtime_hash=runtime)
        receipt=json.loads((folder/'receipt.json').read_text())
        assert receipt['neuron_count']>100000 and receipt['edge_count']>20000000
        assert receipt['runtime']['actual_backend']=='cpu-numba'
        matches[name]={'match':match,'folder':str(folder),'verdict':verdict}
        print('ARENA',name,verdict,flush=True)
    write_json(root/'arena.json',matches)
    return {'experiment_id':experiment_id,'experiment':str(root/'experiment.json'),'arena':str(root/'arena.json')}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'var/research-validation/qualification-v4/final')
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    store=Store(root/'state');compiler=Compiler(Connectome(verify=True))
    service=ResearchService(store,lambda:compiler);wt=service.references()['wildtype']
    profile=profile_manifest();write_json(root/'frozen-profile.json',profile)
    write_json(root/'source-snapshot.json',{str(p.relative_to(ROOT)):file_sha(p) for p in sorted((ROOT/'src/flyarena').rglob('*.py'))})
    q=qualification(root,wt,store.root)
    import flyarena.bridge as bridge
    bridge.QUALIFICATION=root/'qualification.json'
    http=http_trials(root,store,compiler,service,all(q['checks'].values()))
    assert digest(profile_manifest())==digest(profile),'source changed during final acceptance'
    result={'passed':all(q['checks'].values()),'qualification':str(root/'qualification.json'),'http_evidence':http,'profile_sha256':digest(profile)}
    write_json(root/'summary.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
