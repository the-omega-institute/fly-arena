"""Supplementary paired tactile-response curves, derived only from saved records.

Post-freeze reporting addition, separately source-bound; no scientific execution.
"""
from pathlib import Path
import itertools,json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'var/contact-v8'
LEGS=['LF','LM','LH','RF','RM','RH']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ant(a):return a['pools_hz'][:,:,0]-a['pools_hz'][:,:,1]
def means(a):return np.array([np.trapezoid(a[:,i],dx=.01) for i in range(6)])
def main():
    reg=json.loads((BASE/'registration.json').read_text());v=json.loads((BASE/'verification.json').read_text());assert v['integrity_pass']
    records={};sources={};max_error=0.
    for sa,sb in itertools.combinations(reg['subjects'],2):
        for leg,state in itertools.product(['LF','RM','RF'],[42,43]):
            responses=[]
            for subject in [sa,sb]:
                prefix=f"{subject['role']}-{leg}-{state}-neutral-";p=BASE/'trials'/(prefix+'intact')/'samples.npz';q=BASE/'trials'/(prefix+'tactilezero')/'samples.npz'
                a=np.load(p);b=np.load(q);sources[str(p)]=sha(p);sources[str(q)]=sha(q)
                responses.append((a['knees']-b['knees'],ant(a)-ant(b)))
            d=responses[0][0]-responses[1][0];n=responses[0][1]-responses[1][1]
            dy=means(responses[0][0])-means(responses[1][0]);dn=means(responses[0][1])-means(responses[1][1])
            key=f"{sa['role']}-minus-{sb['role']}-{leg}";i=LEGS.index(leg);j=0 if state==42 else 1
            assert dy[i]==v['phenotypes'][key]['deltaY_rad_states42_43'][j]
            assert dn[i]==v['phenotypes'][key]['deltaN_hz_states42_43'][j]
            error=float(max(np.max(np.abs(means(d)-dy)),np.max(np.abs(means(n)-dn))));max_error=max(max_error,error)
            records[key+'-'+str(state)]={'state':state,'probed_leg':leg,'all_output_legs':LEGS,'deltaD_rad':d.tolist(),'delta_neural_trace_hz':n.tolist(),
                'deltaY_rad':dy.tolist(),'deltaN_hz':dn.tolist(),'mean_of_deltaD_rad':means(d).tolist(),'mean_of_delta_neural_trace_hz':means(n).tolist(),
                'signed_mean_roundoff_difference':error,'subject_A':sa['artifact_id'],'subject_B':sb['artifact_id']}
    out={'source_sha256':sha(Path(__file__)),'registration_sha256':sha(BASE/'registration.json'),'verification_sha256':sha(BASE/'verification.json'),
        'source_records':sources,'times_s':(np.arange(101)*.01).tolist(),'records':records,'all_own_paired_means_exactly_match_verified_metrics':True,
        'max_mean_order_roundoff':max_error,'note':'deltaY/deltaN are differences of registered full-trial means. Integrating the difference traces is also reported; tiny reduction-order roundoff is explicit. No thresholds or outcomes are changed.'}
    with (BASE/'paired-tactile-differences.json').open('x') as f:json.dump(out,f,allow_nan=False)
    print(json.dumps({'paired_leg_state_records':len(records),'all6outputs':True,'max_mean_order_roundoff':max_error}))
if __name__=='__main__':main()
