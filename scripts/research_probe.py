#!/usr/bin/env python3
"""Run one real probe, or the matched full-graph engineering acceptance suite."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from flyarena.common import DATA, VAR, write_json
from flyarena.compiler import Compiler
from flyarena.connectome import Connectome
from flyarena.contracts import FlySpec
from flyarena.experiments.probes import run_probe, verify_evidence, profile_manifest

def subject(compiler, var, name, ident, changes=None):
    # Plain legacy FlySpec dictionary: does not depend on intervention additions.
    spec={"name":name,"connectome_sha256":compiler.graph.manifest["sha256"]} | (changes or {})
    artifact=compiler.compile(FlySpec.model_validate(spec),publish=True,root=var)
    return {"id":ident,"artifact_id":artifact["artifact_id"],"spec":spec,"name":name,"reference_kind":"wildtype" if changes is None else "user"}

def validate(data, var, output, seconds, seed=42):
    if seed % 2: raise ValueError("validation seed must be even for mirrored pairing")
    output.mkdir(parents=True,exist_ok=False)
    compiler=Compiler(Connectome(data,verify=True))
    # Validation publishes only into its own evidence tree.
    var=output/"compiler-state"
    wt=subject(compiler,var,"Calibration baseline","1"*32)
    mutation=subject(compiler,var,"Threshold shift +1mV","2"*32,{"neuron_parameters":{"tau_scale":1.,"threshold_shift_mv":1.}})
    trials=[("wt-left",wt,"gradient-v2",seed,{}), ("wt-repeat",wt|{"id":"3"*32},"gradient-v2",seed,{}),
            ("wt-right",wt,"gradient-v2",seed+1,{}), ("mutation-left",mutation,"gradient-v2",seed,{}),
            ("output-ablation",wt,"gradient-v2",seed,{"ablation":"output"}),
            ("blank-v2",wt,"gradient-v2",seed,{"stimulus":"blank"}),
            ("blank-v1",wt,"gradient-v2",seed,{"stimulus":"blank","decoder_version":"v1"}),
            ("delayed-cue",wt,"delayed-cue-v2",seed,{}), ("bifurcation",wt,"bifurcation-v2",seed,{}),
            ("heldout-left",wt,"gradient-v2",seed+10000,{}), ("heldout-right",wt,"gradient-v2",seed+10001,{})]
    reports={}
    for name,fly,pid,seed,options in trials:
        print(f"running {name}",flush=True)
        reports[name]=run_probe(fly,pid,seed,seconds,output/name,data=data,var=var,**options)
        print(json.dumps({"trial":name,"metrics":reports[name]["metrics"]}),flush=True)
    return summarize(output,reports)

def summarize(output,reports=None):
    if reports is None:
        reports={p.parent.name:json.loads(p.read_text()) for p in output.glob('*/report.json')}
    required={"wt-left","wt-repeat","wt-right","mutation-left","output-ablation","blank-v2","blank-v1","delayed-cue","bifurcation","heldout-left","heldout-right"}
    if not required.issubset(reports): raise ValueError(f"Missing required validation trials: {sorted(required-set(reports))}")
    for name,r in reports.items():verify_evidence(output/name,r)
    def yaw(name,t=.5):
        tr=reports[name]["trajectory"]
        vals=np.unwrap([r['yaw'] for r in tr]); i=min(range(len(tr)),key=lambda i:abs(tr[i]['time']-t))
        return float(vals[i]-vals[0])
    base=reports['wt-left']; repeat=reports['wt-repeat']; mutation=reports['mutation-left']
    a=np.array([[r['x'],r['y']] for r in base['trajectory']]);b=np.array([[r['x'],r['y']] for r in mutation['trajectory']])
    checks={"full_graph":json.loads((output/'wt-left/receipt.json').read_text())['neuron_count']>100000,
            "repeat_identical":base['trajectory']==repeat['trajectory'] and base['neural_trace']==repeat['neural_trace'],
            "subject_independent_condition":base['condition_key']==repeat['condition_key']==mutation['condition_key'],
            "left_turn_transfer":yaw('wt-left')>.05,"right_turn_transfer":yaw('wt-right')<-.05,
            "v2_blank_stops":reports['blank-v2']['metrics']['mean_drive'] < 1e-8 and reports['blank-v2']['metrics']['displacement_mm'] < .25
                and reports['blank-v2']['metrics']['path_length_mm'] < .05*reports['blank-v1']['metrics']['path_length_mm'],
            "v1_blank_moves":reports['blank-v1']['metrics']['path_length_mm']>1.,
            "ablation_stops":reports['output-ablation']['metrics']['mean_drive'] < 1e-8 and reports['output-ablation']['metrics']['displacement_mm'] < .25,
            "blank_matches_passive_ablation":reports['blank-v2']['trajectory']==reports['output-ablation']['trajectory'],
            "cue_disappears":all(r['raw_odor_left']==r['raw_odor_right']==0 for r in reports['delayed-cue']['neural_trace'] if r['time']>=1.02),
            "post_cue_stops":reports['delayed-cue']['metrics']['post_cue_mean_drive']<.05,
            "bifurcation_upright":min(r["upright_z"] for r in reports["bifurcation"]["neural_trace"]) > .8}
    if "heldout-left" in reports and "heldout-right" in reports:
        checks["heldout_left_turn_transfer"] = yaw("heldout-left") > .05
        checks["heldout_right_turn_transfer"] = yaw("heldout-right") < -.05
    summary={"schema_version":"science-validation/v2","checks":checks,"passed":all(checks.values()),
             "yaw_at_0_5_seconds":{"left":yaw('wt-left'),"right":yaw('wt-right')},
             "mutation_mean_trajectory_divergence_mm":float(np.linalg.norm(a-b,axis=1).mean()),
             "metrics":{n:r['metrics'] for n,r in reports.items()},
             "minimum_upright_z":{n:min(t["upright_z"] for t in r["neural_trace"]) for n,r in reports.items()},
             "receipts":{n:r['receipt_sha256'] for n,r in reports.items()},
             "interpretation":"Measured engineering transfer, repeatability and ablation. Mutation difference is not advantage; absence of branch choice/food is censored, not success. Temporal persistence does not prove memory."}
    write_json(output/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True)
    if not summary['passed']:raise RuntimeError('engineering acceptance failed; inspect measured checks')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=DATA);p.add_argument('--var',type=Path,default=VAR)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=int,default=2)
    p.add_argument('--validate',action='store_true');p.add_argument('--summarize',action='store_true')
    p.add_argument('--fly',type=Path);p.add_argument('--probe',default='gradient-v2');p.add_argument('--seed',type=int,default=42)
    args=p.parse_args()
    if args.summarize:summarize(args.output)
    elif args.validate:validate(args.data,args.var,args.output,args.duration,args.seed)
    else:
        if not args.fly:p.error('--fly JSON dictionary is required for a single probe')
        result=run_probe(json.loads(args.fly.read_text()),args.probe,args.seed,args.duration,args.output,data=args.data,var=args.var)
        print(json.dumps({'status':result['status'],'metrics':result['metrics'],'receipt_sha256':result['receipt_sha256']},indent=2))
