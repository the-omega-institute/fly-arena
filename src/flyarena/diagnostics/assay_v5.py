"""Preregistered open-loop DN observability assay; no runtime controller exports."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import numpy as np
from flyarena.common import ROOT, file_sha, write_json, digest

OUT = ROOT / 'var/diagnostic-v5'
DT = .01
BASE = '61a89f6cb94e4a6ff206f3fe1e3a147c535a44b2'


def raw_pair(common, contrast):
    common, contrast = np.broadcast_arrays(common, contrast)
    difference = contrast * (2 * common + .05)
    return np.stack([common + difference / 2, common - difference / 2], axis=-1)


def waveforms():
    rows = []
    def add(name, family, history, raw, **extra):
        rows.append(dict(index=len(rows), id=name, family=family, history=history,
                         raw=np.asarray(raw).tolist(), **extra))
    for history in ['blank', 'opposite_ramp']:
        for common in [.55, .95]:
            for contrast in [-.02, 0., .02]:
                raw = np.zeros((60, 2))
                if history == 'opposite_ramp':
                    # Other common level approaches terminal common; opposite signed cue.
                    raw[:30] = raw_pair(np.linspace(1.5-common, common, 30),
                                        np.linspace(-contrast, -contrast/2, 30))
                raw[30:] = raw_pair(common, contrast)
                add(f'clamp_{history}_{common}_{contrast}', 'terminal_clamp', history, raw,
                    terminal_common=common, terminal_contrast=contrast)
    k = np.arange(60)
    for family in ['linear', 'sine']:
        shape = (k-30)/30 if family == 'linear' else np.sin(np.pi*(k-30)/60)
        for trend in [1, -1]:
            for mirror in [1, -1]:
                common = .75 + trend * .4 * shape
                contrast = mirror * np.where(k < 30, -.02, .02)
                add(f'{family}_{trend}_{mirror}', family, f'{family}_{trend}',
                    raw_pair(common, contrast), trend_direction=trend, mirror=mirror)
    add('blank', 'control', 'blank', np.zeros((60, 2)))
    add('silent_low_004', 'control', 'low', np.full((60, 2), .04))
    raw = np.zeros((60, 2)); raw[:30] = raw_pair(.95, .02)
    add('cue_off', 'control', 'cue_off', raw)
    add('checkpoint_repeat', 'control', 'repeat', rows[12]['raw'], repeat_of=12,
        restore_from_reference_at_sample=30)
    return rows


def causal_features(rates, mode):
    """At response k use rates[k], rates[k-5], rates[k-10]; reset prefix is zero."""
    x = np.asarray(rates, dtype=float) / 100
    if mode == 'current':
        return x.copy()
    if mode != 'history':
        raise ValueError(mode)
    parts = [x]
    for lag in (5, 10):
        z = np.zeros_like(x); z[:, lag:] = x[:, :-lag]; parts.append(z)
    return np.concatenate(parts, axis=-1)


def labels(raw):
    common = raw.mean(axis=-1)
    contrast = (raw[..., 0]-raw[..., 1])/(raw.sum(axis=-1)+.05)
    trend = np.zeros_like(common)
    for k in range(1, 60):
        prior = max(0, k-5)
        trend[:, k] = (common[:, k]-common[:, prior])/((k-prior)*DT)
    return np.stack([contrast, common, trend], axis=-1)


def fit_probe(x, y):
    # All fitted statistics depend ONLY on training sequences and active training rows.
    mean = x.mean(axis=0); scale = x.std(axis=0)
    active = scale > 1e-8
    if not active.any():
        raise ValueError('No varying training features')
    scale = np.where(active, scale, 1.)
    z = ((x-mean)/scale)[:, active] / np.sqrt(active.sum())
    ym = y.mean(axis=0)
    dual = np.linalg.solve(z@z.T + np.eye(len(z)), y-ym)
    return dict(mean=mean, scale=scale, active=active,
                coef=z.T@dual, intercept=ym)


def predict_probe(model, x, silence):
    z = ((x-model['mean'])/model['scale'])[..., model['active']]
    z = z/np.sqrt(model['active'].sum())
    result = z@model['coef'] + model['intercept']
    result[silence] = 0
    return result


def source_hashes():
    paths = [ROOT/'src/flyarena'/n for n in ['neural.py','backend.py','connectome.py',
        'body.py','scenarios.py','experiments/sensor.py','experiments/decoder.py',
        'experiments/probes.py','diagnostics/assay_v5.py','diagnostics/contact.py']]
    paths += [ROOT/'tests/test_diagnostic_v5.py']
    return {str(p.relative_to(ROOT)):file_sha(p) for p in paths}


def freeze():
    from flyarena.experiments.sensor import SENSOR
    from flyarena.neural import PROFILE
    rows = waveforms()
    raw = np.asarray([r['raw'] for r in rows])
    matched = []
    for a,b in [(12,14),(13,15),(16,18),(17,19)]:
        # At sample 30 rising/falling common and sign match exactly; histories differ.
        assert np.allclose(raw[a,30], raw[b,30], atol=1e-14)
        matched.append({'a':a,'b':b,'sample':30})
    protocol = dict(schema='diagnostic-open-loop/v5', base_commit=BASE,
        created_unix=time.time(), sample_count=60, sequence_count=24, neural_seconds=14.4,
        input_start_ms=(np.arange(60)*10).tolist(), response_end_ms=((np.arange(60)+1)*10).tolist(),
        neural_steps_per_sample=100, neural_dt_ms=.1,
        sampling='Zero-order hold input on [10k,10(k+1)) ms; end-of-interval rate and command. No body.',
        sequences=rows, matched_current_controls=matched,
        splits=[dict(id='history_and_waveform_holdout', train=list(range(6))+list(range(12,16)),
                     evaluate=list(range(6,12))+list(range(16,20)),
                     reason='Blank clamp histories and linear waveforms fit; entire opposite-ramp histories and sine family held out.'),
                dict(id='reciprocal_history_and_family', train=list(range(6,12))+list(range(16,20)),
                     evaluate=list(range(6))+list(range(12,16)),
                     reason='Predeclared reciprocal sensitivity analysis; not candidate reselection.')],
        controls=list(range(20,24)), feature_modes=['current','history'],
        history_basis=dict(lags_ms=[0,50,100], initialization='All sequence prefixes zero from deterministic resting checkpoint',
                           causal='No future or cross-sequence samples'),
        probe=dict(kind='linear ridge; unpenalized intercept', alpha=1.,
                   objective='sum squared residual + 1 * squared coefficient norm; independent three outputs',
                   scaling='training-only per-column mean/std; drop std<=1e-8; divide by sqrt(active feature count)',
                   fitting_rows='response_end_ms>=100 AND current DN norm>1e-9, training sequences only',
                   silence='force prediction zero if current DN norm<=1e-9; silent rows excluded from fitting and primary gates',
                   outputs=['signed normalized raw contrast (L-R)/(L+R+.05)', 'raw common mean',
                            'causal common slope over preceding up-to-50ms input starts, raw units/s'],
                   target_scope='declared local stimuli only; no world/food/distance/reward/task trajectory',
                   hyperparameter_selection='none'),
        metrics=dict(late_window='response_end_ms in [450,600], terminal clamp heldout only',
                     sign='fraction pred_contrast*true_contrast>0 for nonzero +/-0.02; report pooled and each whole sequence',
                     neutral='max absolute per-sequence mean 0.85*tanh(6*pred_contrast) at contrast=0; also RMS and max absolute sample',
                     asymmetry_mapping='v2 target normalized command asymmetry=(R-L)/(R+L)=0.85*tanh(6*contrast)',
                     common='raw common MAE and v2 common drive MAE via .85*max(pred_common,0)/(max(pred_common,0)+.3)',
                     old_common='mean(old_commands) compared to .85*raw_common/(raw_common+.3)',
                     latency='from input switch at 300ms to first end sample beginning five consecutive correct-sign predictions; null if no response by 600ms; clamp nonzero and dynamic reversal',
                     trend='heldout dynamic family response_end_ms>=100: sign accuracy and MAE; paired current-matched rising/falling at input start300ms separately; controls excluded from fit',
                     uncertainty='descriptive deterministic sequence results; no iid timepoint confidence intervals',
                     separability='DN Euclidean mirror distances and terminal history-pair distances, descriptive, not independent classifier validation'),
        acceptance=dict(sign_accuracy_min=.95, neutral_normalized_asymmetry_max=.02,
                        rule='Both criteria pooled AND each evaluated clamp sequence, for both predeclared split directions; distinguish current and history probes. Common error/latency descriptive, no posthoc thresholds.',
                        temporal_rule='Report trend sign/MAE on heldout families plus paired current-matched slope-order accuracy. Temporal retention is unqualified irrespective of probe result.',
                        failure='One failed fixed linear probe is not proof of absent DN information; no sensor/controller change inferred solely from failure.'),
        checkpoint='Complete v,current,refractory,delay,external,rates,tick,total_spikes at initial,300ms,600ms for all 24; seq23 repeat of12 restores saved initial and saved midpoint',
        actual_current_storage='all stimulated neuron indices plus per-sample actual backend external current values, with exact zero-outside-support assertion; DN internal synaptic currents also saved',
        limits=['No further sequences, retuning or waveform changes after freeze.',
                'Blank and raw .04/.04 may have equal silent DNs but unequal old targets; diagnose, never fit contradictory silent labels.',
                'No runtime decoder weights, motor changes, physical cohort or qualification.',
                'Optional static real-body instrumentation sanity only, zero physical seconds.'],
        sensor=SENSOR, neural_profile=PROFILE, source_sha256=source_hashes(),
        data_sha256=json.loads((OUT/'stable-before.json').read_text())['canonical_sha256'],
        versions={p:importlib.metadata.version(p) for p in ['numpy','scipy','numba','flygym','mujoco']},
        dependency_record_sha256={name: file_sha(Path(importlib.metadata.distribution(name)._path)/'RECORD')
            for name in ['numpy','scipy','numba','flygym','mujoco']},
        interpreter_sha256=file_sha(Path(__import__('sys').executable).resolve()),
        python=platform.python_version(), execution=dict(threads=1, backend='original CPUBrainBackend/Brain full retained graph',
            original_venv_symlink=str((ROOT/'.venv').resolve()), isolated_pythonpath=str(ROOT/'src')))
    path = OUT/'protocol.json'
    if path.exists(): raise FileExistsError('Protocol already frozen')
    write_json(path, protocol)
    (OUT/'protocol.sha256').write_text(file_sha(path)+'\n')
    print('FROZEN', file_sha(path), flush=True)


def load_protocol():
    path = OUT/'protocol.json'
    if file_sha(path) != (OUT/'protocol.sha256').read_text().strip():
        raise ValueError('Frozen protocol changed')
    p = json.loads(path.read_text())
    if source_hashes() != p['source_sha256']:
        raise ValueError('Frozen experiment/source changed')
    return p


def run():
    from flyarena.connectome import Connectome
    from flyarena.neural import Brain
    from flyarena.backend import CPUBrainBackend
    from flyarena.experiments.sensor import encode_odor
    from flyarena.experiments.decoder import Decoder, target
    protocol = load_protocol()
    folder = OUT/'raw'
    folder.mkdir()  # Refuse overwriting or retrying a partly consumed assay.
    start = time.perf_counter()
    graph = Connectome(ROOT/'data', verify=True)
    backend = CPUBrainBackend(Brain(graph)); dn = graph.groups['descending']
    decoder = Decoder(ROOT/'data/connectome/research-v2/readout.npz')
    assert len(dn)==1314 and np.array_equal(dn,decoder.neurons)
    afferents = np.unique(np.concatenate([graph.groups['olfactory_left'],graph.groups['olfactory_right']]))
    outside = np.ones(graph.n,dtype=bool); outside[afferents]=False
    np.savez(folder/'neuron-identities.npz',dn_index=dn,dn_body_id=graph.ids[dn],
             afferent_index=afferents,afferent_body_id=graph.ids[afferents])
    receipt = dict(protocol_sha256=file_sha(OUT/'protocol.json'), neuron_count=graph.n, edge_count=graph.e,
                   dn_count=len(dn), afferent_count=len(afferents), graph_manifest_sha256=graph.manifest['sha256'],
                   sources=source_hashes(), sequences=[], started_unix=time.time())
    for row in protocol['sequences']:
        seq_start = time.perf_counter(); i=row['index']; prefix=folder/f'seq-{i:02d}'
        backend.reset(0)
        if i==23:
            with np.load(folder/'seq-12-start.npz',allow_pickle=False) as a: backend.restore(dict(a))
        np.savez_compressed(str(prefix)+'-start.npz',**backend.checkpoint())
        rates=[]; currents=[]; encoded=[]; commands=[]; dn_current=[]; spikes=[]
        raw=np.array(row['raw'])
        for k,pair in enumerate(raw):
            if k==30:
                if i==23:
                    with np.load(folder/'seq-12-middle.npz',allow_pickle=False) as a: backend.restore(dict(a))
                np.savez_compressed(str(prefix)+'-middle.npz',**backend.checkpoint())
            enc=encode_odor(*pair); backend.stimulate(*enc)
            assert not np.any(backend.brain.external[outside])
            currents.append(backend.brain.external[afferents].copy())
            counts=backend.advance(100)
            rates.append(backend.neural_output(dn)); encoded.append(enc)
            commands.append(decoder.command(rates[-1])); dn_current.append(backend.brain.current[dn].copy())
            spikes.append(counts[dn])
        np.savez_compressed(str(prefix)+'-final.npz',**backend.checkpoint())
        np.savez_compressed(str(prefix)+'-samples.npz',raw=raw,encoded=encoded,external_current=currents,
            dn_rates=rates,dn_synaptic_current=dn_current,dn_spikes=spikes,old_commands=commands,
            old_targets=np.array([target(pair) for pair in raw]),
            input_start_ms=protocol['input_start_ms'],response_end_ms=protocol['response_end_ms'])
        entry=dict(index=i,id=row['id'],wall_seconds=time.perf_counter()-seq_start,final_tick=backend.brain.tick,
                   total_spikes=backend.brain.total_spikes,
                   files={p.name:file_sha(p) for p in folder.glob(f'seq-{i:02d}-*.npz')})
        receipt['sequences'].append(entry)
        write_json(OUT/'run-progress.json',receipt)
        print(f"sequence {i+1}/24 {row['id']}: {entry['wall_seconds']:.2f}s; spikes={entry['total_spikes']}",flush=True)
    receipt['wall_seconds']=time.perf_counter()-start
    receipt['completed_unix']=time.time()
    write_json(OUT/'run-receipt.json',receipt)
    print('ASSAY_COMPLETE',receipt['wall_seconds'],flush=True)


def summarize(pred, truth, old_commands, seqs, protocol, baseline=False):
    time_ms=np.array(protocol['response_end_ms']); late=time_ms>=450
    per=[]; errors=[]; common_errors=[]; latencies=[]
    for i in seqs:
        row=protocol['sequences'][i]
        if row['family']!='terminal_clamp': continue
        c=truth[i,:,0]; common=truth[i,:,1]
        asym=pred[i,:,0] if baseline else .85*np.tanh(6*pred[i,:,0])
        common_prediction=old_commands[i].mean(axis=-1) if baseline else .85*np.maximum(0,pred[i,:,1])/(np.maximum(0,pred[i,:,1])+.3)
        cmerr=float(np.mean(abs(common_prediction[late]-.85*common[late]/(common[late]+.3))))
        record=dict(sequence=i,id=row['id'], common_drive_mae=cmerr)
        common_errors.extend(abs(common_prediction[late]-.85*common[late]/(common[late]+.3)).tolist())
        if row['terminal_contrast']:
            ok=asym*c>0
            record['sign_accuracy']=float(ok[late].mean())
            errors.extend(ok[late].tolist())
            latency=next((int(time_ms[k]-300) for k in range(30,56) if np.all(ok[k:k+5])),None)
            record['latency_ms']=latency; latencies.append(dict(sequence=i,latency_ms=latency))
        else:
            record.update(neutral_asymmetry_bias=float(asym[late].mean()),
                          neutral_asymmetry_rms=float(np.sqrt(np.mean(asym[late]**2))),
                          neutral_max_abs=float(np.max(abs(asym[late]))))
        if not baseline: record['raw_common_mae']=float(np.mean(abs(pred[i,late,1]-common[late])))
        per.append(record)
    neutral=max(abs(r['neutral_asymmetry_bias']) for r in per if 'neutral_asymmetry_bias' in r)
    passed=bool(np.mean(errors)>=.95 and neutral<=.02 and all(r.get('sign_accuracy',1)>=.95 for r in per))
    dynamics=[]
    for i in seqs:
        if protocol['sequences'][i]['family'] not in ['linear','sine']:continue
        ok=pred[i,:,0]*truth[i,:,0]>0
        latency=next((int(time_ms[k]-300) for k in range(30,56) if np.all(ok[k:k+5])),None)
        valid=time_ms>=100
        record=dict(sequence=i,reversal_latency_ms=latency,sign_accuracy=float(ok[valid].mean()))
        if not baseline:
            record.update(trend_sign_accuracy=float(np.mean(pred[i,valid,2]*truth[i,valid,2]>0)),
                          trend_mae=float(np.mean(abs(pred[i,valid,2]-truth[i,valid,2]))),
                          raw_common_mae=float(np.mean(abs(pred[i,valid,1]-truth[i,valid,1]))))
        dynamics.append(record)
    pairs=[]
    if not baseline:
        for m in protocol['matched_current_controls']:
            a,b,k=m['a'],m['b'],m['sample']
            if a in seqs and b in seqs:
                pairs.append(dict(a=a,b=b,sample=k,predicted_trends=[float(pred[a,k,2]),float(pred[b,k,2])],
                    true_trends=[float(truth[a,k,2]),float(truth[b,k,2])],
                    correct_order=bool(pred[a,k,2]>pred[b,k,2]),
                    both_signs_correct=bool(pred[a,k,2]>0 and pred[b,k,2]<0)))
    return dict(passed_engineering_criteria=passed,late_sign_accuracy=float(np.mean(errors)),
        neutral_max_absolute_sequence_bias=neutral,common_drive_mae=float(np.mean(common_errors)),
        late_nonzero_samples=len(errors),clamp_sequences=per,dynamic_sequences=dynamics,
        matched_current_trend_pairs=pairs,latencies=latencies)


def analyze():
    protocol=load_protocol()
    if (OUT/'summary.json').exists(): raise FileExistsError('No probe retuning/overwrite')
    start=time.perf_counter()
    data=[]
    for i in range(24):
        with np.load(OUT/f'raw/seq-{i:02d}-samples.npz',allow_pickle=False) as a: data.append(dict(a))
    rates=np.stack([d['dn_rates'] for d in data]); raw=np.stack([d['raw'] for d in data])
    commands=np.stack([d['old_commands'] for d in data]); truth=labels(raw)
    silence=np.linalg.norm(rates,axis=-1)<=1e-9
    old_asym=(commands[...,1]-commands[...,0])/np.maximum(commands.sum(axis=-1),1e-12)
    old_pred=np.stack([old_asym,np.zeros_like(old_asym),np.zeros_like(old_asym)],axis=-1)
    summary=dict(protocol_sha256=file_sha(OUT/'protocol.json'),splits={},
        baseline=summarize(old_pred,truth,commands,list(range(20)),protocol,True))
    predictions={'labels':truth,'old_asymmetry':old_asym,'silence':silence}
    for split in protocol['splits']:
        reports={}
        for mode in protocol['feature_modes']:
            x=causal_features(rates,mode)
            mask=np.zeros((24,60),bool); mask[split['train'],9:]=True; mask &= ~silence
            model=fit_probe(x[mask],truth[mask])
            pred=predict_probe(model,x,silence)
            np.savez_compressed(OUT/f"probe-{split['id']}-{mode}.npz",**model,training_mask=mask)
            result=summarize(pred,truth,commands,split['evaluate'],protocol)
            result.update(training_rows=int(mask.sum()),training_sequences=split['train'],
                          evaluation_sequences=split['evaluate'],varying_feature_count=int(model['active'].sum()))
            reports[mode]=result; predictions[f"{split['id']}_{mode}"]=pred
        summary['splits'][split['id']]=reports
    pairs=[]
    for i in range(6):
        delta=rates[i,30:]-rates[i+6,30:]
        pairs.append(dict(a=i,b=i+6,terminal_history_dn_rms_hz=float(np.sqrt(np.mean(delta**2))),
                          late_history_dn_rms_hz=float(np.sqrt(np.mean(delta[14:]**2)))))
    mirrors=[]
    for a,b in [(0,2),(3,5),(6,8),(9,11),(12,13),(14,15),(16,17),(18,19)]:
        dist=np.linalg.norm(rates[a]-rates[b],axis=-1)
        mirrors.append(dict(a=a,b=b,late_dn_distance_mean_hz=float(dist[44:].mean()),
                            late_dn_distance_min_hz=float(dist[44:].min())))
    summary['separability']=dict(history_pairs=pairs,mirror_pairs=mirrors)
    summary['controls']=dict(blank_max_dn_rate=float(rates[20].max()),low004_max_dn_rate=float(rates[21].max()),
        blank_low_dn_exact_equal=bool(np.array_equal(rates[20],rates[21])),
        low004_old_target=data[21]['old_targets'][0].tolist(),blank_old_target=data[20]['old_targets'][0].tolist(),
        silent_rows_excluded=int(silence.sum()),cue_off_last_command=commands[22,-1].tolist(),
        cue_off_last_dn_norm=float(np.linalg.norm(rates[22,-1])),
        diagnostic='Identical silent states with unequal targets are a representation limitation; neither state is used as a conflicting training label.')
    for mode in ['current','history']:
        summary[f'{mode}_passes_both_splits']=all(r[mode]['passed_engineering_criteria'] for r in summary['splits'].values())
    summary['decision']=('A separately versioned decoder candidate is supported by the fixed probe gates; no motor or retention qualification.'
        if summary['history_passes_both_splits'] or summary['current_passes_both_splits'] else
        'The fixed linear probes do not meet all prespecified engineering gates. Dynamic decoder deployment is not justified. Failure does not establish absent neural information; a bounded nonlinear readout candidate may be investigated using separate fresh waveforms, without sensor/motor changes or retention claims.')
    summary['analysis_wall_seconds']=time.perf_counter()-start
    np.savez_compressed(OUT/'predictions.npz',**predictions)
    write_json(OUT/'summary.json',summary)
    plot(protocol,data,predictions,summary)
    print(json.dumps(summary,indent=2),flush=True)


def plot(protocol,data,predictions,summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    t=np.array(protocol['response_end_ms'])
    first=protocol['splits'][0]['id']
    fig,axs=plt.subplots(3,2,figsize=(12,9),layout='constrained')
    for col,i in enumerate([8,11]):
        ax=axs[0,col]
        ax.plot(t,predictions['labels'][i,:,0],color='black',label='input contrast')
        for mode in ['current','history']:
            ax.plot(t,predictions[f'{first}_{mode}'][i,:,0],label=f'{mode} DN probe')
        ax.set_title(protocol['sequences'][i]['id']); ax.set_ylabel('Normalized raw contrast'); ax.axvline(300,color='.6',ls=':')
        ax.legend(fontsize=8)
    for col,i in enumerate([16,18]):
        ax=axs[1,col]
        ax.plot(t,predictions['labels'][i,:,2],color='black',label='causal stimulus slope')
        for mode in ['current','history']:
            ax.plot(t,predictions[f'{first}_{mode}'][i,:,2],label=f'{mode} DN probe')
        ax.axvline(310,color='.6',ls=':'); ax.set_ylabel('Common slope (raw/s)'); ax.set_title(protocol['sequences'][i]['id']); ax.legend(fontsize=8)
    for col,i in enumerate([7,10]):
        ax=axs[2,col]
        ax.plot(t,predictions['old_asymmetry'][i],label='Frozen v2')
        for mode in ['current','history']:
            ax.plot(t,.85*np.tanh(6*predictions[f'{first}_{mode}'][i,:,0]),label=mode)
        ax.axhspan(-.02,.02,color='green',alpha=.1); ax.set_ylabel('Neutral normalized asymmetry'); ax.set_title(protocol['sequences'][i]['id']); ax.legend(fontsize=8)
    for ax in axs.flat: ax.set_xlabel('Response end (ms)')
    fig.suptitle('Predeclared full-connectome diagnostic: whole-history / sine-family holdouts')
    fig.savefig(OUT/'diagnostic-traces.png',dpi=170); fig.savefig(OUT/'diagnostic-traces.pdf'); plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    names=['v2']; sign=[summary['baseline']['late_sign_accuracy']]; bias=[summary['baseline']['neutral_max_absolute_sequence_bias']]
    for split,result in summary['splits'].items():
        for mode,r in result.items():
            names.append(('primary ' if split==first else 'reciprocal ')+mode)
            sign.append(r['late_sign_accuracy']);bias.append(r['neutral_max_absolute_sequence_bias'])
    axs[0].bar(names,sign);axs[0].axhline(.95,color='red',ls='--');axs[0].set_ylabel('Late nonzero sign accuracy');axs[0].set_ylim(0,1.05)
    axs[1].bar(names,bias);axs[1].axhline(.02,color='red',ls='--');axs[1].set_ylabel('Maximum absolute neutral sequence bias')
    for ax in axs: ax.tick_params(axis='x',rotation=25)
    fig.suptitle('Diagnostic gates; deterministic time samples are not independent trials')
    fig.savefig(OUT/'diagnostic-gates.png',dpi=170);fig.savefig(OUT/'diagnostic-gates.pdf');plt.close(fig)


def verify():
    protocol=load_protocol(); receipt=json.loads((OUT/'run-receipt.json').read_text())
    from flyarena.experiments.sensor import encode_odor
    from flyarena.connectome import Connectome
    graph=Connectome(ROOT/'data',verify=True)
    with np.load(OUT/'raw/neuron-identities.npz') as a: aff=a['afferent_index']
    assert len(receipt['sequences'])==24
    checks=[]
    for row in receipt['sequences']:
        i=row['index']
        for name,sha in row['files'].items(): assert file_sha(OUT/'raw'/name)==sha
        with np.load(OUT/f'raw/seq-{i:02d}-samples.npz') as d:
            assert d['dn_rates'].shape==(60,1314)
            assert np.array_equal(d['input_start_ms'],np.arange(60)*10)
            assert np.array_equal(d['response_end_ms'],np.arange(1,61)*10)
            assert np.array_equal(d['raw'],protocol['sequences'][i]['raw'])
            assert np.array_equal(d['encoded'],np.array([encode_odor(*x) for x in d['raw']]))
            expected=np.zeros((60,len(aff)))
            for j,side in enumerate(['left','right']):
                expected[:,np.isin(aff,graph.groups['olfactory_'+side])]=48*d['encoded'][:,j,None]
            assert np.array_equal(d['external_current'],expected)
        for part,tick in [('start',0),('middle',3000),('final',6000)]:
            with np.load(OUT/f'raw/seq-{i:02d}-{part}.npz') as a:
                assert set(a.files)=={'v','current','refractory','delay','external','rates','tick','total_spikes'}
                assert int(a['tick'])==tick
                assert a['delay'].shape==(19,graph.n)
                assert all(np.isfinite(a[n]).all() for n in a.files)
    for part in ['start','middle','final','samples']:
        with np.load(OUT/f'raw/seq-12-{part}.npz') as a,np.load(OUT/f'raw/seq-23-{part}.npz') as b:
            assert a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
    checks.append('All arrays, 72 full checkpoint layouts/ticks, serialized input/response grids, 24 waveform identities and actual afferent currents verified; exact reference/repeat sample and full checkpoint equality.')
    for split in protocol['splits']:
        assert not set(split['train'])&set(split['evaluate'])
        assert not set(protocol['controls'])&set(split['train']+split['evaluate'])
        for mode in protocol['feature_modes']:
            with np.load(OUT/f"probe-{split['id']}-{mode}.npz") as a:
                assert not a['training_mask'][split['evaluate']+protocol['controls']].any()
                assert not a['training_mask'][:,:9].any()
                all_rates=np.stack([np.load(OUT/f'raw/seq-{i:02d}-samples.npz')['dn_rates'] for i in range(24)])
                x=causal_features(all_rates,mode)
                expected=np.zeros((24,60),bool);expected[split['train'],9:]=True
                expected &= np.linalg.norm(all_rates,axis=-1)>1e-9
                assert np.array_equal(expected,a['training_mask'])
                assert np.array_equal(a['mean'],x[expected].mean(axis=0))
                sd=x[expected].std(axis=0)
                assert np.array_equal(a['active'],sd>1e-8)
                assert np.array_equal(a['scale'],np.where(sd>1e-8,sd,1.))
    checks.append('Whole-sequence/history/waveform splits and training masks verified; controls absent from fitting.')
    before=json.loads((OUT/'stable-before.json').read_text()); original=Path(before['source_root'])
    preservation={}
    for key in ['tracked_sha256','canonical_sha256','git_metadata_sha256']:
        prefix=original/'.git' if key=='git_metadata_sha256' else original
        # Metadata keys already include .git.
        prefix=original
        changed=[name for name,sha in before[key].items() if not (prefix/name).exists() or file_sha(prefix/name)!=sha]
        preservation[key]={'count':len(before[key]),'changed':changed};assert not changed
    history_changes=[]
    for name,stats in before['history_size_mtime_ns'].items():
        p=original/name
        if not p.exists() or [p.stat().st_size,p.stat().st_mtime_ns]!=stats:history_changes.append(name)
    preservation['history_metadata']={'count':len(before['history_size_mtime_ns']),'changed':history_changes,
        'scope':'file size/mtime, not content hashes; no historical carrier logs read'}
    assert not history_changes
    status=subprocess.check_output(['git','--no-optional-locks','-C',str(original),'status','--porcelain']).decode()
    head=subprocess.check_output(['git','-C',str(original),'rev-parse','HEAD']).decode().strip()
    assert status==before['status'] and head==before['head']==BASE
    write_json(OUT/'verification.json',dict(protocol_sha256=file_sha(OUT/'protocol.json'),checks=checks,
        preservation=preservation,original_status=status,original_head=head,verified_unix=time.time(),
        exact_restore=True,sequence_count=24,sample_count=1440,dn_values=1440*1314))
    print('VERIFIED 24 sequences / 1440 samples / 1,892,160 DN rates; original snapshot preserved',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','analyze','verify'])
    args=p.parse_args();globals()[args.action]()

if __name__=='__main__':main()
