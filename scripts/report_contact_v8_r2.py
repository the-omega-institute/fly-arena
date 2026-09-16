"""Derived, self-contained actual-array viewer and static scientific figure.

No new executions; raw differences are retained regardless of admission.
"""
from pathlib import Path
import json,hashlib,itertools,html
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'var/contact-v8';LEGS=['LF','LM','LH','RF','RM','RH']

def read(name):return dict(np.load(BASE/'trials'/name/'samples.npz'))
def summary(curve):
    return {'signed_mean':[float(np.trapezoid(curve[:,i],dx=.01)) for i in range(curve.shape[1])],'absolute_peak':np.max(np.abs(curve),axis=0).tolist(),'rms':np.sqrt(np.mean(curve**2,axis=0)).tolist(),'curve':curve.tolist()}
def antagonist(a):return a['pools_hz'][:,:,0]-a['pools_hz'][:,:,1]
def main():
    reg=json.loads((BASE/'registration.json').read_text());verified=json.loads((BASE/'verification.json').read_text());assert verified['integrity_pass']
    groups=dict(np.load(BASE/'inputs/groups.npz'));selected=groups.pop('selected');index={int(v):i for i,v in enumerate(selected)}
    subjects=reg['subjects'];records={};pairs={};contrasts={}
    for c in reg['conditions']:
        if c['repeat']:continue
        name=c['id'];a=read(name);u=dict(np.load(BASE/'trials'/name/'inputs.npz'))
        affidx=[[index[int(v)] for v in groups['afferent_'+l]] for l in LEGS]
        records[name]={'condition':c,'time':(a['ticks']*.0001).tolist(),'q':a['knees'].tolist(),'mn':antagonist(a).tolist(),
            'current':np.array([a['external_mv'][:,ix].mean(axis=1) for ix in affidx]).T.tolist(),
            'afferent_rates':np.array([a['rates_hz'][:,ix].mean(axis=1) for ix in affidx]).T.tolist(),
            'afferent_spikes':a['afferent_spikes'].tolist(),'motor_spikes':a['motor_spikes'].tolist(),
            'next_command':a['next_command_rad'].tolist(),'applied_command':a['applied_command_rad'].tolist(),
            'input_time':(u['input_start_tick']*.0001).tolist(),'force_time':(u['force_evaluation_tick']*.0001).tolist(),
            'contact_ratio_inputs':u['contact_ratios'].tolist(),'work':a['work_native'].tolist(),
            'samples_sha256':hashlib.sha256((BASE/'trials'/name/'samples.npz').read_bytes()).hexdigest()}
    for subject in subjects:
        role=subject['role']
        for context in (['neutral','off'] if role=='wildtype' else ['neutral']):
            for leg,state in itertools.product(['LF','RM','RF'],[42,43]):
                prefix=f'{role}-{leg}-{state}-{context}-'
                for ac,bc in [('intact','tactilezero'),('intact','motorzero'),('tactilezero','motorzero'),('intact','noprobe')]:
                    a,b=read(prefix+ac),read(prefix+bc)
                    contrasts[prefix+ac+'-minus-'+bc]={'body_rad':summary(a['knees']-b['knees']),'antagonist_hz':summary(antagonist(a)-antagonist(b))}
                own=LEGS.index(leg);metrics=verified['local'][f'{role}-{leg}-{context}']['states'][str(state)]
                base=contrasts[prefix+'intact-minus-tactilezero']
                assert base['body_rad']['signed_mean'][own]==metrics['Y_rad']
                assert abs(base['antagonist_hz']['signed_mean'][own]-metrics['N_hz'])<1e-12
    for a,b in itertools.combinations(subjects,2):
        for leg,state,control in itertools.product(['LF','RM','RF'],[42,43],['intact','tactilezero','motorzero','noprobe']):
            suffix=f'-{leg}-{state}-neutral-{control}';x,y=read(a['role']+suffix),read(b['role']+suffix)
            pairs[a['role']+'-minus-'+b['role']+suffix]={'body_rad':summary(x['knees']-y['knees']),'antagonist_hz':summary(antagonist(x)-antagonist(y)),
                'applied_command_rad':summary(x['applied_command_rad']-y['applied_command_rad'])}
    payload={'subjects':subjects,'records':records,'contrasts':contrasts,'pairwise':pairs,'verified':verified,
        'limits':'Engineered 48 mV broad nerve-group synchronous contact switch; not fitted physiology. Thorax tether, 60 non-knee constraints, neutral servos; motorzero is offset clamp. No free walking or arena qualification. Identical imposed conditions allow realized contact to differ through feedback.',
        'absent':'Official/submitted odor OFF NOT RUN. LM/LH/RH outputs observed but NOT directly probed. No free-body trials. Browser QA NOT performed.'}
    with (BASE/'derived-r2.json').open('x') as f:json.dump(payload,f,allow_nan=False)
    template=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Actual contact phenotype · v8</title>
