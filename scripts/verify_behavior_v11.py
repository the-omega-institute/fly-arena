"""Read saved archives independently: inventory, schema, partition, explicit vertices.

No simulation/controller advancement. Fixed checks revisit existing audit samples.
"""
import csv,json,sys,traceback
from pathlib import Path
import numpy as np
import mujoco as mj
from flyarena.experiments.realization_io_v11 import OUT,RAW,sha,exclusive_json,Budget,slices


def main():
    budget=Budget();budget.check()
    reg=json.loads((OUT/'registration.json').read_text());execution=json.loads((OUT/'execution-terminal.json').read_text())
    if not execution['complete']:raise ValueError('incomplete execution')
    if len(reg['inventory'])!=28 or set(execution['complete_cases'])!={c['id'] for c in reg['inventory']}:raise ValueError('case coverage')
    rawreg=json.loads((RAW/'registration.json').read_text());fields=slices(rawreg['core_schema']);m=mj.MjModel.from_binary_path(str(RAW/'model.mjb'));d=mj.MjData(m)
    foot=rawreg['measurement']['foot_geom_ids'];overlap=0;chunks=0;rows=0;maximum=0.;parsed_intervals=0;bouts=0
    for item in reg['inventory']:
        case=OUT/'cases'/item['id'];terminal=json.loads((case/'dense/terminal.json').read_text());allvalues=[];allticks=[]
        if not terminal['complete'] or terminal['initialized_rows']!=19001 or terminal['committed_rows']!=19001:raise ValueError('dense horizon')
        for j,entry in enumerate(terminal['files']):
            p=case/'dense'/entry['file']
            if p.name!=f'chunk-{j:05d}.npz' or sha(p)!=entry['sha256']:raise ValueError('archive hash')
            with np.load(p,allow_pickle=False) as z:
                t=z['ticks'];v=z['values']
                if set(z.files)!={'ticks','values'} or t.dtype!=np.int64 or v.dtype!=np.float64 or v.shape!=(len(t),288) or not np.isfinite(v).all():raise ValueError('saved archive schema/nonfinite')
                allticks.append(t);allvalues.append(v)
            chunks+=1
        ticks=np.concatenate(allticks);values=np.concatenate(allvalues)
        if not np.array_equal(ticks,np.arange(6000,25001)):raise ValueError('saved tick coverage')
        rows+=len(ticks)
        # Explicit world-vertex oracle at fixed existing sample ticks, independent
        # of the audit's batch directional support and centroid implementation.
        for tick in [6000,15000,25000]:
            with np.load(Path(item['raw'])/'core'/f'chunk-{tick//1000:05d}.npz',allow_pickle=False) as z:
                rr=z['values'][np.flatnonzero(z['ticks']==tick)[0]]
            d.qpos[:]=rr[fields['qpos']];mj.mj_kinematics(m,d)
            for j,gid in enumerate(foot):
                mesh=m.geom_dataid[gid];a=m.mesh_vertadr[mesh];n=m.mesh_vertnum[mesh]
                vv=m.mesh_vert[a:a+n].astype(float)
                points=(d.geom_xmat[gid].reshape(3,3)@vv.T).T+d.geom_xpos[gid]
                err=abs(float(points[:,2].min())-values[tick-6000,j]);maximum=max(maximum,err)
                if err>1e-12:raise ValueError('explicit vertex clearance mismatch')
                if j%5==4:
                    centroid=points.mean(axis=0)
                    # Schema offsets: first90 =3x30 minima; world starts90.
                    saved=values[tick-6000,90+(j//5)*3:93+(j//5)*3]
                    if np.max(np.abs(saved-centroid))>1e-12:raise ValueError('material centroid mismatch')
                overlap+=1
        parsed=json.loads((case/'parsed.json').read_text())
        if set(parsed)!={'actual','command','unit_r1'}:raise ValueError('record omission')
        for record,legs in parsed.items():
            if set(legs)!={'lf','lm','lh','rf','rm','rh'}:raise ValueError('leg omission')
            for leg,recorddata in legs.items():
                ii=recorddata['intervals'];parsed_intervals+=len(ii)
                if ii[0]['start_tick']!=6000 or ii[-1]['end_tick_inclusive']!=25000:raise ValueError('partial omission')
                for a,b in zip(ii[:-1],ii[1:]):
                    if a['end_tick_inclusive']!=b['start_tick']:raise ValueError('interval coverage gap')
        runs=json.loads((case/'original-bouts.json').read_text())
        for leg,rr in runs.items():
            bouts+=len(rr)
            if rr[0]['start_tick']!=6000 or rr[-1]['end_tick_exclusive']!=25001:raise ValueError('bout window omission')
            for a,b in zip(rr[:-1],rr[1:]):
                if a['end_tick_exclusive']!=b['start_tick'] or a['contact']==b['contact']:raise ValueError('bout partition mismatch')
        budget.check()
    report=OUT/'report'
    with (report/'all-case-leg-records.csv').open() as f:table=list(csv.DictReader(f))
    if len(table)!=28*6*3 or len({(r['case_id'],r['leg'],r['record']) for r in table})!=28*6*3:raise ValueError('all-condition CSV coverage')
    for name,v in json.loads((report/'manifest.json').read_text()).items():
        if sha(report/name)!=v['sha256']:raise ValueError('report artifact changed')
    # All frozen input and sealed implementation fingerprints remain fixed.
    for manifest in [json.loads((OUT/'inputs.json').read_text()),json.loads((OUT/'implementation-seal.json').read_text())['files']]:
        for path,v in manifest.items():
            if sha(path)!=v['sha256']:raise ValueError('final source/input mutation '+path)
    return {'schema':'independent-saved-evidence-check/v11','passed':True,'cases':28,'records_per_case':3,'dense_rows':rows,'numeric_chunks':chunks,
            'explicit_world_mesh_checks':overlap,'maximum_clearance_error_mm':maximum,'retained_parsed_intervals':parsed_intervals,'retained_contact_runs':bouts,
            'all_condition_csv_rows':len(table),'physical_seconds':0,'neural_seconds':0,'resources':budget.report()}

if __name__=='__main__':
    error=None;result=None
    try:result=main()
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)};traceback.print_exc()
    finally:
        receipt={'complete':error is None,'result':result,'error':error}
        try:exclusive_json(OUT/'verification.json',receipt)
        except BaseException as exc:
            error={'retention_failure':str(exc)}
            try:exclusive_json(Path('/tmp/fly-v11-realization/verification-failure.json'),error)
            except BaseException:print('TOTAL FILESYSTEM FAILURE: verification receipt unavailable',file=sys.stderr)
    print(json.dumps(receipt,indent=2))
    if error:raise SystemExit(1)
