"""Actual-time realized events and unchanged physical criteria, pure fixtures allowed."""
import numpy as np
from .schema import DT,TOL,MODES
LO,HI=6000,25000
SWING={'LIFT','TRANSFER','LAND'}
SUPPORT={'SUPPORT','RELEASE_WAIT','REACQUIRE'}
def longest(values):
    best=current=0
    for value in values:
        current=current+1 if value else 0;best=max(best,current)
    return best

def realized_partition(phi,modes,cycles,resume,beta,wait,lag,*,lo=LO,hi=HI,active=True,admitted=None,distal_count=None,load_count=None):
    """Holds retain their physical ticks; cycle/mode validation precedes partition."""
    phi=np.asarray(phi);modes=np.asarray(modes);cycles=np.asarray(cycles)
    if phi.shape!=modes.shape or phi.shape!=cycles.shape or phi.ndim!=2 or phi.shape[1]!=6 or len(phi)<=hi:raise ValueError('realized grid')
    result=[]
    for leg in range(6):
        flags=[];faults=[]
        for k in range(lo,hi+1):
            mode=MODES[int(modes[k,leg])];old=MODES[int(modes[k-1,leg])] if k else mode
            p=phi[k,leg]-cycles[k,leg]*2*np.pi;b=beta[leg]
            check=MODES[int(resume[k,leg])] if mode=='REACQUIRE' else mode
            intervals={'LIFT':(0,b/3),'TRANSFER':(b/3,2*b/3),'LAND':(2*b/3,b),'SUPPORT':(b,2*np.pi),'RELEASE_WAIT':(2*np.pi,2*np.pi)}
            invalid=check not in intervals
            if not invalid:
                low,high=intervals[check];invalid=not low-TOL<=p<=high+TOL
            if active and k>lo:
                delta=phi[k,leg]-phi[k-1,leg];cycle_delta=cycles[k,leg]-cycles[k-1,leg]
                legal_change=(old,mode) in {('LIFT','TRANSFER'),('TRANSFER','LAND'),('LAND','SUPPORT'),('SUPPORT','RELEASE_WAIT'),('RELEASE_WAIT','LIFT'),('SUPPORT','LIFT'),('SUPPORT','REACQUIRE'),('RELEASE_WAIT','REACQUIRE'),('REACQUIRE','SUPPORT'),('REACQUIRE','RELEASE_WAIT')}
                if old=='REACQUIRE' and mode=='LIFT':
                    old_phase=phi[k-1,leg]-cycles[k-1,leg]*2*np.pi
                    legal_change=(MODES[int(resume[k-1,leg])]=='RELEASE_WAIT' and cycle_delta==1
                      and abs(old_phase-2*np.pi)<=TOL and abs(p)<=TOL and abs(delta)<=TOL
                      and admitted is not None and distal_count is not None and load_count is not None
                      and admitted[k,leg]==1 and distal_count[k-1,leg]==29 and distal_count[k,leg]==0
                      and load_count[k,leg]==30 and wait[k,leg]==0)
                invalid|=delta< -TOL or cycle_delta not in (0,1) or (cycle_delta==1 and mode!='LIFT') or (old!=mode and not legal_change)
                if delta==0 and old==mode:
                    boundary={'LIFT':b/3,'TRANSFER':2*b/3,'LAND':b,'SUPPORT':2*np.pi,'RELEASE_WAIT':2*np.pi}.get(mode)
                    invalid|=mode!='REACQUIRE' and abs(p-boundary)>TOL
                invalid|=wait[k,leg]>500 or not -TOL<=lag[k,leg]<=np.pi/2
            if invalid and active:faults.append(k)
            flags.append(mode in SWING)
        groups={'swing':[],'stance':[],'partials':[],'invalid_ticks':faults}
        begin=lo
        for end in range(lo+1,hi+2):
            if end<=hi and flags[end-lo]==flags[begin-lo] and cycles[end,leg]==cycles[begin,leg]:continue
            kind='swing' if flags[begin-lo] else 'stance'
            record={'kind':kind,'start_tick':begin,'end_tick_exclusive':end,'cycle':int(cycles[begin,leg])}
            if begin==lo or end==hi+1:groups['partials'].append(record)
            else:groups[kind].append((begin,end))
            begin=end
        result.append(groups)
    return result

