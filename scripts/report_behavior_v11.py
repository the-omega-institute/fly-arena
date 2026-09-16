"""All-condition descriptive report/plots from sealed audit outputs only."""
import csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flyarena.experiments.realization_io_v11 import OUT,ROOT,Budget,exclusive_json,read_dense,sha
from flyarena.experiments.realization_native_v11 import LEGS,RECORDS
from flyarena.experiments.realization_v11 import view_fields


def main():
    budget=Budget();budget.check()
    terminal=json.loads((OUT/'execution-terminal.json').read_text())
    if not terminal['complete']:raise ValueError('report requires complete all28 audit')
    allcases=json.loads((OUT/'all-conditions.json').read_text());cases=allcases['cases']
    if len(cases)!=28:raise ValueError('missing condition')
    output=OUT/'report';output.mkdir(exist_ok=False)
    rows=[];paired_rows=[];envelopes=[];bout_counts={};ambiguous={};grouped={};cells={}
    for case in cases:
        ident=case['case'];p=OUT/'cases'/ident['id']
        parsed=json.loads((p/'parsed.json').read_text());pairs=json.loads((p/'paired.json').read_text());bouts=json.loads((p/'original-bouts.json').read_text())
        for r in case['records']:
            row={'case_id':ident['id'],'profile':ident['profile'],'seed':ident['seed'],'condition':ident['case'][0],**{k:v for k,v in r.items() if k!='window'}}
            row.update({k:v for k,v in r['window'].items() if not isinstance(v,list)})
            rows.append(row)
            key=(ident['profile'],r['record'],r['leg'])
            grouped.setdefault(key,[]).append(r)
        for record in RECORDS:
            for leg in LEGS:
                key=(ident['profile'],record,leg)
                ambiguous.setdefault(key,{})
                for interval in parsed[record][leg]['intervals']:
                    for flag in interval['ambiguities']:ambiguous[key][flag]=ambiguous[key].get(flag,0)+1
                cc=parsed[record][leg]['cells'];cells.setdefault(key,{'complete':0,'partial':0,'missing':0,'tied':0})
                cells[key]['complete']+=sum(c['complete'] for c in cc);cells[key]['partial']+=sum(not c['complete'] and not c['missing'] for c in cc)
                cells[key]['missing']+=sum(c['missing'] for c in cc);cells[key]['tied']+=sum(len(c.get('tie_ticks',[]))>1 for c in cc)
        for pair in pairs:
            for record,parts in pair['records'].items():
                paired_rows.append({'case_id':ident['id'],'profile':ident['profile'],'leg':pair['leg'],'record':record,
                                    'start_tick':pair['start_tick'],'end_tick':pair['end_tick_inclusive'],'complete':pair['complete'],
                                    'ambiguous':bool(pair['ambiguities']),
                                    **{'protraction_'+k:parts['protraction'][k] for k in ['wholefoot_peak_mm','wholefoot_min_mm','fraction_floor_intersection','fraction_above_002']},
                                    'whole_stride_peak_mm':parts['whole_stride']['wholefoot_peak_mm']})
        for leg in LEGS:
            for interval in parsed['actual'][leg]['intervals']:
                if interval['kind']=='stride':envelopes.append({'case_id':ident['id'],'profile':ident['profile'],'leg':leg,
                    'start_tick':interval['aep_tick'],'end_tick':interval['end_tick_inclusive'],'complete':interval['complete'],
                    'ambiguous':bool(interval['ambiguities']),**interval['support_envelope']})
            for b in bouts[leg]:
                key=(ident['profile'],'stance' if b['contact'] else 'contact_free',b['original_qualifying'],b['original_sample_category'])
                bout_counts[key]=bout_counts.get(key,0)+1
    def csvout(name,data):
        fields=list(dict.fromkeys(k for row in data for k in row))
        with (output/name).open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
    csvout('all-case-leg-records.csv',rows);csvout('paired-actual-strides.csv',paired_rows);csvout('support-envelopes.csv',envelopes)
    csvout('original-bout-inventory.csv',[{'profile':k[0],'kind':k[1],'original_qualifying':k[2],'original_sample_category':k[3],'count':v} for k,v in bout_counts.items()])
    totals=[]
    for (profile,record,leg),rs in grouped.items():
        totals.append({'profile':profile,'record':record,'leg':leg,'conditions':len(rs),'complete_strides':sum(x['complete_strides'] for x in rs),
                       'partial_strides':sum(x['partial_strides'] for x in rs),'ambiguous_complete':sum(x['ambiguous_complete_strides'] for x in rs),
                       'protraction_peaks_above_002':sum(x['complete_protraction_peak_above_002'] for x in rs),
                       'whole_stride_peaks_above_002':sum(x['complete_stride_peak_above_002'] for x in rs),
                       'minimum_stride_peak_mm':min(x['minimum_complete_stride_peak_mm'] for x in rs if x['minimum_complete_stride_peak_mm'] is not None),
                       'maximum_stride_peak_mm':max(x['maximum_complete_stride_peak_mm'] for x in rs if x['maximum_complete_stride_peak_mm'] is not None),
                       'window_floor_intersection_fraction_range':[min(x['window']['fraction_floor_intersection'] for x in rs),max(x['window']['fraction_floor_intersection'] for x in rs)],
                       'tarsus5_limiting_fraction':sum(x['window']['limiting_link_counts'][4] for x in rs)/sum(x['window']['samples'] for x in rs),
                       'cells':cells[(profile,record,leg)],'ambiguity_flags_all_intervals':ambiguous[(profile,record,leg)]})
    csvout('profile-leg-record-totals.csv',[{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in totals])
    support={}
    for profile in dict.fromkeys(c['case']['profile'] for c in cases):
        pp=[e for e in envelopes if e['profile']==profile and e['complete']]
        support[profile]={'complete_envelopes':len(pp),'ambiguous':sum(e['ambiguous'] for e in pp),
                          'unsupported':sum(e['status']=='unsupported' for e in pp),'single_sample':sum(e['status']=='single-sample-unresolved' for e in pp),
                          'displacement_at_or_above_015':sum(e['supported_displacement_mm'] is not None and e['supported_displacement_mm']>=.15 for e in pp),
                          'max_supported_displacement_mm':max(e['supported_displacement_mm'] for e in pp if e['supported_displacement_mm'] is not None),
                          'max_whole_retraction_displacement_mm':max(e['whole_envelope_displacement_mm'] for e in pp),
                          'max_gap_ticks':max(e['largest_internal_unsupported_gap_ticks'] or 0 for e in pp),
                          'support_duty_range':[min(e['positive_support_duty'] for e in pp),max(e['positive_support_duty'] for e in pp)]}
    checks={'dense_rows':sum(c['validation']['contact_rows'] for c in cases),'geometry_overlap_rows':sum(c['validation']['geometry_overlap_rows'] for c in cases),
            'old_bouts_verified':sum(c['validation']['original_qualifying_bouts_verified'] for c in cases),'all_retained_contact_runs':sum(bout_counts.values()),
            'max_source_command_error_rad':max(c['validation']['source_command_max_error_rad'] for c in cases),
            'max_force_balance_residual_native':max(c['validation']['max_force_balance_residual_native'] for c in cases)}
    realization=[]
    for c in cases:
        for leg in c['realization']['legs']:
            realization.append({'case_id':c['case']['id'],'profile':c['case']['profile'],**leg})
    summary={'schema':'distal-report-facts/v11','checks':checks,'profile_leg_record_totals':totals,'support':support,
             'paired_records':len(paired_rows),'support_envelopes_including_partial':len(envelopes),
             'tracking_rms_max_rad':max(max(x['tracking_rms_rad']) for x in realization),
             'velocity_residual_rms_max_mm_s':max(max(x['velocity_residual_rms_xyz_mm_s']) for x in realization),
             'integrated_displacement_residual_max_abs_mm':max(max(abs(y) for y in x['integrated_displacement_residual_xyz_mm']) for x in realization),
             'normal_duty_range':[min(x['normal_support_duty'] for x in realization),max(x['normal_support_duty'] for x in realization)],
             'positive_distance_normal_fraction_range':[min(x['positive_distance_normal_fraction'] for x in realization if x['positive_distance_normal_fraction'] is not None),max(x['positive_distance_normal_fraction'] for x in realization if x['positive_distance_normal_fraction'] is not None)]}
    exclusive_json(output/'facts.json',summary)
    # All cases, all legs, three fixed records. Counts/denominators include
    # ambiguous complete intervals; no favorable subset or pooled seed hiding.
    labels=[]
    for c in cases:
        i=c['case'];labels.append(('H' if i['profile']=='historical' else 'C')+str(i['seed'])+' '+i['case'][0])
    fig,axes=plt.subplots(1,3,figsize=(16,12),sharey=True,layout='constrained')
    for ax,record in zip(axes,RECORDS):
        matrix=np.empty((28,6));counts=[]
        for i,c in enumerate(cases):
            rr=[next(r for r in c['records'] if r['record']==record and r['leg']==leg) for leg in LEGS]
            matrix[i]=[r['complete_protraction_peak_above_002']/r['complete_strides'] if r['complete_strides'] else np.nan for r in rr]
            counts.append(rr)
        im=ax.imshow(matrix,vmin=0,vmax=1,cmap='cividis',aspect='auto')
        for i in range(28):
            for j in range(6):
                r=counts[i][j];ax.text(j,i,f"{r['complete_protraction_peak_above_002']}/{r['complete_strides']}",ha='center',va='center',fontsize=6.5,color='white' if matrix[i,j]<.5 else 'black')
        ax.set_xticks(range(6),[l.upper() for l in LEGS]);ax.set_title(record.replace('_',' '));ax.set_yticks(range(28),labels,fontsize=8)
        for y in [6.5,13.5,20.5]:ax.axhline(y,color='white',lw=1)
    fig.colorbar(im,ax=axes,label='Fraction of complete diagnostic protractions with peak whole-foot clearance >0.02 mm',shrink=.6)
    fig.suptitle('Every retained condition · dense 0.1 ms geometry · complete intervals include ambiguity\nH: historical; C: cadence v10. References hold actual root and passive joints fixed; no gait qualification.',fontsize=13)
    fig.savefig(output/'all-conditions.png',dpi=180);plt.close(fig)
    # Fixed representative specified by the original motivating condition,
    # all six legs and the full registered window, no clearance-selected slice.
    ident='cadence-normalized-hybrid-v10--42--straight-02';dense=view_fields(read_dense(OUT/'cases'/ident/'dense'))
    t=np.arange(6000,25001)*.0001
    fig,axes=plt.subplots(6,2,figsize=(16,15),sharex=True,layout='constrained')
    colors=['#151515','#ca6526','#1675ae']
    for leg,name in enumerate(LEGS):
        ax=axes[leg,0]
        for r,record in enumerate(RECORDS):ax.plot(t,dense['link_clearance'][:,r,leg].min(axis=1),color=colors[r],lw=.75,label=record)
        ax.axhline(.02,color='#9c388e',lw=.7,ls='--');ax.axhline(0,color='gray',lw=.6);ax.set_ylabel(name.upper()+' clearance (mm)');ax.grid(alpha=.2)
        ap=dense['centroid_thorax'][:,0,leg,0];support=dense['normal_per_link'][:,leg].sum(axis=1)>0
        axes[leg,1].plot(t,ap,color='#151515',lw=.8,label='actual thorax AP')
        axes[leg,1].fill_between(t,ap.min(),ap.max(),where=support,color='#289d83',alpha=.18,label='positive reconstructed normal support')
        axes[leg,1].set_ylabel(name.upper()+' thorax AP (mm)');axes[leg,1].grid(alpha=.2)
    axes[0,0].legend(ncol=3,fontsize=8,loc='upper right');axes[0,1].legend(fontsize=8,loc='upper right')
    axes[-1,0].set_xlabel('Recorded time (s)');axes[-1,1].set_xlabel('Recorded time (s)')
    fig.suptitle('Cadence v10 · seed42 · straight0.2 · complete registered window\nCounterfactual floor intersections use frozen actual body/passive posture; dynamic body adjustment remains unknown.',fontsize=13)
    fig.savefig(output/'representative-all-legs.png',dpi=170);plt.close(fig)
    exclusive_json(output/'manifest.json',{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file()})
    budget.check();print(json.dumps(summary,indent=2))

if __name__=='__main__':
    import sys,traceback
    error=None
    try:main()
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        traceback.print_exc()
    finally:
        receipt={'schema':'distal-report-terminal/v11','complete':error is None,'error':error}
        try:exclusive_json(OUT/'report-terminal.json',receipt)
        except BaseException as exc:
            receipt['complete']=False;receipt['retention_error']=str(exc)
            try:exclusive_json(Path('/tmp/fly-v11-realization/report-failure.json'),receipt)
            except BaseException:print('TOTAL FILESYSTEM FAILURE: report receipt unavailable',file=sys.stderr)
            error=receipt
    if error:raise SystemExit(1)
