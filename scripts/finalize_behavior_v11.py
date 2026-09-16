"""Exclusive final receipts for the complete v11 diagnostic; no new analysis."""
import hashlib,json,os,sys,time
from pathlib import Path
from flyarena.experiments.realization_io_v11 import ROOT,OUT,SCRATCH,sha,exclusive_json,json_bytes,Budget

CONTROL=Path('/Users/lexa/Desktop/lexa/omega/fly-arena/var/sshx/behavior-v11')

def main():
    budget=Budget();budget.check()
    execution=json.loads((OUT/'execution-terminal.json').read_text())
    verify=json.loads((OUT/'verification.json').read_text())
    facts=json.loads((OUT/'report/facts.json').read_text())
    for name in ['execution-terminal.json','verification.json','report-terminal.json','cross-tabs-terminal.json']:
        if not json.loads((OUT/name).read_text())['complete']:raise ValueError('incomplete prerequisite '+name)
    if not json.loads((OUT/'visual-qa.json').read_text())['passed']:raise ValueError('visual QA missing')
    for mapping in [json.loads((OUT/'inputs.json').read_text()),json.loads((OUT/'implementation-seal.json').read_text())['files']]:
        for path,item in mapping.items():
            if sha(path)!=item['sha256']:raise ValueError('final hash mismatch: '+path)
    changed={}
    for base in ['src','tests','scripts','docs']:
        for p in sorted((ROOT/base).rglob('*')):
            if p.is_file() and ('v11' in p.name.lower()) and p.suffix in ['.py','.sh','.md']:
                changed[str(p.relative_to(ROOT))]=sha(p)
    exclusive_json(OUT/'final-source-manifest.json',{'schema':'distal-final-source-manifest/v11','files':changed,
                    'note':'Audit modules/tests unchanged from pre-outcome seal; later scripts/docs only report, independently verify, cross-tab and finalize retained measurements.'})
    # Log is written from this in-memory text only; never read back.
    log='''# v11 implementation worker receipt

Completed the approved distal-foot realization audit in the isolated target.
All28 nonzero cases, exactticks6000..25000 and fixedactual/command/unit-r1 records
were analyzed; no physical/neural seconds, reset, controller advancement, new
candidate, sweep, gain/lift/IK choice or runtime/API change.

Registration preceded outcomes. It binds2023 source/input files and30 native
mesh/material-point records. The source/transmission mapping and right-axis
conversion were tested, then the computational implementation was exclusively
sealed. A pre-outcome addendum corrects only a deadline field that held the task
start epoch. No parser, measurement, reference or audit algorithm changed after
execution began. One pre-seal text-only source edit used the system python3;
all numerical registration/tests/audit/report/verification used the exact
requested venv interpreter. An initial dependency import requested an automatic
OS-temp Matplotlib cache; subsequent runs fixed all caches and tempfiles to the
owned scratch, and no persistent fallback cache remains. These setup details did
not produce scientific outcomes or change any original source/evidence.

All28 completed without scientific/retention exceptions. The audit retains
532028 dense sample times /1596084 record-times in560 fixed-schema numeric chunks;
53228 geometry overlaps matchbitwise; commands match installed source equations
exactly; original165766 qualifying bouts match boundaries/metrics; all178073
contactruns and8778 parsed intervals remain. All17 contract tests passed,
including meaningful native geometric and fault-retention tests. Independent
saved-data verification passed allcases/chunks/504 summaryrows and2520 explicit
world-mesh checks. Both scientific figures were generated and visually inspected.

New diagnosis: tarsus5 limits all dense hind-foot records and actualhind clearance
never reaches.02mm in any of28 windows. Command geometry usually intersects the
floor at actualroot/passive pose. Nativeunit excursion supplies some potential
clearance but is poorly aligned with actualprotraction: cadence76/168 peaks
using referenceAP intervals become17/168 on actualAP intervals, versus0/168actual.
This is not a demonstrated amplitude remedy. Fixed-root intersections cannot
exclude dynamicbody adjustment. Positive reconstructed normal force occurs on
52.995% of cadencecontact-free samples; distance-basedcontactflag is not support.
All10788 originallysingle-sample cadence stances have nonzero densemotion.
85/509 completecadence support envelopes move>=.15mm, maximum1.172581mm, but
all509 are ambiguous and gaps remain; this is not proof of loadedcontact slip.
No olddecision is regraded. Force estimates are nativeforward reconstructions;
Jacobian correlations/decomposition have explicit finite-difference/integrated
residuals and do not establish causes.

Physical remedy selection remains inconclusive. One bounded next question:
Can source-native excursion become actual>.02mm hind clearance during actual
protraction with free root/passive response while preserving the original
support/upright/speed/turn/stop bounds? Only a later separatelyregistered single
physicalcandidate may test that. Original15gates, untouched31042/31043,
fullgraph/phenotype/repeat/ablation and existingLab/API/replay path remainrequired.

No peer reasoning/review result, protocol transcript or prior log was read.
No subagents, installs, remote/Git/GitHub/service/auth/browser actions were used.
Existing v10inputs/dependencies/data/artifacts remained read-only. Durable
failure receipts and emergencyprefixes are implemented/tested, with explicit
acknowledgment that totalfilesystemfailure cannot guarantee durable evidence.
'''
    logpath=CONTROL/'implementation.log.md'
    with logpath.open('x') as f:f.write(log);f.flush();os.fsync(f.fileno())
    indexed={str(p.relative_to(OUT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(OUT.rglob('*')) if p.is_file()}
    exclusive_json(OUT/'evidence-index.json',{'schema':'distal-evidence-index/v11','files':indexed,
        'excludes':'This index and final resource/completion receipts; those bind the index separately. Control envelope/log/done are outside evidence root.'})
    measured=budget.check();control_bytes=logpath.stat().st_size
    # Bound all remaining receipts rather than pretending to measure a file
    # before it exists. Reserved64KiB is far larger than the concrete payloads.
    resources={'task_wall_seconds_to_finalization':time.time()-1789577628,
               'audit_process':execution['resources'],'independent_verification':verify['result']['resources'],
               'new_output_bytes_before_final_receipts':measured['new_bytes']+control_bytes,
               'final_new_output_upper_bound_bytes':measured['new_bytes']+control_bytes+65536,
               'peak_observed_rss_bytes':max(execution['resources']['peak_rss_bytes'],verify['result']['resources']['peak_rss_bytes']),
               'workers':1,'physical_seconds':0,'neural_seconds':0,'sweeps':0,'installs':0,
               'caps':{'wall_seconds':5400,'rss_bytes':8*1024**3,'new_output_bytes':2*1024**3},
               'measurement_note':'Task wall includes setup/tests/reporting/finalization. New-output upper bound includes source/docs, owned scratch/cache, evidence and control receipts. Per-process CPU counters are not claimed to be summed task CPU.'}
    if resources['final_new_output_upper_bound_bytes']>2*1024**3:raise RuntimeError('final output cap')
    exclusive_json(OUT/'final-resources.json',resources)
    evidence_names=['registration.json','registration-addendum.json','inputs.json','native.json','implementation-seal.json',
                    'execution-terminal.json','all-conditions.json','cross-tabs.json','verification.json','visual-qa.json',
                    'report/manifest.json','final-source-manifest.json','evidence-index.json','final-resources.json']
    conclusion={
      'verdict':'implemented',
      'scientific_verdict':'Complete diagnostic; physical-remedy selection remains causally inconclusive. v10 failed qualification remains unchanged; no walking/phenotype/API admission.',
      'target':str(ROOT),'changed_file_hashes':changed,
      'registration_facts':{'registration_before_outcomes':True,'bound_input_source_files':2023,'native_tarsal_meshes':30,
        'parser':'Increasing2pi cells; earliest PEP/AEP with1e-12mm ties; every reversal/tie/partial/degenerate interval retained; own-record and actual-interval paired comparisons.',
        'fixed_references':'Actual; recorded position targets through native transmissions; installed compatible spline exactlyr=1. Actualroot/passive qpos held fixed; original right-axis conversion exactlyonce.',
        'pre_outcome_addendum':'Deadline field mistakenly encoded start epoch; exclusive addendum fixes deadline1789583028 before outcomes; no scientific rules changed.'},
      'evidence_facts':{'root':str(OUT),'sha256':{n:sha(OUT/n) for n in evidence_names},
        'dense_sample_times':532028,'geometry_record_times':1596084,'numeric_chunks':560,'bitwise_geometry_overlap_rows':53228,
        'retained_parsed_intervals':8778,'retained_contact_runs':178073,'original_qualifying_bouts_verified':165766,'all_condition_leg_record_rows':504,
        'command_source_max_error_rad':0.0,'native_force_balance_max_residual':facts['checks']['max_force_balance_residual_native'],
        'figures':'All-condition matrix and fixedseed42straight0.2/all6legs/fullwindow plot generated and visually inspected.',
        'preservation':'Originalraw/source/decision/thresholds/subjects/artifacts unchanged and finally rehashed. Oldfailure remains verbatim. No oldrecorder/correctionrunner imported.'},
      'test_facts':{'passed':17,'junit':str(OUT/'tests-final.xml'),'junit_sha256':sha(OUT/'tests-final.xml'),
        'coverage':'Native all42active/24passive/root material-point Jacobians versus finite perturbations; raw spline knots/order/signs; nativeforce-zero targets; fullvertex geometry oracle; ties/reversals/partials; gapstitching; input/flush/terminal/totalfilesystemfailure fixtures; no stepping/reset calls.',
        'independent_saved_data_check':'All560chunks/all28cases/3records/504CSVrows and partitions;2520 explicitworld-mesh checks, maximum error2.78e-17mm.'},
      'resource_facts':resources,
      'complete_cases':{'count':28,'inventory':str(OUT/'registration.json'),'scope':'historical/cadence ×42/43 ×all7 nonzero conditions; ticks6000..25000 inclusive; fixed3records'},
      'skipped_cases':[],
      'actual_new_diagnosis':[
        'Tarsus5 limits100% of dense hind samples in all3records. Neither actualhind foot reaches0.02mm anywhere in any28window. HistoricalmaxLH/RH0.002875/0.003233mm; cadencemax0.006212/0.009726mm. This survives parser ambiguity.',
        'At actualroot/passives, historicalhind command geometry intersectsfloor100%; cadence95.75–100%. Perfecttracking of those poses does not generally createclearance. TrackingRMS reaches0.113417rad; axes/conversion/sourcecommands check out.',
        'Unitreference has some headroom but poor actualAP alignment: cadencehind76/168 own-reference protractions exceed0.02mm, only17/168 pairedactual protractions, versus0/168actual. Unitwholeinterval peaks90/168 pairedactual intervals. Fixedbody intersections are counterfactual, not dynamic impossibility.',
        'All509cadence completeintervals are ambiguous;1729/1745historical ambiguous. Seed42straight0.08LH hasno completephase-bounded interval and remainsinconclusive; its full densewindow/partials/bouts are retained.',
        'Positive reconstructednormal support occurs in52.995%cadence and78.008%historical contact-free samples. Forces are instantaneous nativeforward estimates, not retainedforce observations. Every10788cadence single-sample stancezero haspositivedensemotion; denseoriginalstance maximum0.036301mm and none>=0.15mm.',
        'Stitched support envelopes show85/509cadence materialdisplacements>=0.15mm, max1.172581mm, with16unsupported and8single-support cases. All areAP-ambiguous and gapsremain; no claim of provenloadedslip or retroactivev10regrading.',
        'Root/active/passive traces and Jacobian contributions retained. Passivehind excursions reach0.439207rad. Finite-difference residualRMS max7.237887mm/s; integratedcoordinate residualmax0.028160mm. Correlation/decomposition doesnot identify a causal gain/reflex/adhesion/passive culprit.'
      ],
      'one_bounded_next_physical_question':'Can source-native excursion produce actualhind clearance>0.02mm during actualprotraction, with freelyresponding root/passive posture, while preserving originalsupport/upright/speed/turn/stop bounds? Geometricheadroom plusAP mismatch justify this question, not selection/admission of a remedy. Requires a later separatelyregistered singlephysicalcandidate; no gains/offsets/IK or newtrial chosen here.',
      'downstream':'Unchanged15gates and untouched31042/31043, repeat/activephysicalrestoration; then fullgraph40s,59s15-predicate evaluation,120smatchedWT/official/submitted+10srepeat+30sablations, originalsubjects/mirroredconditions, effect erasedbyoutputablation, existingLab/API/100Hzreplay. Broader goal remains unmet.',
      'limitations':'Totalfilesystemfailure cannot guarantee durable receipts; explicitly documented/fault-tested. Setup-only interpreter/cache details are in the newly written opaque log; numerical work uses exactrequestedvenv. No scientific algorithm changed after execution.'
    }
    envelope={'conclusion':conclusion,'log_ref':str(logpath)}
    if len(json.dumps(envelope).split())>1800:raise ValueError('envelope exceeds1800words')
    data=json_bytes(envelope)
    if len(data)>60000:raise ValueError('final receipt reservation insufficient')
    exclusive_json(CONTROL/'implementation.json',envelope)
    exclusive_json(OUT/'completion.json',{'schema':'distal-completion/v11','complete':True,'cases':28,'skipped':0,'implementation_sha256':hashlib.sha256(data).hexdigest(),
                  'evidence_index_sha256':sha(OUT/'evidence-index.json'),'final_resources_sha256':sha(OUT/'final-resources.json'),
                  'log_sha256_from_written_memory':hashlib.sha256(log.encode()).hexdigest(),'exit_code':0})
    budget.check()
    # Final marker is last; every scientific and delivery prerequisite succeeded.
    exclusive_json(CONTROL/'implementation.done',{'exit_code':0,'complete':True})
    print(json.dumps({'complete':True,'implementation':str(CONTROL/'implementation.json'),'word_count':len(json.dumps(envelope).split()),'changed_files':len(changed),'output_upper_bound_bytes':resources['final_new_output_upper_bound_bytes']}))

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        receipt={'complete':False,'type':type(exc).__name__,'message':str(exc)}
        try:exclusive_json(OUT/'finalization-failure.json',receipt)
        except BaseException:
            try:exclusive_json(SCRATCH/'finalization-failure.json',receipt)
            except BaseException:print('TOTAL FILESYSTEM FAILURE: finalization receipt unavailable',file=sys.stderr)
        raise
