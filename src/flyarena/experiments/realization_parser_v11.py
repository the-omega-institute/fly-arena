"""Registered AP parser; ambiguity is data, not an exclusion criterion."""
from __future__ import annotations
import numpy as np
TIE=1e-12
TAU=2*np.pi

def extrema(y,maximum=False):
    value=float(np.max(y) if maximum else np.min(y))
    indices=np.flatnonzero(np.abs(y-value)<=TIE)
    return int(indices[0]),indices.tolist(),value

def reversal_ticks(y,start=0):
    delta=np.diff(y);nz=np.flatnonzero(np.abs(delta)>TIE)
    if len(nz)<2:return []
    return (nz[1:][np.sign(delta[nz[1:]])!=np.sign(delta[nz[:-1]])]+start+1).tolist()

def parse_ap(phases,ap,tick0=6000):
    phases=np.asarray(phases);ap=np.asarray(ap)
    if phases.shape!=ap.shape or phases.ndim!=1 or len(ap)<2 or not np.isfinite(phases).all() or not np.isfinite(ap).all():raise ValueError('bad AP/phase record')
    if not np.all(np.diff(phases)>0):raise ValueError('phase is not strictly increasing')
    bins=np.floor(phases/TAU).astype(np.int64);cells=[]
    for k in range(int(bins[0]),int(bins[-1])+1):
        ii=np.flatnonzero(bins==k)
        if not len(ii):
            cells.append({'cell':k,'complete':False,'missing':True,'pep_index':None,'ambiguities':['missing-cell']});continue
        lo,hi=int(ii[0]),int(ii[-1]);a,ties,value=extrema(ap[lo:hi+1]);pep=lo+a
        complete=(lo>0 or phases[0]==k*TAU) and hi<len(ap)-1 and bins[hi+1]==k+1
        cells.append({'cell':k,'complete':bool(complete),'missing':False,'start_tick':lo+tick0,'end_tick_inclusive':hi+tick0,
                      'pep_index':pep,'pep_tick':pep+tick0,'pep_ap_mm':value,'tie_ticks':[lo+t+tick0 for t in ties],
                      'reversal_ticks':reversal_ticks(ap[lo:hi+1],lo+tick0),'ambiguities':['tied-PEP'] if len(ties)>1 else []})
    intervals=[]
    present=[c for c in cells if c['pep_index'] is not None]
    for a,b in zip(present[:-1],present[1:]):
        lo,hi=a['pep_index'],b['pep_index'];peak,ties,val=extrema(ap[lo:hi+1],True);aep=lo+peak
        flags=a['ambiguities']+b['ambiguities']
        reversals=reversal_ticks(ap[lo:hi+1],lo+tick0)
        if len(ties)>1:flags+=['tied-AEP']
        if aep in (lo,hi):flags+=['boundary-AEP']
        if np.ptp(ap[lo:hi+1])<=TIE:flags+=['degenerate-AP']
        if len(reversals)>1:flags+=['additional-reversals']
        if np.any(np.diff(ap[lo:aep+1]) < -TIE):flags+=['negative-protraction']
        if np.any(np.diff(ap[aep:hi+1]) > TIE):flags+=['positive-retraction']
        if b['cell']!=a['cell']+1:flags+=['missing-cell']
        intervals.append({'kind':'stride','start_tick':lo+tick0,'aep_tick':aep+tick0,'end_tick_inclusive':hi+tick0,
                          'complete':bool(a['complete'] and b['complete'] and b['cell']==a['cell']+1),
                          'cells':[a['cell'],b['cell']],'aep_ap_mm':val,'aep_tie_ticks':[lo+t+tick0 for t in ties],
                          'reversal_ticks':reversals,'ambiguities':sorted(set(flags))})
    if present:
        first,last=present[0]['pep_index'],present[-1]['pep_index']
        intervals.insert(0,{'kind':'prefix','start_tick':tick0,'end_tick_inclusive':first+tick0,'complete':False,'ambiguities':['unbounded']})
        intervals.append({'kind':'suffix','start_tick':last+tick0,'end_tick_inclusive':len(ap)-1+tick0,'complete':False,'ambiguities':['unbounded']})
    return {'cells':cells,'intervals':intervals}

def contact_runs(contact,phase,tick0=6000):
    c=np.asarray(contact,dtype=bool);p=np.asarray(phase)
    bounds=np.r_[0,np.flatnonzero(c[1:]!=c[:-1])+1,len(c)]
    runs=[]
    for lo,hi in zip(bounds[:-1],bounds[1:]):
        lo,hi=int(lo),int(hi);bounded=lo>0 and hi<len(c)
        runs.append({'start_tick':lo+tick0,'end_tick_exclusive':hi+tick0,'contact':bool(c[lo]),
                     'bounded':bounded,'original_qualifying':bool(bounded and p[hi-1]>p[lo]),
                     'phase_advance':float(p[hi-1]-p[lo]),'dense_samples':hi-lo})
    return runs

def max_displacement(points):
    if not len(points):return None
    return float(np.linalg.norm(points-points[0],axis=1).max())

def support_envelope(points,support,contact):
    points=np.asarray(points);s=np.asarray(support)>0;ii=np.flatnonzero(s)
    result={'samples':len(points),'positive_support_samples':len(ii),'positive_support_duty':float(s.mean()),
            'contact_duty':float(np.mean(contact)),'whole_envelope_displacement_mm':max_displacement(points),
            'supported_displacement_mm':None,'supported_net_chord_mm':None,'supported_path_mm':None,
            'largest_internal_unsupported_gap_ticks':None,'status':'unsupported' if not len(ii) else 'single-sample-unresolved' if len(ii)==1 else 'multiple'}
    if len(ii):
        lo,hi=int(ii[0]),int(ii[-1]);p=points[lo:hi+1];gaps=~s[lo:hi+1]
        changes=np.r_[0,np.flatnonzero(gaps[1:]!=gaps[:-1])+1,len(gaps)]
        longest=max([int(b-a) for a,b in zip(changes[:-1],changes[1:]) if gaps[a]] or [0])
        result.update({'first_supported_offset':lo,'last_supported_offset':hi,'supported_displacement_mm':max_displacement(p),
                       'supported_net_chord_mm':float(np.linalg.norm(p[-1]-p[0])),
                       'supported_path_mm':float(np.linalg.norm(np.diff(p,axis=0),axis=1).sum()),
                       'largest_internal_unsupported_gap_ticks':longest})
    return result
