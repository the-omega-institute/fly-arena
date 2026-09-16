"""Load authoritative MuJoCo binary/state without model construction or tuning.

FlyGym's unchanged force observer operates on an explicit segment-to-geom map.
A second contact-pair reconstruction corroborates every positive sensor value.
Forces after mj_step are evaluated at tick-1; initial mj_forward is at tick 0.
No extra forward call is inserted at scientific input boundaries.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib, json
import numpy as np
import mujoco as mj
from flygym.anatomy import BodySegment
from flygym.simulation import Simulation
from .contact_v6 import LEGS

BINARY_SHA = '5a9b00ad3df366f2837aa811cf7b732e8c55b912c0afc8080c58e1db71bd4691'

def penetration(tick):
    t=tick*.0001
    return 0. if t<.2 or t>=.5 else .05*(t-.2)/.1 if t<.3 else .05 if t<.4 else .05*(.5-t)/.1

class BinaryFixture:
    def __init__(self, inputs):
        inputs=Path(inputs)
        if hashlib.sha256((inputs/'compiled.mjb').read_bytes()).hexdigest()!=BINARY_SHA:
            raise ValueError('authoritative binary mismatch')
        self.model=mj.MjModel.from_binary_path(str(inputs/'compiled.mjb'))
        self.data=mj.MjData(self.model)
        self.geometry=json.loads((inputs/'geometry.json').read_text())
        m=self.model; g=self.geometry
        self.jids=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_JOINT,n) for n in g['joint_names']])
        self.aids=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_ACTUATOR,n) for n in g['actuator_names']])
        if min(self.jids)<0 or min(self.aids)<0: raise ValueError('missing named actuator/joint')
        self.qadr=m.jnt_qposadr[self.jids]; self.vadr=m.jnt_dofadr[self.jids]
        self.neutral=np.array(g['neutral_rad']); self.signs=np.array(g['flexion_signs'])
        self.probe_geom=mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'probe_sphere')
        self.probe_id=m.body_mocapid[mj.mj_name2id(m,mj.mjtObj.mjOBJ_BODY,'probe')]
        assert np.array_equal(self.qadr,g['qpos_addresses'])
        assert np.all(m.actuator_gainprm[self.aids,0]==45) and np.all(m.actuator_forcerange[self.aids]==[-65,65])
        assert np.array_equal(m.actuator_trnid[self.aids,0],self.jids)
        assert (m.nq,m.nv,m.nu,m.neq)==(66,66,42,60) and m.opt.timestep==.0001
        names=[l.lower()+'_'+s for l in LEGS for s in ('tibia','tarsus1','tarsus2')]
        self.segment_geoms=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'fixture/'+s) for s in names])
        assert min(self.segment_geoms)>=0 and len(set(self.segment_geoms))==18
        self.segment_map={int(gid):i for i,gid in enumerate(self.segment_geoms)}
        self.segment_names=names
        self.sim=SimpleNamespace(mj_model=m,mj_data=self.data,
            _internal_geomid_by_bodyseg_by_fly={'fixture':{BodySegment(n):int(g) for n,g in zip(names,self.segment_geoms)}})
        ids=[i for i in range(m.nbody) if (mj.mj_id2name(m,mj.mjtObj.mjOBJ_BODY,i) or '').startswith('fixture/')]
        self.weight=float(m.body_mass[ids].sum()*np.linalg.norm(m.opt.gravity))
        assert self.weight==g['body_weight_native']
        self.tick=0; self.command=np.zeros(6)
        self.initial=dict(np.load(inputs/'body-rest.npz'))
        self.restore(self.initial)
        assert np.array_equal(self.data.qpos[self.qadr],self.neutral)
        assert np.array_equal(self.data.mocap_pos[self.probe_id],[0,0,10])

    def checkpoint(self):
        sig=mj.mjtState.mjSTATE_INTEGRATION
        state=np.empty(mj.mj_stateSize(self.model,sig)); mj.mj_getState(self.model,self.data,state,sig)
        return {'integration':state,'tick':np.array(self.tick),'command':self.command.copy()}

    def restore(self, state):
        template=self.checkpoint()
        if set(state)!=set(template): raise ValueError('physical fields')
        for k,v in template.items():
            a=np.asarray(state[k])
            if a.shape!=v.shape or a.dtype!=v.dtype or not np.isfinite(a).all(): raise ValueError('physical '+k)
        if state['tick']<0 or abs(state['integration'][0]-state['tick']*.0001)>1e-8 or np.max(np.abs(state['command']))>.1: raise ValueError('physical bounds/time')
        mj.mj_setState(self.model,self.data,state['integration'],mj.mjtState.mjSTATE_INTEGRATION)
        self.tick=int(state['tick']); self.command=state['command'].copy(); mj.mj_forward(self.model,self.data)

    def command_knees(self, command):
        command=np.asarray(command)
        if command.shape!=(6,) or not np.isfinite(command).all() or np.max(np.abs(command))>.1+1e-12: raise ValueError('command range')
        self.command=command.copy(); self.data.ctrl[self.aids]=self.neutral+self.signs*command

    def step(self):
        mj.mj_step(self.model,self.data); self.tick+=1
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all(): raise ValueError('nonfinite body')
        if np.max(np.abs(self.data.actuator_force[self.aids]))>65+1e-9: raise ValueError('force contract')
        if abs(self.data.time-self.tick*.0001)>1e-8: raise ValueError('body clock')

    def observe(self, sham=False):
        forces=Simulation.get_bodysegment_contact_forces(self.sim,'fixture',self.segment_names,ground_only=False).reshape(6,3,3)
        reconstructed=np.zeros((18,3)); loaded=np.zeros(6,dtype=bool); rows=[]
        for ci in range(self.data.ncon):
            c=self.data.contact[ci]; w=np.zeros(6); mj.mj_contactForce(self.model,self.data,ci,w)
            g1,g2=int(c.geom1),int(c.geom2); world=c.frame.reshape(3,3).T@w[:3]
            # All raw pairs, including inactive pairs, retained with native wrench.
            rows.append([ci,g1,g2,int(c.exclude),int(c.efc_address),float(c.dist),*w,*c.frame])
            if c.exclude: continue
            if g1 in self.segment_map: reconstructed[self.segment_map[g1]]-=world
            if g2 in self.segment_map: reconstructed[self.segment_map[g2]]+=world
            other=g2 if g1==self.probe_geom else g1 if g2==self.probe_geom else -1
            if other in self.segment_map and c.efc_address>=0 and w[0]>0:
                loaded[self.segment_map[other]//3]=True
            if sham and self.probe_geom in (g1,g2) and c.efc_address>=0 and w[0]>0:
                raise ValueError('loaded probe contact during remote sham')
        if not np.array_equal(forces.reshape(18,3),reconstructed): raise ValueError('contact force reconstruction mismatch')
        ratios=np.linalg.norm(forces,axis=2).sum(axis=1)/self.weight
        if not np.isfinite(ratios).all() or np.any((ratios>0)&~loaded): raise ValueError('positive net force lacks loaded probe/leg pair')
        if sham and (np.any(ratios>0) or not np.array_equal(self.data.mocap_pos[self.probe_id],[0,0,10])): raise ValueError('sham contamination')
        return ratios,forces,loaded,np.asarray(rows,dtype=float).reshape(-1,21)