def physical_runs(partitions,ap,height,normal,weighted,peak):
    swings=[];stances=[];ok_swing=True;ok_stance=True
    for leg,p in enumerate(partitions):
        sr=[];tr=[]
        for start,end in p['swing']:
            raw=ap[start:end,leg]; filtered=np.median(np.lib.stride_tricks.sliding_window_view(raw,31),axis=1) if len(raw)>=31 else np.empty(0)
            rec={'start_tick':start,'end_tick_exclusive':end,'status':'inconclusive','reason':'no full median window'}
            if len(filtered):
                low=float(filtered.min());high=float(filtered.max());i=int(np.flatnonzero(filtered==low)[0]);later=np.flatnonzero((filtered==high)&(np.arange(len(filtered))>i))
                differences=np.diff(filtered);sign=np.sign(differences[differences!=0])
                rec.update(filtered_min_mm=low,filtered_max_mm=high,min_ties=int(np.count_nonzero(filtered==low)),max_ties=int(np.count_nonzero(filtered==high)),flat_differences=int(np.count_nonzero(differences==0)),reversals=int(np.count_nonzero(sign[1:]!=sign[:-1])))
                if len(later):
                    pep=start+15+i;aep=start+15+int(later[0]);dwell=longest((height[pep:aep+1,leg]>.02)&(normal[pep:aep+1,leg]==0))
                    passed=aep>pep and high-low>.02 and dwell>=30
                    rec.update(status='pass' if passed else 'fail',reason=None,pep_tick=pep,aep_tick=aep,excursion_mm=high-low,recovery_dwell_ticks=dwell,duration_s=(aep-pep)*DT)
                else:rec['reason']='global maximum not later than earliest global minimum'
            sr.append(rec)
        for start,end in p['stance']:
            load=normal[start:end,leg]>0; dwell=longest(load)
            slip=float(DT*np.divide(weighted[start:end,leg],normal[start:end,leg],out=np.zeros(end-start),where=load).sum())
            tr.append({'start_tick':start,'end_tick_exclusive':end,'status':'pass' if dwell>=30 and slip<.15 else 'fail','support_dwell_ticks':dwell,'slip_mm':slip,'loaded_intervals':int(load.sum()),'peak_pre_state_contact_tangent_speed_mm_s':float(peak[start:end,leg].max(initial=0))})
        ok_swing&=bool(sr) and all(r['status']=='pass' for r in sr)
        ok_stance&=bool(tr) and all(r['status']=='pass' for r in tr)
        swings.append(sr);stances.append(tr)
    return {'swing_cycles':swings,'stance_cycles':stances,'phase_partitions':partitions,'recovery_passed':bool(ok_swing),'support_slip_passed':bool(ok_stance),'phase_valid':not any(p['invalid_ticks'] for p in partitions),'invalid_interior_phase_episodes':sum(len(p['invalid_ticks']) for p in partitions)}

def independent_realized_gate(phi,modes,cycles,ap,height,normal,weighted,*,lo=LO,hi=HI):
    """Second segmentation and scalar median/quadrature implementation."""
    passed=[True,True];counts=[0,0]
    for leg in range(6):
        kinds=np.isin(modes[:,leg],[MODES.index(m) for m in SWING])
        for kind in (True,False):
            runs=[];start=None
            for t in range(lo,hi+2):
                on=t<=hi and bool(kinds[t])==kind
                if start is not None and (not on or cycles[t,leg]!=cycles[start,leg]):runs.append((start,t));start=None
                if on and start is None:start=t
            complete=[(a,b) for a,b in runs if a>lo and b<=hi]
            index=0 if kind else 1;passed[index]&=bool(complete);counts[index]+=len(complete)
            for a,b in complete:
                if kind:
                    med=[sorted(float(x) for x in ap[t-15:t+16,leg])[15] for t in range(a+15,b-15)]
                    if not med:passed[0]=False;continue
                    lower=min(med);upper=max(med);i=med.index(lower);later=[j for j,x in enumerate(med) if j>i and x==upper]
                    if not later:passed[0]=False;continue
                    pep=a+15+i;aep=a+15+later[0];run=best=0
                    for t in range(pep,aep+1):run=run+1 if height[t,leg]>.02 and normal[t,leg]==0 else 0;best=max(best,run)
                    passed[0]&=upper-lower>.02 and aep>pep and best>=30
                else:
                    run=best=0;slip=0.
                    for t in range(a,b):
                        loaded=normal[t,leg]>0;run=run+1 if loaded else 0;best=max(best,run)
                        if loaded:slip+=float(weighted[t,leg]/normal[t,leg])*DT
                    passed[1]&=best>=30 and slip<.15
    return bool(passed[0]),bool(passed[1]),counts

def pose_gates(position,rotation,case):
    if len(position)!=40001:raise ValueError('full pose gate requires complete trial')
    velocity=np.diff(position,axis=0)/DT;yaw=np.unwrap(np.arctan2(rotation[:,1,0],rotation[:,0,0]));_,common,asym=case
    forward=float(np.mean(np.sum(velocity[6000:25000]*rotation[6000:25000,:,0],axis=1)))
    stop_speed=float(np.linalg.norm(velocity[30000:40000],axis=1).mean());stop_distance=float(np.linalg.norm(position[40000]-position[30000]));yawrate=float((yaw[25000]-yaw[6000])/1.9);turn=float(yaw[25000]-yaw[3000])
    gates={'finite':bool(np.isfinite(position).all() and np.isfinite(rotation).all()),'upright':bool(rotation[:,2,2].min()>.8),'stop':stop_distance<.25 and stop_speed<.1}
    if common:gates['turn' if asym else 'straight_yaw']=bool(np.sign(turn)==np.sign(asym) and abs(turn)>.1) if asym else abs(yawrate)<.15
    return gates,{'forward_mean_mm_s':forward,'stop_mean_speed_mm_s':stop_speed,'stop_displacement_mm':stop_distance,'mean_yaw_rate_rad_s':yawrate,'net_active_yaw_rad':turn}
