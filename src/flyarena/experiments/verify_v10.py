"""Independent v10 gate reconstruction from raw numeric geometry/control/contact.

No producer metrics or summary decisions are admission inputs. This module has no
controller stepping and cannot run an experiment or admit the production bridge.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import mujoco as mj
from ..common import file_sha, write_json
from .cadence_v10 import PROFILE


def read_stream(path,rows,width,stride):
    terminal=json.loads((path/'terminal.json').read_text())
    if not terminal['complete'] or terminal['primary_failure'] is not None or terminal['retention_failures']:
        raise ValueError(f'incomplete scientific stream: {path}')
    if terminal['initialized_rows']!=rows:
        raise ValueError('wrong scientific horizon')
    chunks=sorted(path.glob('chunk-*.npz'))
    expected={p.name for p in chunks}
    if expected != {n for n in terminal['files'] if n.startswith('chunk-')}:
        raise ValueError('chunk manifest mismatch')
    ticks=[];values=[]
    for index,p in enumerate(chunks):
        if p.name!=f'chunk-{index:05d}.npz' or file_sha(p)!=terminal['files'][p.name]:
            raise ValueError('chunk order/hash mismatch')
        with np.load(p,allow_pickle=False) as a:
            if set(a.files)!={'ticks','values'} or a['ticks'].dtype!=np.dtype('int64') or a['values'].dtype!=np.dtype('float64'):
                raise ValueError('invalid scientific archive schema')
            t=a['ticks'];v=a['values']
            if t.ndim!=1 or v.shape!=(len(t),width) or not np.isfinite(v).all():
                raise ValueError('invalid scientific shape/nonfinite data')
            ticks.append(t);values.append(v)
    t=np.concatenate(ticks);v=np.concatenate(values)
    if not np.array_equal(t,np.arange(rows,dtype=np.int64)*stride):
        raise ValueError('missing/duplicate/fractional ticks')
    return t,v


def fields(schema):
    offset=0; out={}
    for name,n in schema:out[name]=slice(offset,offset+n);offset+=n
    return out


def complete_runs(contact,phase,desired,lo=6000,hi=25000):
    # End is exclusive; both bounding opposite-state samples must be in window.
    inside=contact[lo:hi+1].astype(bool)
    switches=np.flatnonzero(inside[1:]!=inside[:-1])+lo+1
    result=[]
    for start,end in zip(switches[:-1],switches[1:]):
        if bool(contact[start])==desired and phase[end-1]>phase[start]:
            result.append((int(start),int(end)))
    return result


def reconstruct_trial(root,trial,reg):
    dt=reg['dt'];s=fields(reg['core_schema'])
    t,x=read_stream(trial/'core',40001,sum(n for _,n in reg['core_schema']),1)
    gt,g=read_stream(trial/'geometry',4001,360,10)
    meta=json.loads((trial/'core/start.json').read_text())
    if meta!=json.loads((trial/'geometry/start.json').read_text()):raise ValueError('stream conditions differ')
    if meta['registration_sha256']!=file_sha(root/'registration.json') or meta['sources_sha256']!=reg['sources_sha256']:
        raise ValueError('wrong immutable stage identity')
    name,c,a=meta['case']
    expected=np.zeros((40001,2));expected[3001:25001]=[c*(1-a),c*(1+a)]
    if not np.array_equal(x[:,s['input']],expected):raise ValueError('wrong waveform')
    contacts=x[:,s['foot_contact']]
    if not np.isin(contacts,[0.,1.]).all():raise ValueError('invalid contact state')
    pos=x[:,s['thorax_position']];rot=x[:,s['thorax_rotation']].reshape(-1,3,3)
    gp=g[:,:90].reshape(-1,30,3);gr=g[:,90:].reshape(-1,30,3,3)
    model=mj.MjModel.from_binary_path(str(root/'model.mjb'));data=mj.MjData(model)
    foot=np.array(reg['measurement']['foot_geom_ids']);thorax=mj.mj_name2id(model,mj.mjtObj.mjOBJ_BODY,'fly-0/c_thorax')
    # Geometry and thorax frames are independently reconstructed from native
    # qpos on every geometry sample. Never infer a limb axis from a display label.
    for i,tick in enumerate(gt):
        data.qpos[:]=x[tick,s['qpos']];mj.mj_kinematics(model,data)
        if not (np.array_equal(data.geom_xpos[foot],gp[i]) and np.array_equal(data.geom_xmat[foot].reshape(30,3,3),gr[i]) and
                np.array_equal(data.xpos[thorax],pos[tick]) and np.array_equal(data.xmat[thorax].reshape(3,3),rot[tick])):
            raise ValueError(f'geometry/physical qpos disagreement at {tick}')
    clearance=np.full((len(gt),6),np.inf);foot_world=np.empty((len(gt),6,3))
    for j,gid in enumerate(foot):
        mesh=int(model.geom_dataid[gid]);start=int(model.mesh_vertadr[mesh]);n=int(model.mesh_vertnum[mesh])
        vertices=np.asarray(model.mesh_vert[start:start+n],dtype=float)
        # Lowest support of the actual compiled collision mesh in world z.
        low=(gr[:,j,2,:]@vertices.T).min(axis=1)+gp[:,j,2]
        clearance[:,j//5]=np.minimum(clearance[:,j//5],low)
        if j%5==4:foot_world[:,j//5]=np.einsum('nij,j->ni',gr[:,j],vertices.mean(axis=0))+gp[:,j]
    body_foot=np.einsum('nji,nlj->nli',rot[gt],foot_world-pos[gt,None,:])
    yaw=np.unwrap(np.arctan2(rot[:,1,0],rot[:,0,0]))
    velocity=np.diff(pos,axis=0)/dt
    forward=(velocity[6000:25000]*rot[6000:25000,:,0]).sum(axis=1)
    stop_speed=float(np.linalg.norm(velocity[30000:40000],axis=1).mean())
    stop_displacement=float(np.linalg.norm(pos[40000]-pos[30000]))
    phases=x[:,s['phases']]; swing=[];stance=[];swing_ok=True;stance_ok=True
    for leg in range(6):
        sw=[];st=[]
        for begin,end in complete_runs(contacts[:,leg],phases[:,leg],False):
            mask=(gt>=begin)&(gt<end)
            peak=float(clearance[mask,leg].max()) if mask.any() else None
            sw.append({'start_tick':begin,'end_tick_exclusive':end,'peak_lowest_clearance_mm':peak})
        for begin,end in complete_runs(contacts[:,leg],phases[:,leg],True):
            mask=(gt>=begin)&(gt<end)
            positions=foot_world[mask,leg]
            displacement=float(np.linalg.norm(positions-positions[0],axis=1).max()) if len(positions) else None
            st.append({'start_tick':begin,'end_tick_exclusive':end,'max_foot_displacement_mm':displacement})
        swing_ok &= bool(sw) and all(v['peak_lowest_clearance_mm'] is not None and v['peak_lowest_clearance_mm']>.02 for v in sw)
        stance_ok &= bool(st) and all(v['max_foot_displacement_mm'] is not None and v['max_foot_displacement_mm']<.15 for v in st)
        swing.append(sw);stance.append(st)
    minimum_upright=float(rot[:,2,2].min())
    net_yaw=float(yaw[25000]-yaw[3000]);yaw_rate=float((yaw[25000]-yaw[6000])/1.9)
    controls=x[:,s['ctrl']];force=x[:,s['actuator_force']]
    position_acts=np.flatnonzero(model.actuator_trntype==int(mj.mjtTrn.mjTRN_JOINT))
    adhesion_acts=np.flatnonzero(model.actuator_trntype==int(mj.mjtTrn.mjTRN_BODY))
    if len(position_acts)!=42 or len(adhesion_acts)!=6:raise ValueError('wrong native transmissions')
    if not np.isin(controls[:,adhesion_acts],[0.,1.]).all():raise ValueError('invalid adhesion command')
    bound=model.actuator_forcerange[position_acts,1]
    saturation=(np.abs(force[:,position_acts])>=bound-1e-9)
    gate={'finite':True,'upright':minimum_upright>.8,'stop':stop_displacement<.25 and stop_speed<.1}
    if c>0:
        gate['swing']=bool(swing_ok);gate['stance']=bool(stance_ok)
        if a!=0:gate['turn']=bool(np.sign(net_yaw)==np.sign(a) and abs(net_yaw)>.1)
        else:gate['straight_yaw']=abs(yaw_rate)<.15
    if meta['profile']==PROFILE:
        # Entire emitted command and mutable numerical state hold in both silence windows.
        statecols=np.r_[np.arange(s['ctrl'].start,s['ctrl'].stop),np.arange(s['phases'].start,s['net_correction'].stop)]
        for start,end in [(1,3001),(25001,40001)]:
            if not np.all(x[start:end,statecols]==x[start-1,statecols]):
                raise ValueError('v10 silent state/control drift')
    return {'conditions':meta,'gates':gate,'forward_mean_mm_s':float(forward.mean()),
      'mean_yaw_rate_rad_s':yaw_rate,'net_active_yaw_rad':net_yaw,'min_upright_z':minimum_upright,
      'stop_displacement_mm':stop_displacement,'stop_mean_speed_mm_s':stop_speed,
      'swing_cycles':swing,'stance_cycles':stance,'position_force_saturation_fraction':float(saturation.mean()),
      'max_native_position_force':float(np.abs(force[:,position_acts]).max()),
      'foot_body_ap_range_mm':np.ptp(body_foot[:,:,0],axis=0).tolist(),
      'core_terminal_sha256':file_sha(trial/'core/terminal.json'),'geometry_terminal_sha256':file_sha(trial/'geometry/terminal.json')}


def verify_panel(root,stage):
    reg=json.loads((root/'registration.json').read_text())
    if file_sha(root/'model.mjb')!=reg['model_sha256']:raise ValueError('changed compiled model')
    if file_sha(root/'sources.json')!=reg['sources_sha256']:raise ValueError('changed source manifest')
    for name,e in json.loads((root/'sources.json').read_text()).items():
        if file_sha(root/e['archive'])!=e['sha256'] or file_sha(Path(name))!=e['sha256']:
            raise ValueError(f'changed stage source: {name}')
    seeds=reg['development_seeds'] if stage=='development' else reg['evaluation_seeds']
    expected={f'{profile}--{seed}--{case[0]}':(profile,seed,case)
         for profile in reg['profiles'] for seed in seeds for case in reg['cases']}
    if {p.name for p in (root/stage).iterdir()}!=set(expected):raise ValueError('incomplete/extra mechanical panel')
    metrics={}
    for name,(profile,seed,case) in expected.items():
        result=reconstruct_trial(root,root/stage/name,reg)
        meta=result['conditions']
        if (meta['profile'],meta['seed'],meta['case'],meta['stage'])!=(profile,seed,case,stage):
            raise ValueError('condition identity mismatch')
        metrics[name]=result
    aggregate={}
    for seed in seeds:
        speed=[metrics[f'{PROFILE}--{seed}--{case}']['forward_mean_mm_s'] for case in ['straight-008','straight-02','straight-04']]
        aggregate[f'speed-{seed}']=bool(speed[0]>.2 and all(b-a>.2 for a,b in zip(speed,speed[1:])))
    restoration=json.loads((root/'restoration/result.json').read_text())
    with np.load(root/'restoration/continuations.npz',allow_pickle=False) as ar:
        restored=all(np.array_equal(ar[f'{kind}_a'],ar[f'{kind}_b']) for kind in ['core','geometry','physical'])
    aggregate['restoration']=restored and restoration['passed'] is True
    if stage=='evaluation':
        original=root/stage/f'{PROFILE}--31042--straight-02'
        repeat=root/'repeat'/f'{PROFILE}--31042--straight-02'
        reconstruct_trial(root,repeat,reg)
        equal=True
        for stream,rows,width,stride in [('core',40001,sum(n for _,n in reg['core_schema']),1),('geometry',4001,360,10)]:
            a=read_stream(original/stream,rows,width,stride);b=read_stream(repeat/stream,rows,width,stride)
            equal &= all(np.array_equal(i,j) for i,j in zip(a,b))
        aggregate['repeat']=bool(equal)
    candidate=[v for v in metrics.values() if v['conditions']['profile']==PROFILE]
    passed=all(aggregate.values()) and all(all(v['gates'].values()) for v in candidate)
    return {'schema':'independent-mechanical-decision/v10','stage':stage,'candidate_passed':bool(passed),
       'registration_sha256':file_sha(root/'registration.json'),'aggregate_gates':aggregate,'trials':metrics,
       'evaluation_allowed':bool(passed and stage=='development'),'neural_allowed':bool(passed and stage=='evaluation')}


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--stage',default='development',choices=['development','evaluation']);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=verify_panel(args.root,args.stage);write_json(args.output,result)
    print(json.dumps({'candidate_passed':result['candidate_passed'],'aggregate_gates':result['aggregate_gates']}))

if __name__=='__main__':main()
