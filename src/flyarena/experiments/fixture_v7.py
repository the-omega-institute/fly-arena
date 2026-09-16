"""Actual FlyGym/MuJoCo tethered six-knee fixture. No locomotion claim."""
import numpy as np
import mujoco as mj
from flygym.compose.world import TetheredWorld
from flygym.compose import ActuatorType
from flygym.anatomy import BodySegment
from flygym.utils.math import Rotation3D
from flygym.simulation import Simulation
from flygym_demo.complex_terrain.common import make_locomotion_fly, dof_spec_to_jointdof
from .contact_v6 import LEGS, observe_flygym_contact

class Fixture:
    def __init__(self):
        fly = make_locomotion_fly('fixture', add_adhesion=False)
        dofs = [dof_spec_to_jointdof(l.lower(), ('trochanterfemur','tibia','pitch')) for l in LEGS]
        self.joint_names = ['fixture/'+fly.jointdof_to_mjcfjoint[d].name for d in dofs]
        self.actuator_names = ['fixture/'+fly.jointdof_to_mjcfactuator_by_type[ActuatorType.POSITION][d].name for d in dofs]
        self.constraints = {}
        for dof, joint in fly.jointdof_to_mjcfjoint.items():
            if dof not in dofs:
                angle = fly.jointdof_to_neutralangle[dof]
                fly.mjcf_root.add_equality(name='lock_'+joint.name, type=mj.mjtEq.mjEQ_JOINT,
                    name1=joint.name, data=[angle,0,0,0,0,0,0,0,0,0,0], solref=[.0002,1], solimp=[.9999,.9999,.001,.5,2])
                self.constraints[joint.name] = angle
        world = TetheredWorld()
        world.add_fly(fly, (0,0,0), Rotation3D('quat',(1,0,0,0)))
        probe = world.mjcf_root.worldbody.add_body(name='probe', mocap=True, pos=[0,0,10])
        probe.add_geom(name='probe_sphere', type=mj.mjtGeom.mjGEOM_SPHERE, size=[.1,0,0], contype=4, conaffinity=1, friction=[1,.02,.0001])
        for geoms in fly.bodyseg_to_mjcfgeom.values():
            for geom in geoms: geom.contype=1; geom.conaffinity=4
        self.sim = Simulation(world, timestep=.0001)
        self.model, self.data = self.sim.mj_model, self.sim.mj_data
        self.jids = np.array([mj.mj_name2id(self.model,mj.mjtObj.mjOBJ_JOINT,n) for n in self.joint_names])
        self.aids = np.array([mj.mj_name2id(self.model,mj.mjtObj.mjOBJ_ACTUATOR,n) for n in self.actuator_names])
        assert min(self.jids)>=0 and min(self.aids)>=0
        self.qadr = self.model.jnt_qposadr[self.jids]; self.vadr = self.model.jnt_dofadr[self.jids]
        self.neutral = self.data.qpos[self.qadr].copy()
        self.probe_id = self.model.body_mocapid[mj.mj_name2id(self.model,mj.mjtObj.mjOBJ_BODY,'probe')]
        assert np.all(self.model.actuator_gainprm[self.aids,0] == 45)
        assert np.all(self.model.actuator_forcerange[self.aids] == [-65,65])
        assert np.all(self.model.actuator_trnid[self.aids,0] == self.jids)
        mj.mj_forward(self.model,self.data)
        self.tick = 0; self.command = np.zeros(6); self.signs = np.ones(6)
        self.initial = self.checkpoint()

    def checkpoint(self):
        sig = mj.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mj.mj_stateSize(self.model,sig)); mj.mj_getState(self.model,self.data,state,sig)
        return {'integration':state,'tick':np.array(self.tick),'command':self.command.copy()}

    def restore(self, state):
        template = self.checkpoint()
        if set(state)!=set(template): raise ValueError('physical fields')
        for k,v in template.items():
            if state[k].shape!=v.shape or state[k].dtype!=v.dtype or not np.isfinite(state[k]).all(): raise ValueError('physical '+k)
        if state['tick']<0 or abs(state['integration'][0]-state['tick']*.0001)>1e-8 or np.max(np.abs(state['command']))>.1: raise ValueError('physical bounds/time')
        mj.mj_setState(self.model,self.data,state['integration'],mj.mjtState.mjSTATE_INTEGRATION)
        self.tick=int(state['tick']); self.command=state['command'].copy(); mj.mj_forward(self.model,self.data)

    def command_knees(self, command):
        command=np.asarray(command)
        if command.shape!=(6,) or not np.isfinite(command).all() or np.max(np.abs(command))>.1+1e-12: raise ValueError('command range')
        self.command=command.copy(); self.data.ctrl[self.aids]=self.neutral+self.signs*command

    def step(self):
        self.sim.step(); self.tick+=1
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all(): raise ValueError('nonfinite body')
        if np.max(np.abs(self.data.actuator_force[self.aids]))>65+1e-9: raise ValueError('force contract')
        if abs(self.data.time-self.tick*.0001)>1e-8: raise ValueError('body clock')

    def points(self, leg):
        return np.array([self.data.xpos[mj.mj_name2id(self.model,mj.mjtObj.mjOBJ_BODY,'fixture/'+leg.lower()+'_'+s)] for s in ('trochanterfemur','tibia','tarsus1')])

    def angle(self, leg):
        p,k,d=self.points(leg); a=p-k; b=d-k
        return float(np.arccos(np.clip(a@b/(np.linalg.norm(a)*np.linalg.norm(b)),-1,1)))

    def geometry(self):
        derivatives=[]; points=[]
        for i,l in enumerate(LEGS):
            points.append(self.points(l).tolist()); values=[]
            for eps in (-1e-5,1e-5):
                self.restore(self.initial); self.data.qpos[self.qadr[i]]+=eps; mj.mj_forward(self.model,self.data); values.append(self.angle(l))
            derivative=(values[1]-values[0])/2e-5
            if abs(derivative)<.1: raise ValueError('ambiguous flexion')
            derivatives.append(derivative)
        self.restore(self.initial); self.signs=-np.sign(derivatives)
        ids=[i for i in range(self.model.nbody) if (mj.mj_id2name(self.model,mj.mjtObj.mjOBJ_BODY,i) or '').startswith('fixture/')]
        return {'joint_names':self.joint_names,'actuator_names':self.actuator_names,'qpos_addresses':self.qadr.tolist(),
                'neutral_rad':self.neutral.tolist(),'flexion_signs':self.signs.tolist(),'included_angle_derivative':derivatives,
                'neutral_landmarks_mm':points,'constraints':self.constraints,'body_weight_native':float(self.model.body_mass[ids].sum()*np.linalg.norm(self.model.opt.gravity)),
                'gravity_mm_s2':self.model.opt.gravity.tolist(),'nq':self.model.nq,'nv':self.model.nv,'nu':self.model.nu,
                'neq':self.model.neq,'kp':45,'forcerange':[-65,65], 'mechanics':'mocap thorax; non-Ti joint equality at NEUTRAL; no ground, CPG or adhesion; probe initially remote'}
