"""Compact actual-state comparison and noncircular v16 evidence closure."""
import argparse
import json
from pathlib import Path
import shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flyarena.common import file_sha, write_json
from flyarena.experiments.mechanical_v16 import PROFILE, CONTROL, validate_freeze
from flyarena.experiments.behavior_v12_correction import _junit_counts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--trusted-registration-sha256',required=True);args=parser.parse_args()
    root=args.output.resolve();repo=args.repo.resolve();reg=validate_freeze(root)
    if file_sha(root/'registration.json')!=args.trusted_registration_sha256 or (root/'output-inventory.json').exists():raise ValueError('invalid anchor or already closed')
    terminal=json.loads((root/'execution-terminal.json').read_text())
    if terminal['outcome']!='completed':raise ValueError('cannot report complete evidence from incomplete execution')
    analysis=json.loads((root/'development-analysis.json').read_text());verified=json.loads((root/'development-independent-verification.json').read_text())
    if not verified['passed'] or verified['analysis_sha256']!=file_sha(root/'development-analysis.json') or verified['registration_sha256']!=args.trusted_registration_sha256:raise ValueError('independent receipt binding mismatch')
    tests=json.loads((root/'tests/receipt.json').read_text());junit=root/'tests/junit.xml'
    counts=_junit_counts(junit)
    if tests['junit_sha256']!=file_sha(junit) or counts!=(tests['tests'],0,0,0) or tests['registration_sha256']!=args.trusted_registration_sha256:raise ValueError('actual test evidence mismatch')
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharex=True,constrained_layout=True)
    for row,(profile,case,label) in enumerate([(CONTROL,'straight-02','Unchanged v15'),(PROFILE,'straight-02','V16 minimal relaxation')]):
        trial=analysis['trials'][f'{profile}--42--{case}']
        with np.load(root/'development-derived'/trial['derived_npz'],allow_pickle=False) as data:
            ticks=data['ticks']*.0001;sel=(ticks>=.6)&(ticks<=1.)
            for leg,name in enumerate(('LF','LM','LH','RF','RM','RH')):
                axes[row,0].plot(ticks[sel],data['endpoint_whole_foot_min_height'][sel,leg],lw=.9,label=name)
                axes[row,1].plot(ticks[sel],data['interval_summed_positive_normal'][sel,leg],lw=.9,label=name)
        axes[row,0].axhline(.02,color='black',ls='--',lw=.8);axes[row,0].set_ylabel(label+'\nMinimum whole-foot height (mm)')
        axes[row,1].set_ylabel('Summed positive normal force\n(native units)')
    axes[0,0].legend(ncol=6,fontsize=8);axes[-1,0].set_xlabel('Actual physical time (s)');axes[-1,1].set_xlabel('Actual physical time (s)')
    fig.suptitle('V16 actual endpoint clearance and interval support — seed 42, straight c=0.2, a=0\n0.6–1.0 s excerpt; qualification uses every registered complete cycle')
    figure=root/'actual-clearance-support.png';fig.savefig(figure,dpi=150);plt.close(fig)
    rows=['# V16 whole-foot retraction feedback mechanical experiment','',f"Development candidate passed: **{analysis['candidate_passed']}**. Independent numerical verification passed: **{verified['passed']}**.",'','One fixed engineered two-direction relaxation changes only the v15 budget-limited swing allocation. Already-feasible v15 allocation remains unchanged. The same instantaneous angular budget is retained, with the smallest row-space amplitude in the selected two-direction plane when feasible, and bounded maximum normal authority otherwise. This explicitly permits tangential motion; AP, yaw, ALL-vertex clearance, actual unloaded dwell, support and slip remain decisive. Fresh unchanged v15 is the control. Plant, gains, scalar/phase dynamics, adhesion, subjects and gates remain unchanged.','','| Profile | Seed | Case | Speed mm/s | Yaw rad | Recovery | Support/slip | Stop | Failed gates |','|---|---:|---|---:|---:|---|---|---|---|']
    for name,t in analysis['trials'].items():
        profile,seed,case=name.split('--');g=t['gates'];bad=', '.join(k for k,v in g.items() if not v) or 'none'
        rows.append(f"| {profile} | {seed} | {case} | {t['forward_mean_mm_s']:.6f} | {t['net_active_yaw_rad']:.6f} | {g.get('recovery','exempt')} | {g.get('support_slip','exempt')} | {g['stop']} | {bad} |")
    rows+=['','## Feedback and limits','', 'Candidate trigger counts and raw retraction maxima by leg (LF, LM, LH, RF, RM, RH):','']
    for name,t in analysis['trials'].items():
        if name.startswith(PROFILE+'--'):
            rows.append(f"- {name}: triggers {t['feedback']['trigger_counts']}; raw maxima {t['feedback']['raw_retraction_max']}; raw scalar >80 active ticks {t['feedback']['raw_retraction_over80_ticks']}.")
    rows+=['','## Registered relaxation diagnostics','']
    for name,t in analysis['trials'].items():
        if name.startswith(PROFILE+'--'):
            rows.append(f"- {name}: branch leg-rows unchanged/relaxed/maximum-authority {t['relaxation']['branches_active_leg_rows']}; maximum row-space amplitude (rad) {t['relaxation']['rowspace_component_max_rad']}; positive local residual rows {t['relaxation']['positive_local_residual_leg_rows']}. Branch zero includes inactive/stance zero diagnostics; local residual is not a physical admission gate.")
    rows+=['','## Speed dose gates','']+[f'- {key}: {value}' for key,value in analysis['aggregate_gates'].items()]
    rows+=['','## Evidence and limits','',f"Actual physical seconds: {terminal['resources']['mechanical_seconds']}. Full network seconds: 0. Peak RSS: {terminal['resources']['peak_rss_bytes']} bytes. Runtime: {terminal['resources']['wall_seconds']:.2f} seconds.",f"Registration SHA-256: `{args.trusted_registration_sha256}`.",f"Actual nonphysical tests: {tests['tests']} passing cases; JUnit SHA-256 `{tests['junit_sha256']}`.",'','Raw force/cache rows retain their prestate ownership; corrected endpoints use q[k], and every coherent contact velocity uses J(q[k-1])v[k-1]. Tick zero contributes no quadrature. Every complete swing/stance, ambiguity, reversal, tie, boundary partial, passive state and joint tracking measurement is retained.','', 'Development failure blocks held-out, repeat, restoration, neural, phenotype and product admission. This experiment does not establish coordinated walking unless all frozen gates and later qualification pass. No coefficient was selected from its outcome.','','Actual walking remains the first unresolved goal, followed by the unchanged original neural 15 predicates, matched Wild Type/official/user phenotype panels and causal ablations, then clear design identity and actual-state Lab/API/replay integration.','','![Actual clearance and support](actual-clearance-support.png)','']
    rows+=['','## Conditional qualification','']
    for label,path in [('held-out',root/'evaluation-analysis.json'),('exact repeat',root/'repeat-verification.json'),('active restoration',root/'restoration/result.json')]:
        if path.exists():
            result=json.loads(path.read_text());rows.append(f"- {label}: {result.get('candidate_passed',result.get('passed'))}.")
        else:rows.append(f'- {label}: unrun; development did not admit continuation.')
    report='\n'.join(rows);(root/'RESULTS.md').write_text(report)
    (repo/'docs/BEHAVIOR_V16_RESULTS.md').write_text(report.replace('(actual-clearance-support.png)','(evidence/behavior-v16-actual-clearance-support.png)'))
    (repo/'docs/evidence').mkdir(exist_ok=True);shutil.copyfile(figure,repo/'docs/evidence/behavior-v16-actual-clearance-support.png')
    write_json(root/'resource-closure.json',{'schema':'behavior-v16-resources/v1','execution':terminal['resources'],'physics_seconds':terminal['resources']['mechanical_seconds'],'neural_seconds':0,'workers':1,'closed_after_semantic_verification':True,'registration_sha256':args.trusted_registration_sha256,'scientific_admission':False})
    payload={str(p.relative_to(root)):{'bytes':p.stat().st_size,'sha256':file_sha(p)} for p in sorted(root.rglob('*')) if p.is_file()}
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('nonregular output')
    write_json(root/'output-inventory.json',{'schema':'behavior-v16-output-inventory/v1','registration_sha256':args.trusted_registration_sha256,'payload':payload,'payload_files':len(payload),'payload_bytes':sum(v['bytes'] for v in payload.values()),'self_exclusion':'output-inventory.json; parent binds hash and closed size externally','no_files_may_be_added_after_inventory':True})
    print(json.dumps({'closed':True,'payload_files':len(payload),'candidate_passed':analysis['candidate_passed'],'inventory_sha256':file_sha(root/'output-inventory.json')}))


if __name__=='__main__':main()
