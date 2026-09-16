"""Native qpos kinematics and forward observation; never integrates any state."""
from __future__ import annotations
import json
import numpy as np
import mujoco as mj
from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
from flygym_demo.complex_terrain.common import get_default_locomotion_dof_order,dof_spec_to_jointdof
from .realization_io_v11 import RAW

LEGS=('lf','lm','lh','rf','rm','rh')
# Fixed records and fixed numeric schema. Input traces remain hash references.
SCHEMA=[('link_clearance',90),('centroid_world',54),('centroid_thorax',54),('velocity_components',54),('normal_per_link',30),('normal_nonpositive_distance',6)]
WIDTH=sum(n for _,n in SCHEMA)
SHAPES={'link_clearance':(3,6,5),'centroid_world':(3,6,3),'centroid_thorax':(3,6,3),'velocity_components':(6,3,3),'normal_per_link':(6,5),'normal_nonpositive_distance':(6,)}
RECORDS=('actual','command','unit_r1')

class Native:
    def __init__(self,raw=RAW):
        self.raw=raw;self.model=m=mj.MjModel.from_binary_path(str(raw/'model.mjb'))
        self.actual=mj.MjData(m);self.references=[mj.MjData(m),mj.MjData(m)]
        self.foot=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,f'fly-0/{l}_tarsus{k}') for l in LEGS for k in range(1,6)])
        self.thorax=mj.mj_name2id(m,mj.mjtObj.mjOBJ_BODY,'fly-0/c_thorax')
        self.ground=mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'ground_plane')
        if min(self.foot)<0 or len(set(self.foot))!=30 or self.thorax<0 or self.ground<0:raise ValueError('missing native identifiers')
        self.foot_index={int(g):i for i,g in enumerate(self.foot)}
        self.active=np.flatnonzero(m.actuator_trntype==int(mj.mjtTrn.mjTRN_JOINT))
        self.adhesion=np.flatnonzero(m.actuator_trntype==int(mj.mjtTrn.mjTRN_BODY))
        self.joints=m.actuator_trnid[self.active,0];self.qadr=m.jnt_qposadr[self.joints];self.dadr=m.jnt_dofadr[self.joints]
        self.passive=np.array(sorted(set(range(m.nv))-set(range(6))-set(self.dadr)))
        self.passive_q=np.array([m.jnt_qposadr[j] for j in range(1,m.njnt) if m.jnt_dofadr[j] in self.passive])
        if len(self.active)!=42 or len(self.passive)!=24 or len(self.adhesion)!=6 or m.nq!=73 or m.nv!=72:raise ValueError('native partition changed')
        if not np.all(m.jnt_type[self.joints]==int(mj.mjtJoint.mjJNT_HINGE)):raise ValueError('nonhinge transmission')
        if not np.all(m.actuator_gear[self.active,1:]==0) or not np.all(m.actuator_gear[self.active,0]!=0):raise ValueError('unsupported gear')
        if np.any(m.actuator_biasprm[self.active,2:]!=0) or np.any(m.actuator_gainprm[self.active,1:]!=0):raise ValueError('nonposition actuator equation')
        if m.geom_type[self.ground]!=int(mj.mjtGeom.mjGEOM_PLANE) or not np.array_equal(m.geom_pos[self.ground],[0,0,0]) or not np.array_equal(m.geom_quat[self.ground],[1,0,0,0]):raise ValueError('ground frame changed')
        self.vertices=[]
        for g in self.foot:
            if m.geom_type[g]!=int(mj.mjtGeom.mjGEOM_MESH):raise ValueError('nonmesh tarsus')
            mesh=m.geom_dataid[g];a=m.mesh_vertadr[mesh];n=m.mesh_vertnum[mesh]
            self.vertices.append(m.mesh_vert[a:a+n].astype(float))
        self.centroids=np.array([self.vertices[i].mean(axis=0) for i in range(4,30,5)])
        self.steps=PreprogrammedSteps(path=raw/'sources/0114-single_steps_untethered.pkl')
        self.order=get_default_locomotion_dof_order()
        if len(self.order)!=42:raise ValueError('DOF order')
        self.dof_indices=[[self.order.index(dof_spec_to_jointdof(leg,spec)) for spec in self.steps.dofs_per_leg] for leg in LEGS]
        for i,dof in enumerate(self.order):
            name=mj.mj_id2name(m,mj.mjtObj.mjOBJ_JOINT,int(self.joints[i]))
            # Native enum representations are independently bound to joint names.
            expected=f'fly-0/{dof.parent.name}-{dof.child.name}-{dof.axis.value}'
            if name!=expected:raise ValueError(f'DOF/native mismatch {name} != {expected}')
        self.jac=np.empty((3,m.nv));self.mass=np.empty((m.nv,m.nv));self.force=np.empty(6)
    def targets_to_qpos(self,ctrl):
        m=self.model;a=self.active
        return -(m.actuator_gainprm[a,0]*ctrl+m.actuator_biasprm[a,0])/(m.actuator_biasprm[a,1]*m.actuator_gear[a,0])
    def unit_targets(self,phases):
        out=np.empty((len(phases),42))
        for i,leg in enumerate(LEGS):out[:,self.dof_indices[i]]=self.steps.get_joint_angles(leg,phases[:,i],1).T
        return out
    def source_targets(self,phases,magnitudes,corrections):
        # Read-only source evaluation with retained correction, no reflex advancement.
        from flygym_demo.complex_terrain.hybrid_controller import _CORRECTION_VECTORS,_RIGHT_LEG_CORRECTION_SIGN
        out=np.empty((len(phases),42))
        for i,leg in enumerate(LEGS):
            angles=self.steps.get_joint_angles(leg,phases[:,i],magnitudes[:,i]).T
            vector=_CORRECTION_VECTORS[leg[1]]
            if leg.startswith('r'):vector=vector*_RIGHT_LEG_CORRECTION_SIGN
            out[:,self.dof_indices[i]]=angles+corrections[:,i,None]*vector
        return out
    def observe(self,qpos,qvel,ctrl,tick,check_balance=False):
        m=self.model;d=self.actual;d.qpos[:]=qpos;d.qvel[:]=qvel;d.ctrl[:]=ctrl;d.time=tick*.0001
        mj.mj_forward(m,d)
        if not all(np.isfinite(a).all() for a in [d.qacc,d.qfrc_constraint,d.actuator_force,d.geom_xpos,d.geom_xmat]):raise FloatingPointError('nonfinite native reconstruction')
        flags=np.zeros(6,dtype=bool);normal=np.zeros(30);penetrating=np.zeros(6)
        for index,c in enumerate(d.contact):
            g1,g2=int(c.geom1),int(c.geom2)
            foot=g2 if g1==self.ground else g1 if g2==self.ground else -1
            if foot not in self.foot_index:continue
            j=self.foot_index[foot]
            if c.dist<=0:flags[j//5]=True
            mj.mj_contactForce(m,d,index,self.force)
            if not np.isfinite(self.force).all() or self.force[0]<-1e-10:raise FloatingPointError('invalid normal force')
            fn=max(0.,float(self.force[0]));normal[j]+=fn
            if c.dist<=0:penetrating[j//5]+=fn
        residual=0.
        if check_balance:
            mj.mj_fullM(m,self.mass,d.qM)
            lhs=self.mass@d.qacc+d.qfrc_bias
            rhs=d.qfrc_passive+d.qfrc_actuator+d.qfrc_constraint+d.qfrc_applied
            residual=float(np.max(np.abs(lhs-rhs)))
            if residual>1e-7+1e-6*max(np.max(np.abs(lhs)),np.max(np.abs(rhs))):raise ValueError('native force-balance mismatch')
        return flags,normal,penetrating,residual
    def transforms(self,qpos,command,unit):
        m=self.model;datas=[self.actual,*self.references]
        for d,target in zip(self.references,[command,unit]):
            d.qpos[:]=qpos;d.qpos[self.qadr]=self.targets_to_qpos(target);mj.mj_kinematics(m,d)
        p=np.array([d.geom_xpos[self.foot] for d in datas]);r=np.array([d.geom_xmat[self.foot].reshape(30,3,3) for d in datas])
        return p,r
    def velocities(self,world_points):
        m=self.model;d=self.actual;out=np.empty((6,3,3))
        for leg,p in enumerate(world_points):
            mj.mj_jac(m,d,self.jac,None,p,int(m.geom_bodyid[self.foot[leg*5+4]]))
            out[leg,0]=self.jac[:,:6]@d.qvel[:6]
            out[leg,1]=self.jac[:,self.dadr]@d.qvel[self.dadr]
            out[leg,2]=self.jac[:,self.passive]@d.qvel[self.passive]
        return out
    def geometry(self,positions,rotations,thorax_position,thorax_rotation):
        # Batch full-mesh directional support; no subsampling or hull approximation.
        n=len(positions);low=np.empty((n,3,30))
        for j,v in enumerate(self.vertices):
            z=rotations[:,:,j,2,:].reshape(-1,3)@v.T
            low[:,:,j]=z.min(axis=1).reshape(n,3)+positions[:,:,j,2]
        world=np.einsum('nrldk,lk->nrld',rotations[:,:,4::5],self.centroids)+positions[:,:,4::5]
        body=np.einsum('nkd,nrlk->nrld',thorax_rotation,world-thorax_position[:,None,None,:])
        return low.reshape(n,3,6,5),world,body
