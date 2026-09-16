"""Descriptive cross-tabs of retained measurements; no new reconstruction."""
import json,csv,sys,traceback
from pathlib import Path
import numpy as np
from flyarena.experiments.realization_io_v11 import OUT,Budget,exclusive_json,read_dense


def main():
    budget=Budget();cases=json.loads((OUT/'all-conditions.json').read_text())['cases']
    profiles={};allcase=[]
    with (OUT/'report/paired-actual-strides.csv').open() as f:pairs=list(csv.DictReader(f))
    for c in cases:
        ident=c['case']['id'];profile=c['case']['profile'];path=OUT/'cases'/ident
        bucket=profiles.setdefault(profile,{'foot_samples':0,'contact_free_samples':0,'contact_free_positive_support_samples':0,'positive_support_samples':0,
            'qualifying_stance_bouts':0,'dense_stance_max_mm':0.,'dense_stance_at_or_above_015':0,'single_original_sample_stances':0,'single_original_dense_motion_positive':0,
            'missing_original_stances':0,'hind_pairs':{r:{'count':0,'protraction_peak_above_002':0,'whole_stride_peak_above_002':0,'mean_fraction_floor_intersection_sum':0.} for r in ['actual','command','unit_r1']}})
        dense=read_dense(path/'dense');normal=dense[:,252:282].reshape(-1,6,5).sum(axis=2)
        bouts=json.loads((path/'original-bouts.json').read_text());contact=np.zeros((19001,6),dtype=bool)
        for j,leg in enumerate(['lf','lm','lh','rf','rm','rh']):
            for b in bouts[leg]:
                contact[b['start_tick']-6000:b['end_tick_exclusive']-6000,j]=b['contact']
                if b['contact'] and b['original_qualifying']:
                    bucket['qualifying_stance_bouts']+=1;bucket['dense_stance_max_mm']=max(bucket['dense_stance_max_mm'],b['dense_displacement_mm'])
                    bucket['dense_stance_at_or_above_015']+=b['dense_displacement_mm']>=.15
                    bucket['missing_original_stances']+=b['original_sample_category']=='missing'
                    if b['original_sample_category']=='single':
                        bucket['single_original_sample_stances']+=1;bucket['single_original_dense_motion_positive']+=b['dense_displacement_mm']>0
        bucket['foot_samples']+=contact.size;bucket['contact_free_samples']+=int((~contact).sum())
        bucket['positive_support_samples']+=int((normal>0).sum());bucket['contact_free_positive_support_samples']+=int(((~contact)&(normal>0)).sum())
        for r in pairs:
            if r['case_id']==ident and r['leg'] in ['lh','rh'] and r['complete']=='True':
                target=bucket['hind_pairs'][r['record']];target['count']+=1
                target['protraction_peak_above_002']+=float(r['protraction_wholefoot_peak_mm'])>.02
                target['whole_stride_peak_above_002']+=float(r['whole_stride_peak_mm'])>.02
                target['mean_fraction_floor_intersection_sum']+=float(r['protraction_fraction_floor_intersection'])
        hind=[r for r in c['records'] if r['record']=='actual' and r['leg'] in ['lh','rh']]
        ref=[r for r in pairs if r['case_id']==ident and r['record']=='unit_r1' and r['leg'] in ['lh','rh'] and r['complete']=='True']
        allcase.append({'case':ident,'hind_actual_window_peaks_mm':[r['window']['wholefoot_peak_mm'] for r in hind],
                        'complete_actual_hind_intervals':len(ref),'unit_paired_protraction_peaks_above_002':sum(float(r['protraction_wholefoot_peak_mm'])>.02 for r in ref),
                        'legs_without_complete_actual_interval':[r['leg'] for r in c['records'] if r['record']=='actual' and not r['complete_strides']]})
        budget.check()
    for p in profiles.values():
        p['contact_free_positive_support_fraction']=p['contact_free_positive_support_samples']/p['contact_free_samples']
        for r in p['hind_pairs'].values():r['mean_protraction_floor_intersection_fraction']=r.pop('mean_fraction_floor_intersection_sum')/r['count']
    return {'schema':'retained-cross-tabs/v11','profiles':profiles,'all_cases':allcase,'method':'Cross-tabs only from sealed dense values/parsed intervals/original bouts; no new geometry, reference, controller or dynamics.'}

if __name__=='__main__':
    error=None
    try:
        result=main();exclusive_json(OUT/'cross-tabs.json',result);print(json.dumps(result,indent=2))
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)};traceback.print_exc()
    finally:
        try:exclusive_json(OUT/'cross-tabs-terminal.json',{'complete':error is None,'error':error})
        except BaseException as exc:
            error={'retention_failure':str(exc)}
            try:exclusive_json(Path('/tmp/fly-v11-realization/cross-tabs-failure.json'),error)
            except BaseException:print('TOTAL FILESYSTEM FAILURE: cross-tab receipt unavailable',file=sys.stderr)
    if error:raise SystemExit(1)