<style>body{font:16px system-ui;margin:24px auto;max-width:1280px;padding:0 22px;color:#172534;background:#fafcff}h1{font-size:28px}p{line-height:1.5}label{display:inline-block;margin:8px 18px 8px 0}select{font:inherit;padding:5px}article{border:1px solid #ccd6e1;padding:14px;border-radius:8px;margin:10px 0;background:white}small{word-break:break-all}#plots{display:grid;grid-template-columns:1fr 1fr;gap:12px}svg{width:100%;height:auto}pre{white-space:pre-wrap;font-size:13px}table{border-collapse:collapse;font-size:13px}td,th{padding:8px;border-bottom:1px solid #ccd6e1;text-align:left}.limit{background:#fff4d8;padding:12px}button{padding:8px;font:inherit}@media(max-width:750px){#plots{grid-template-columns:1fr}}</style>
<h1>Actual WT / official / submitted contact phenotype</h1><p id="scope" class="limit"></p><p id="coverage"></p><div id="subjects"></div>
<label>Probed leg <select id="leg"><option>LF</option><option>RM</option><option>RF</option></select></label>
<label>Initial state <select id="state"><option>42</option><option>43</option></select></label>
<label>Context <select id="context"><option value="neutral">Neutral odor (.55,.55), actual A/B/C</option><option value="off">Odor OFF — WT only</option></select></label>
<label>Observed output <select id="channel"><option>LF</option><option>LM</option><option>LH</option><option>RF</option><option>RM</option><option>RH</option></select></label>
<label>Trace <select id="contrast"><option value="intact|tactilezero">Intact − tactilezero (causal)</option><option value="intact|motorzero">Intact − motorzero (mechanical)</option><option value="tactilezero|motorzero">Tactilezero − motorzero</option><option value="intact|noprobe">Intact − remote sham</option><option value="intact|">Raw intact</option><option value="tactilezero|">Raw tactilezero</option><option value="motorzero|">Raw motorzero</option><option value="noprobe|">Raw remote sham</option></select></label>
<p id="status"></p><div id="plots"></div><p>Endpoint traces: 101 frames over 1 s. Input/current read starts every 10 ms; force evaluations are explicitly recorded at tick 0 or read tick − 1. Current/spike plots use the selected contrast. A new neural command is applied in the next physical interval. Contact plots show actual input samples, without an invented final sample. State 42/43 means +/− .005 rad own-knee perturbation, not biological replicates.</p>
<h2>Registered local results (raw nulls retained)</h2><div id="metrics"></div><h2>Actual paired subject phenotypes</h2><div id="phenotypes"></div><details><summary>Verification and absent conditions</summary><pre id="verification"></pre></details><p><button id="download">Download all derived arrays and pairwise curves</button> · <a href="joint-phenotype-r2.png">Static scientific figure</a> · <a href="verification.json">Verification JSON</a> · <a href="registration.json">Frozen registration</a></p>
<script>const data=PAYLOAD;
const legs=['LF','LM','LH','RF','RM','RH'],colors=['#147568','#d48413','#7058b2'],dashes=['','9 4','2 4'];
const labels=['WT · wildtype','Nectar · official','Preview Olfactory 1.08 · submitted'];
const el=id=>document.getElementById(id),esc=s=>String(s).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
el('scope').textContent=data.limits;el('coverage').textContent='Completed 96 scientific + 3 exact repeats; all six neural/body output channels. '+data.absent;
el('subjects').innerHTML=data.subjects.map((s,i)=>`<article style="border-left:5px solid ${colors[i]}"><b>${esc(labels[i])}</b> · ${['solid','dashed','dotted'][i]} line · owner <code>${esc(s.owner)}</code><br><small>Artifact ${s.artifact_id}<br>Weights ${s.weights_sha256}<br>Subject ${s.id}</small></article>`).join('');
function draw(title,unit,series){let values=series.flatMap(s=>s.y),lo=Math.min(0,...values),hi=Math.max(0,...values);if(lo===hi){lo-=unit==='rad'?0.001:1;hi+=unit==='rad'?0.001:1}const pad=(hi-lo)*.08;lo-=pad;hi+=pad;const x=t=>58+480*t,y=v=>222-(v-lo)/(hi-lo)*180;
let svg=`<svg viewBox="0 0 580 280" role="img" aria-label="${esc(title)}"><text x="58" y="20" font-size="14" font-weight="600">${esc(title)} (${unit})</text>`;
for(let j=0;j<5;j++){let v=lo+(hi-lo)*j/4;svg+=`<path d="M58 ${y(v)}H538" stroke="#e4e9ee"/><text x="52" y="${y(v)+4}" text-anchor="end" font-size="10">${v.toPrecision(3)}</text>`}
for(let t=0;t<=1.001;t+=.2)svg+=`<text x="${x(t)}" y="244" text-anchor="middle" font-size="11">${t.toFixed(1)}</text>`;
for(const s of series){svg+=`<path d="${s.y.map((v,k)=>(k?'L':'M')+x(s.t[k]).toFixed(3)+','+y(v).toFixed(3)).join(' ')}" fill="none" stroke="${colors[s.i]}" stroke-width="2" stroke-dasharray="${dashes[s.i]}"/>`}
return '<article>'+svg+'<text x="298" y="268" text-anchor="middle" font-size="11">Time (s)</text></svg></article>'}
function render(){let l=el('leg').value,state=el('state').value,context=el('context').value,ch=legs.indexOf(el('channel').value),[ac,bc]=el('contrast').value.split('|'),active=[];
data.subjects.forEach((s,i)=>{let prefix=`${s.role}-${l}-${state}-${context}-`,a=data.records[prefix+ac],b=bc?data.records[prefix+bc]:null;if(a)active.push({a,b,i,s})});
let fields=[['q','Knee angle','rad'],['mn','Flexor − extensor pool rate','Hz'],['current','Afferent external current','mV'],['afferent_spikes','Afferent spikes per 10 ms','count'],['applied_command','Applied neural motor offset','rad'],['motor_spikes','Motor spikes per 10 ms','count']];
el('plots').innerHTML=fields.map(([key,title,unit])=>draw(title,unit,active.map(({a,b,i})=>({i,t:a.time,y:a[key].map((v,k)=>v[ch]-(b?b[key][k][ch]:0))})))).join('')+draw('Realized intact contact / body weight','ratio',active.map(({s,i})=>{const a=data.records[`${s.role}-${l}-${state}-${context}-intact`];return{i,t:a.input_time,y:a.contact_ratio_inputs.map(v=>v[ch])}}));
el('status').textContent=(context==='off'?'Official/submitted OFF NOT RUN. ':'')+(l==='RF'?'RF own-output results are shown below; cross-leg motion does not qualify RF. ':'')+'Observed '+legs[ch]+(legs[ch]!==l?' is not the directly probed leg.':'.')+' Differences are measured; numerical nonzero is not automatically a resolved phenotype.';
let rows=data.subjects.flatMap(s=>{let r=data.verified.local[`${s.role}-${l}-${context}`];return r?[`<tr><td>${esc(s.role)}</td><td>${r.local_admission?'PASS local only':'NO local admission'}</td><td>${r.states[state].Y_rad.toPrecision(7)}</td><td>${r.states[state].N_hz.toPrecision(7)}</td><td>${r.states[state].overlapping_same_direction_s.toFixed(2)}</td><td>${r.states[state].causal_pass}</td></tr>`]:[`<tr><td>${esc(s.role)}</td><td colspan="5">NOT RUN in this context</td></tr>`]});
el('metrics').innerHTML='<table><tr><th>Role</th><th>Both-state local gate</th><th>Y (rad), selected state</th><th>N (Hz)</th><th>Overlap (s)</th><th>Causal</th></tr>'+rows.join('')+'</table>';
el('phenotypes').innerHTML='<pre>'+esc(JSON.stringify(Object.fromEntries(Object.entries(data.verified.phenotypes).filter(([k])=>k.endsWith('-'+l))),null,2))+'</pre>'}
for(const id of ['leg','state','context','channel','contrast'])el(id).onchange=()=>{if(id==='leg')el('channel').value=el('leg').value;render()};
el('verification').textContent=JSON.stringify({integrity:data.verified.integrity_pass,records:data.verified.verified_records,physical_intervals:data.verified.physical_intervals.length,physical_max_error:data.verified.physical_interval_max_error,neural_intervals:data.verified.neural_intervals,repeats:data.verified.exact_repeats,limitations:data.verified.neural_replay_limit,absent:data.absent},null,2);
el('download').onclick=()=>{let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));a.download='contact-v8-derived-arrays.json';a.click();URL.revokeObjectURL(a.href)};render();
</script></html>'''
    with (BASE/'viewer-r2.html').open('x') as f:f.write(template.replace('PAYLOAD',json.dumps(payload,allow_nan=False).replace('</','<\\/')))
    styles=['-','--',':'];colors=['#147568','#d48413','#7058b2']
    fig,axes=plt.subplots(4,3,figsize=(16,13),sharex=True)
    for col,leg in enumerate(['LF','RM','RF']):
        i=LEGS.index(leg)
        for si,state in enumerate([42,43]):
            for j,s in enumerate(subjects):
                k=f"{s['role']}-{leg}-{state}-neutral-intact-minus-tactilezero";v=contrasts[k]
                axes[si,col].plot(np.arange(101)*.01,np.array(v['body_rad']['curve'])[:,i],styles[j],color=colors[j],lw=1.7,label=['WT (wildtype)','Nectar (official)','Preview 1.08 (submitted)'][j])
                axes[si+2,col].plot(np.arange(101)*.01,np.array(v['antagonist_hz']['curve'])[:,i],styles[j],color=colors[j],lw=1.7)
            axes[si,col].set_title(f'{leg} · state {state} · own knee I − T')
            axes[si+2,col].set_title(f'{leg} · state {state} · own antagonist rate I − T')
    for row in range(4):
        for col in range(3):
            ax=axes[row,col];ax.axhline(0,c='#8b949e',lw=.6);ax.grid(alpha=.18);ax.set_ylabel('rad' if row<2 else 'Hz');ax.set_xlabel('Time (s)')
            ax.axvspan(.2,.5,color='#8095a8',alpha=.10)
    axes[0,0].legend(fontsize=9,loc='best')
    rf=[verified['local'][f"{s['role']}-RF-neutral"]['local_admission'] for s in subjects]
    fig.suptitle('Contact presence 48 mV · actual neutral-context A/B/C · tethered local fixture\nMeasured intact − tactilezero traces; shaded imposed probe motion .2–.5 s',fontsize=17,y=.985)
    provenance='\n'.join(f"{['WT solid','Official dashed','Submitted dotted'][i]} · owner {s['owner']} · artifact {s['artifact_id']}" for i,s in enumerate(subjects))
    footer=f'RF local admission WT / official / submitted: {rf}. Raw nulls retained. 96 scientific + 3 exact repeats; all 6 outputs in viewer.\nOfficial/submitted odor OFF and LM/LH/RH direct probes NOT RUN. Engineered synchronous input; not physiological calibration.\nThorax tether + 60 non-knee constraints; no free walking or arena qualification. State ±.005 rad is not biological replication.\n{provenance}'
    fig.text(.035,.018,footer,fontsize=8.1,va='bottom',linespacing=1.55)
    fig.tight_layout(rect=[.02,.15,.995,.94],h_pad=2.0)
    fig.savefig(BASE/'joint-phenotype-r2.png',dpi=160);plt.close(fig)
    facts={'records_embedded':len(records),'control_contrasts':len(contrasts),'raw_pairwise_cells':len(pairs),'all6channels':True,'html_self_contained':True,
        'browser_qa':'NOT RUN; browser unavailable under task constraints','static_png_inspection':'pending external view_image inspection','source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (BASE/'report-check-r2.json').open('x') as f:json.dump(facts,f,indent=2)
    print(json.dumps(facts))
if __name__=='__main__':main()
