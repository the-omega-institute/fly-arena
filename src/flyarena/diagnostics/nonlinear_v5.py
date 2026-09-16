"""One fixed train-only RBF diagnostic; never exported as a runtime decoder."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import numpy as np
from scipy.spatial.distance import cdist, pdist
from flyarena.common import ROOT, file_sha, write_json, digest
from flyarena.diagnostics.assay_v5 import raw_pair, labels, causal_features

OUT = ROOT/'var/nonlinear-v5'
DEVELOPMENT = ROOT/'var/diagnostic-v5'


def waveforms():
    rows=[]
    def add(name,family,history,raw,**extra):
        rows.append(dict(index=len(rows),id=name,family=family,history=history,raw=np.asarray(raw).tolist(),**extra))
    k=np.arange(30)
    for history in ['triangle_excursion','two_step_pulse']:
        for common in [.55,.95]:
            for contrast in [-.02,0.,.02]:
                raw=np.zeros((60,2))
                if history=='triangle_excursion':
                    pre_common=np.interp(k,[0,14,29],[.35,1.15,common])
                    pre_contrast=np.interp(k,[0,14,29],[-.04,.04,-contrast])
                else:
                    pre_common=np.where(k<15,1.05,.35)
                    pre_contrast=np.where(k<15,.04,-.03)
                raw[:30]=raw_pair(pre_common,pre_contrast)
                raw[30:]=raw_pair(common,contrast)
                add(f'clamp_{history}_{common}_{contrast}','terminal_clamp',history,raw,
                    terminal_common=common,terminal_contrast=contrast)
    k=np.arange(60)
    for family in ['triangle','cubic_ease']:
        u=k/60
        shape=(np.interp(k,[0,15,30,45,59],[-1,1,0,-1,0]) if family=='triangle'
               else 2*(3*u*u-2*u*u*u)-1)
        for direction in [1,-1]:
            for mirror in [1,-1]:
                add(f'{family}_{direction}_{mirror}',family,family,
                    raw_pair(.75+direction*.4*shape,mirror*np.where(k<30,-.02,.02)),
                    direction=direction,mirror=mirror)
    add('blank','control','blank',np.zeros((60,2)))
    add('silent_low_004','control','low',np.full((60,2),.04))
    off=np.zeros((60,2));off[:30]=raw_pair(.95,.02)
    add('cue_off','control','cue_off',off)
    add('checkpoint_repeat','control','repeat',rows[12]['raw'],repeat_of=12)
    return rows


def fit_kernel(x,y):
    mean=x.mean(axis=0);sd=x.std(axis=0);active=sd>1e-8
    if not active.any():raise ValueError('No active training columns')
    scale=np.where(active,sd,1.)
    z=((x-mean)/scale)[:,active]/np.sqrt(active.sum())
    distances=pdist(z,'euclidean');nonzero=distances[distances>0]
    if not len(nonzero):raise ValueError('No nonzero training pair distances')
    sigma=float(np.median(nonzero))
    kernel=np.exp(-cdist(z,z,'sqeuclidean')/(2*sigma*sigma))
    intercept=y.mean(axis=0)
    dual=np.linalg.solve(kernel+np.eye(len(z)),y-intercept)
    return dict(mean=mean,scale=scale,active=active,train_z=z,sigma=np.array(sigma),
                dual=dual,intercept=intercept)


def predict_kernel(model,x,silence):
    original=x.shape[:-1]
    z=((x.reshape(-1,x.shape[-1])-model['mean'])/model['scale'])[:,model['active']]
    z/=np.sqrt(model['active'].sum())
    kernel=np.exp(-cdist(z,model['train_z'],'sqeuclidean')/(2*float(model['sigma'])**2))
    result=(kernel@model['dual']+model['intercept']).reshape(*original,-1)
    result[silence]=0
    return result


def sources():
    names=['common.py','neural.py','backend.py','connectome.py','experiments/sensor.py',
           'experiments/decoder.py','diagnostics/assay_v5.py','diagnostics/nonlinear_v5.py']
    result={str((ROOT/'src/flyarena'/n).relative_to(ROOT)):file_sha(ROOT/'src/flyarena'/n) for n in names}
    result['tests/test_nonlinear_v5.py']=file_sha(ROOT/'tests/test_nonlinear_v5.py')
    return result


def protected_snapshot():
    # Metadata covers prior diagnostic evidence without reading prohibited logs.
    paths=list(DEVELOPMENT.rglob('*'))+[ROOT/'src/flyarena/diagnostics/assay_v5.py',
        ROOT/'src/flyarena/diagnostics/contact.py',ROOT/'tests/test_diagnostic_v5.py']
    return {str(p.relative_to(ROOT)):[p.stat().st_size,p.stat().st_mtime_ns] for p in paths if p.is_file()}


def freeze():
    OUT.mkdir(exist_ok=False)
    before=protected_snapshot()
    data=[];identities={}
    for i in range(20):
        path=DEVELOPMENT/f'raw/seq-{i:02d}-samples.npz'
        with np.load(path,allow_pickle=False) as a:data.append(dict(a))
        identities[str(path.relative_to(ROOT))]=file_sha(path)
    rates=np.stack([d['dn_rates'] for d in data]);raw=np.stack([d['raw'] for d in data])
    features=causal_features(rates,'history');truth=labels(raw)
    mask=np.zeros((20,60),bool);mask[:,9:]=True;mask &= np.linalg.norm(rates,axis=-1)>1e-9
    model=fit_kernel(features[mask],truth[mask])
    np.savez_compressed(OUT/'candidate.npz',**model,training_mask=mask)
    rows=waveforms();raw_fresh=np.array([r['raw'] for r in rows])
    pairs=[dict(a=a,b=b,sample=30) for a,b in [(12,14),(13,15),(16,18),(17,19)]]
    for pair in pairs:assert np.array_equal(raw_fresh[pair['a'],30],raw_fresh[pair['b'],30])
    manifest=json.loads((ROOT/'data/connectome/manifest.json').read_text())
    canonical={str((ROOT/'data/connectome'/name).relative_to(ROOT)):sha for name,sha in manifest['files'].items()}
    canonical['data/connectome/manifest.json']=file_sha(ROOT/'data/connectome/manifest.json')
    canonical['data/connectome/research-v2/readout.npz']=file_sha(ROOT/'data/connectome/research-v2/readout.npz')
    protocol=dict(schema='dn-causal-gaussian-diagnostic/v1',created_unix=time.time(),
        candidate=dict(alpha=1.,lags_ms=[0,50,100],rate_scaling='rate Hz /100 before train-only scaling',
            normalization='training column mean/std; drop std<=1e-8; divide sqrt(active count)',
            bandwidth_rule='median of ALL strictly positive Euclidean distances for unordered training-row pairs, scipy pdist, no subsampling',
            kernel='K(z,zprime)=exp(-||z-zprime||^2/(2*sigma^2))',sigma=float(model['sigma']),
            heads=['local signed contrast','local raw common','local causal common slope; descriptive only'],
            head_formula='independent heads: train_target_mean + K_eval_train @ solve(K_train_train + 1*I, target-train_target_mean)',
            training_sequences=list(range(20)),training_rows=int(mask.sum()),
            training_mask='response_end_ms >=100 and current DN L2 norm>1e-9; all 20 noncontrol development sequences only',
            silence='If current DN L2 norm<=1e-9 all predictions=0; exclude from fitting and primary gates; report excluded counts',
            history='0/50/100ms; causal zero-prefix per independent reset; no time/sequence/world/task/reward labels',
            weights_sha256=file_sha(OUT/'candidate.npz'),active_columns=int(model['active'].sum()),
            trend_decision='Include third independently fitted diagnostic head, never used for gates or commands'),
        sequences=rows,matched_current_pairs=pairs,controls=list(range(20,24)),
        input_start_ms=(np.arange(60)*10).tolist(),response_end_ms=(np.arange(1,61)*10).tolist(),
        samples_per_sequence=60,sequence_count=24,neural_dt_ms=.1,steps_per_sample=100,
        acceptance=dict(late_start_ms=450,late_end_ms=600,sign_min=.95,neutral_mean_max=.02,
            rule='Nonzero terminal clamps: >=95% pooled AND each sequence correct predicted sign; neutral clamps: max abs sequence mean .85*tanh(6*pred_contrast)<=.02; no empty eligible sequence may pass',
            failure='Stop single candidate; no refit, tuning, sensor/motor change or body trial',
            neutral_rms_peak='descriptive; do not replace the approved mean gate',
            latency='input switch300ms to first end sample starting five consecutive correct signs, k30..55; null if absent',
            dynamic='response_end_ms>=100; contrast sign, common and trend MAE/sign, matched-current trend ordering descriptive only'),
        sample_contract='Hold input on [10k,10(k+1))ms; save end rates and actual injected currents; no body',
        checkpoint='Full initial/mid300ms/final600ms for24; seq23 restores seq12 initial and midpoint',
        development_sha256=identities,canonical_sha256=canonical,source_sha256=sources(),
        protected_snapshot=before,no_body_trials=True,no_runtime_export=True)
    write_json(OUT/'protocol.json',protocol)
    (OUT/'protocol.sha256').write_text(file_sha(OUT/'protocol.json')+'\n')
    print(json.dumps(dict(frozen=file_sha(OUT/'protocol.json'),candidate=protocol['candidate'])),flush=True)


def load_protocol():
    p=OUT/'protocol.json'
    assert file_sha(p)==(OUT/'protocol.sha256').read_text().strip()
    protocol=json.loads(p.read_text())
    assert sources()==protocol['source_sha256']
    assert file_sha(OUT/'candidate.npz')==protocol['candidate']['weights_sha256']
    for name,sha in protocol['development_sha256'].items():assert file_sha(ROOT/name)==sha
    for name,sha in protocol['canonical_sha256'].items():assert file_sha(ROOT/name)==sha
    return protocol


def run():
    from flyarena.connectome import Connectome
    from flyarena.neural import Brain
    from flyarena.backend import CPUBrainBackend
    from flyarena.experiments.sensor import encode_odor
    from flyarena.experiments.decoder import Decoder,target
    protocol=load_protocol();folder=OUT/'raw';folder.mkdir()
    start=time.perf_counter();graph=Connectome(ROOT/'data',verify=True)
    backend=CPUBrainBackend(Brain(graph));dn=graph.groups['descending']
    decoder=Decoder(ROOT/'data/connectome/research-v2/readout.npz')
    assert len(dn)==1314 and np.array_equal(dn,decoder.neurons)
    aff=np.unique(np.concatenate([graph.groups['olfactory_left'],graph.groups['olfactory_right']]))
    outside=np.ones(graph.n,bool);outside[aff]=False
    np.savez(folder/'neuron-identities.npz',dn_index=dn,dn_body_id=graph.ids[dn],afferent_index=aff,afferent_body_id=graph.ids[aff])
    receipt=dict(protocol_sha256=file_sha(OUT/'protocol.json'),candidate_sha256=file_sha(OUT/'candidate.npz'),
        neuron_count=graph.n,edge_count=graph.e,dn_count=len(dn),afferent_count=len(aff),
        started_unix=time.time(),sequences=[])
    assert receipt['started_unix']>protocol['created_unix']
    for row in protocol['sequences']:
        i=row['index'];t=time.perf_counter();prefix=folder/f'seq-{i:02d}'
        backend.reset(0)
        if i==23:
            with np.load(folder/'seq-12-start.npz',allow_pickle=False) as a:backend.restore(dict(a))
        np.savez_compressed(str(prefix)+'-start.npz',**backend.checkpoint())
        rates=[];current=[];encoded=[];commands=[];dn_current=[];spikes=[]
        raw=np.array(row['raw'])
        for k,pair in enumerate(raw):
            if k==30:
                if i==23:
                    with np.load(folder/'seq-12-middle.npz',allow_pickle=False) as a:backend.restore(dict(a))
                np.savez_compressed(str(prefix)+'-middle.npz',**backend.checkpoint())
            enc=encode_odor(*pair);backend.stimulate(*enc)
            assert not np.any(backend.brain.external[outside])
            current.append(backend.brain.external[aff].copy());counts=backend.advance(100)
            rates.append(backend.neural_output(dn));encoded.append(enc)
            commands.append(decoder.command(rates[-1]));dn_current.append(backend.brain.current[dn].copy());spikes.append(counts[dn])
        np.savez_compressed(str(prefix)+'-final.npz',**backend.checkpoint())
        np.savez_compressed(str(prefix)+'-samples.npz',raw=raw,encoded=encoded,external_current=current,
            dn_rates=rates,dn_synaptic_current=dn_current,dn_spikes=spikes,old_commands=commands,
            old_targets=np.array([target(pair) for pair in raw]),input_start_ms=protocol['input_start_ms'],response_end_ms=protocol['response_end_ms'])
        receipt['sequences'].append(dict(index=i,id=row['id'],wall_seconds=time.perf_counter()-t,
            final_tick=backend.brain.tick,total_spikes=backend.brain.total_spikes,
            files={p.name:file_sha(p) for p in folder.glob(f'seq-{i:02d}-*.npz')}))
        write_json(OUT/'run-progress.json',receipt)
        print(f'sequence {i+1}/24 {row["id"]}',flush=True)
    receipt.update(wall_seconds=time.perf_counter()-start,completed_unix=time.time())
    write_json(OUT/'run-receipt.json',receipt)
    print('ASSAY_COMPLETE',receipt['wall_seconds'],flush=True)


def metrics(pred,truth,silence,protocol):
    times=np.array(protocol['response_end_ms']);late=(times>=450)&(times<=600)
    clamps=[];all_ok=[];neutral=[];dynamics=[]
    for i,row in enumerate(protocol['sequences'][:20]):
        valid=late & ~silence[i];asym=.85*np.tanh(6*pred[i,:,0]);ok=pred[i,:,0]*truth[i,:,0]>0
        latency=next((int(times[k]-300) for k in range(30,56) if np.all(ok[k:k+5])),None)
        if row['family']=='terminal_clamp':
            r=dict(sequence=i,id=row['id'],eligible_late_samples=int(valid.sum()),excluded_silent_late_samples=int((late&silence[i]).sum()),
                raw_common_mae=float(np.mean(abs(pred[i,valid,1]-truth[i,valid,1]))) if valid.any() else None,
                common_drive_mae=float(np.mean(abs(.85*np.maximum(pred[i,valid,1],0)/(np.maximum(pred[i,valid,1],0)+.3)-.85*truth[i,valid,1]/(truth[i,valid,1]+.3)))) if valid.any() else None)
            if row['terminal_contrast']:
                r.update(sign_accuracy=float(ok[valid].mean()) if valid.any() else 0.,latency_ms=latency)
                all_ok.extend(ok[valid].tolist())
            else:
                r.update(neutral_mean=float(asym[valid].mean()) if valid.any() else None,
                    neutral_rms=float(np.sqrt(np.mean(asym[valid]**2))) if valid.any() else None,
                    neutral_peak=float(np.max(abs(asym[valid]))) if valid.any() else None)
                if valid.any():neutral.append(abs(r['neutral_mean']))
            clamps.append(r)
        else:
            v=(times>=100)&~silence[i];slope=v&(abs(truth[i,:,2])>1e-12)
            dynamics.append(dict(sequence=i,id=row['id'],sign_accuracy=float(ok[v].mean()),latency_ms=latency,
                raw_common_mae=float(np.mean(abs(pred[i,v,1]-truth[i,v,1]))),
                trend_sign_accuracy=float(np.mean(pred[i,slope,2]*truth[i,slope,2]>0)),
                trend_mae=float(np.mean(abs(pred[i,v,2]-truth[i,v,2])))))
    pooled=float(np.mean(all_ok)) if all_ok else 0.;bias=max(neutral) if neutral else None
    gate=dict(pooled_sign=pooled,pooled_sign_pass=pooled>=.95,
        per_sequence_sign_pass=all(r.get('sign_accuracy',1)>=.95 for r in clamps),
        neutral_max_absolute_mean=bias,neutral_mean_pass=bias is not None and bias<=.02,
        no_empty_sequence=all(r['eligible_late_samples']>0 for r in clamps),late_nonzero_samples=len(all_ok))
    gate['passed']=all(gate[k] for k in ['pooled_sign_pass','per_sequence_sign_pass','neutral_mean_pass','no_empty_sequence'])
    pairs=[]
    for pair in protocol['matched_current_pairs']:
        a,b,k=pair['a'],pair['b'],pair['sample'];p=pred[[a,b],k,2];y=truth[[a,b],k,2]
        pairs.append(pair|dict(predicted_slopes=p.tolist(),true_slopes=y.tolist(),
            correct_order=bool((p[0]-p[1])*(y[0]-y[1])>0),both_signs_correct=bool(np.all(p*y>0))))
    return dict(gate_result=gate,clamp_sequences=clamps,dynamic_sequences=dynamics,matched_current_pairs=pairs)


def analyze():
    protocol=load_protocol()
    if (OUT/'summary.json').exists():raise FileExistsError('No reanalysis or tuning')
    data=[]
    for i in range(24):
        with np.load(OUT/f'raw/seq-{i:02d}-samples.npz',allow_pickle=False) as a:data.append(dict(a))
    rates=np.stack([d['dn_rates'] for d in data]);raw=np.stack([d['raw'] for d in data])
    with np.load(OUT/'candidate.npz',allow_pickle=False) as a:model=dict(a)
    silence=np.linalg.norm(rates,axis=-1)<=1e-9;truth=labels(raw)
    pred=predict_kernel(model,causal_features(rates,'history'),silence)
    np.savez_compressed(OUT/'predictions.npz',prediction=pred,truth=truth,silence=silence)
    summary=metrics(pred,truth,silence,protocol)
    summary.update(protocol_sha256=file_sha(OUT/'protocol.json'),candidate_sha256=file_sha(OUT/'candidate.npz'),
        controls=dict(blank_max_rate=float(rates[20].max()),low_max_rate=float(rates[21].max()),
            blank_low_dn_identical=bool(np.array_equal(rates[20],rates[21])),
            cue_off_final_dn_norm=float(np.linalg.norm(rates[22,-1])),cue_off_final_prediction=pred[22,-1].tolist(),
            total_silent_samples=int(silence.sum())),
        decision='Diagnostic pass only; no runtime/body/retention qualification' if summary['gate_result']['passed'] else 'STOP: candidate failed; no refit, alternate model, sensor/motor change or body trial')
    write_json(OUT/'summary.json',summary)
    print(json.dumps(summary,indent=2),flush=True)


def verify():
    protocol=load_protocol();receipt=json.loads((OUT/'run-receipt.json').read_text())
    from flyarena.connectome import Connectome
    from flyarena.experiments.sensor import encode_odor
    graph=Connectome(ROOT/'data',verify=True)
    assert len(receipt['sequences'])==24 and receipt['started_unix']>protocol['created_unix']
    with np.load(OUT/'raw/neuron-identities.npz') as a:
        aff=a['afferent_index'];assert np.array_equal(a['dn_index'],graph.groups['descending'])
        assert np.array_equal(a['dn_body_id'],graph.ids[a['dn_index']])
    data=[]
    for entry in receipt['sequences']:
        i=entry['index']
        for name,sha in entry['files'].items():assert file_sha(OUT/'raw'/name)==sha
        with np.load(OUT/f'raw/seq-{i:02d}-samples.npz') as a:
            data.append(dict(a));assert a['dn_rates'].shape==(60,1314)
            assert np.array_equal(a['raw'],protocol['sequences'][i]['raw'])
            assert np.array_equal(a['input_start_ms'],np.arange(60)*10)
            assert np.array_equal(a['response_end_ms'],np.arange(1,61)*10)
            assert np.array_equal(a['encoded'],np.array([encode_odor(*p) for p in a['raw']]))
            expected=np.zeros((60,len(aff)))
            for j,side in enumerate(['left','right']):expected[:,np.isin(aff,graph.groups['olfactory_'+side])]=48*a['encoded'][:,j,None]
            assert np.array_equal(a['external_current'],expected)
        for part,tick in [('start',0),('middle',3000),('final',6000)]:
            with np.load(OUT/f'raw/seq-{i:02d}-{part}.npz') as a:
                assert set(a.files)=={'v','current','refractory','delay','external','rates','tick','total_spikes'}
                assert int(a['tick'])==tick and a['delay'].shape==(19,graph.n)
                assert all(np.isfinite(a[k]).all() for k in a.files)
    for part in ['start','middle','final','samples']:
        with np.load(OUT/f'raw/seq-12-{part}.npz') as a,np.load(OUT/f'raw/seq-23-{part}.npz') as b:
            assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
    old=[]
    for i in range(20):
        with np.load(DEVELOPMENT/f'raw/seq-{i:02d}-samples.npz') as a:old.append(dict(a))
    rates=np.stack([d['dn_rates'] for d in old]);x=causal_features(rates,'history');y=labels(np.stack([d['raw'] for d in old]))
    mask=np.zeros((20,60),bool);mask[:,9:]=True;mask&=np.linalg.norm(rates,axis=-1)>1e-9
    with np.load(OUT/'candidate.npz') as a:model=dict(a)
    assert np.array_equal(mask,model['training_mask'])
    assert np.array_equal(model['mean'],x[mask].mean(axis=0))
    sd=x[mask].std(axis=0);assert np.array_equal(model['active'],sd>1e-8)
    assert np.array_equal(model['scale'],np.where(sd>1e-8,sd,1))
    z=((x[mask]-model['mean'])/model['scale'])[:,model['active']]/np.sqrt(model['active'].sum())
    assert np.array_equal(z,model['train_z'])
    dist=pdist(z);assert float(model['sigma'])==float(np.median(dist[dist>0]))
    kernel=np.exp(-cdist(z,z,'sqeuclidean')/(2*float(model['sigma'])**2))
    np.testing.assert_allclose((kernel+np.eye(len(z)))@model['dual'],y[mask]-model['intercept'],atol=1e-10)
    assert np.array_equal(model['intercept'],y[mask].mean(axis=0))
    rates=np.stack([d['dn_rates'] for d in data]);silence=np.linalg.norm(rates,axis=-1)<=1e-9
    with np.load(OUT/'predictions.npz') as a:
        np.testing.assert_array_equal(a['prediction'],predict_kernel(model,causal_features(rates,'history'),silence))
        assert np.array_equal(a['silence'],silence)
        expected_metrics=metrics(a['prediction'],a['truth'],silence,protocol)
    summary=json.loads((OUT/'summary.json').read_text())
    for key,value in expected_metrics.items():assert value==summary[key]
    assert protected_snapshot()==protocol['protected_snapshot']
    checks=['frozen source/model/protocol/development/canonical hashes unchanged',
        '24 fresh arrays, 1440 samples and exact encoded/injected currents verified',
        '72 complete checkpoints; exact initial/midpoint replay and full output/state equality',
        'train-only masks/scaling/active columns/all-pairs bandwidth and fixed ridge equation verified without refit',
        'saved predictions exactly recomputed from frozen DN-only model; gates recomputed',
        'prior diagnostic source/evidence size and mtime unchanged; prohibited logs not read']
    write_json(OUT/'verification.json',dict(checks=checks,passed=True,verified_unix=time.time(),
        protocol_sha256=file_sha(OUT/'protocol.json'),candidate_sha256=file_sha(OUT/'candidate.npz')))
    print(json.dumps(dict(passed=True,checks=checks)),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','analyze','verify']);a=p.parse_args();globals()[a.action]()

if __name__=='__main__':main()
