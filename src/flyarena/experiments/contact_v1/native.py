"""Prospective native adapter. Nothing here instantiates or steps a model on import.

Native calls below are reviewable implementation, NOT executed in the source-only
flight. Recording the completed interval is separate from silent controller state.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from .contracts import (Binding, Contact, Observation, ContractError, DT, LEGS,
                        MAX_CONTACTS, MAX_COORDINATES, MAX_VERTICES, drives,
                        SILENCE, array, rotation, encode, decode, observation_state,
                        observation_from_state, identity)
from .law import Controller, Proposal


def _mj():
    import mujoco
    return mujoco


def transport_material(point_prior, prior_position, prior_rotation, current_position, current_rotation):
    """Pure material transport; force ownership is never reassigned to a minimum."""
    point_prior=array(point_prior,(3,),'prior material point')
    p0=array(prior_position,(3,),'prior body position'); p1=array(current_position,(3,),'current body position')
    r0=rotation(prior_rotation,'prior rotation'); r1=rotation(current_rotation,'current rotation')
    local=r0.T@(point_prior-p0)
    return local,p1+r1@local


@dataclass(frozen=True)
class IntervalRow:
    index: int
    geom: int
    ground: int
    leg: int
    point: np.ndarray
    frame: np.ndarray
    distance: float
    force: np.ndarray


@dataclass(frozen=True)
class CompletedInterval:
    tick: int  # prestate index, endpoint is tick+1
    model_hash: str
    qpos: np.ndarray
    qvel: np.ndarray
    rows: tuple

    def validate(self,binding,endpoint_tick):
        if type(self.tick) is not int or self.tick!=endpoint_tick-1 or self.model_hash!=binding.model_hash or not isinstance(self.rows,tuple) or len(self.rows)>MAX_CONTACTS:
            raise ContractError('completed interval clock/capacity')
        array(self.qpos,(binding.nq,),'interval qpos'); array(self.qvel,(binding.nv,),'interval qvel')
        ids=set(); owners={int(g):i for i,row in enumerate(binding.foot_geoms) for g in row}
        for row in self.rows:
            if not isinstance(row,IntervalRow) or any(type(getattr(row,k)) is not int for k in ('index','geom','ground','leg')) or row.index<0 or row.index in ids:
                raise ContractError('interval row identity')
            ids.add(row.index)
            if row.geom not in binding.fly_geoms or row.ground!=binding.ground_geom or row.leg!=owners.get(row.geom,-1): raise ContractError('interval row ownership')
            array(row.point,(3,),'interval point'); array(row.force,(6,),'interval force'); rotation(row.frame,'interval frame')
            if not np.isfinite(row.distance): raise ContractError('interval distance')
        return self


def interval_state(packet):
    """Pure complete recorder serialization; no native cache or force reread."""
    return {**deepcopy(packet.__dict__), 'rows':tuple(deepcopy(row.__dict__) for row in packet.rows)}


def interval_from_state(state):
    copied=deepcopy(state)
    if not isinstance(copied,dict) or set(copied)!={'tick','model_hash','qpos','qvel','rows'}:
        raise ContractError('interval checkpoint schema')
    copied['rows']=tuple(IntervalRow(**row) for row in copied['rows'])
    return CompletedInterval(**copied)


def validate_pre_step(saved,binding,tick):
    """Pure recorder schema; saved arrays originate from authoritative pre-step data."""
    if (not isinstance(saved,dict) or set(saved)!={'tick','model_hash','qpos','qvel'}
            or type(saved['tick']) is not int or saved['tick']!=tick or tick<0
            or saved['model_hash']!=binding.model_hash):
        raise ContractError('saved pre-step identity')
    array(saved['qpos'],(binding.nq,),'saved pre-step qpos')
    array(saved['qvel'],(binding.nv,),'saved pre-step qvel')


def validate_recorder(recorder,binding,tick):
    """Validate complete material packet against the independently saved prestate."""
    if not isinstance(recorder,dict): raise ContractError('recorder schema')
    if tick==0 and recorder=={}: return None
    if tick==0 and set(recorder)=={'pre_step'}:
        validate_pre_step(recorder['pre_step'],binding,0)
        return None
    if set(recorder)!={'pre_step','completed_interval'}: raise ContractError('complete recorder schema')
    packet=interval_from_state(recorder['completed_interval']).validate(binding,tick)
    saved=recorder['pre_step']; validate_pre_step(saved,binding,tick-1)
    if not np.array_equal(packet.qpos,saved['qpos']) or not np.array_equal(packet.qvel,saved['qvel']):
        raise ContractError('packet does not own actual saved pre-step state')
    return packet


def validate_observed_packet(obs,packet):
    """Pure equality check shared by apply and action-boundary checkpoint restore."""
    if (packet is None or packet.tick!=obs.tick-1 or packet.model_hash!=obs.model_hash
            or not np.array_equal(packet.qpos,obs.prior_qpos) or not np.array_equal(packet.qvel,obs.prior_qvel)
            or len(packet.rows)!=len(obs.contacts)):
        raise ContractError('native/sensor interval mismatch')
    for row,con in zip(packet.rows,obs.contacts):
        if (row.index!=con.index or row.geom!=con.geom or row.ground!=con.ground or row.leg!=con.leg
                or row.distance!=con.distance or not np.array_equal(row.force,con.force)
                or not np.array_equal(row.frame,con.frame) or not np.array_equal(row.point,con.point_prior)):
            raise ContractError('recorder/sensor material ownership')


def model_digest(model):
    """Prospective independent compiled-observation binding, not an MJB-file hash."""
    fields=('actuator_trnid','actuator_trntype','actuator_gear','actuator_gaintype',
            'actuator_gainprm','actuator_biastype','actuator_biasprm','actuator_forcelimited',
            'actuator_forcerange','actuator_ctrllimited','actuator_ctrlrange','actuator_dyntype',
            'jnt_type','jnt_qposadr','jnt_dofadr','jnt_limited','jnt_range','body_parentid',
            'body_mass','body_inertia','body_ipos','body_iquat','body_pos','body_quat',
            'geom_type','geom_bodyid','geom_dataid','geom_pos','geom_quat','geom_size',
            'geom_friction','geom_contype','geom_conaffinity','mesh_vert','mesh_vertadr','mesh_vertnum')
    h=hashlib.sha256()
    for name in fields:
        a=np.ascontiguousarray(getattr(model,name))
        h.update(name.encode()); h.update(a.dtype.str.encode()); h.update(str(a.shape).encode()); h.update(a.tobytes())
    h.update(np.asarray(model.opt.gravity,dtype=np.float64).tobytes())
    h.update(np.asarray([model.opt.timestep],dtype=np.float64).tobytes())
    return h.hexdigest()


def bind_native(model,steps,*,expected_model_hash,asset_hash,input_hash,fly_name='fly-0'):
    """Use only in later registered runtime. No model building occurs here."""
    if int(model.nq)>MAX_COORDINATES or int(model.nv)>MAX_COORDINATES:
        raise ContractError('native coordinate capacity')
    if int(model.nu)!=48 or float(model.opt.timestep)!=DT:
        raise ContractError('native action count/timestep')
    if model_digest(model)!=identity(expected_model_hash,'expected_model_hash'):
        raise ContractError('compiled model changed')
    mj=_mj()
    from flygym_demo.complex_terrain.common import get_default_locomotion_dof_order, dof_spec_to_jointdof
    if tuple(steps.legs)!=LEGS: raise ContractError('native leg order')
    order=get_default_locomotion_dof_order()
    indices=np.array([[order.index(dof_spec_to_jointdof(leg,spec)) for spec in steps.dofs_per_leg] for leg in LEGS],dtype=np.int64)
    joints=np.asarray(model.actuator_trnid[:42,0],dtype=np.int64)
    if len(set(joints))!=42 or np.any(model.jnt_type[joints]!=mj.mjtJoint.mjJNT_HINGE) or np.any(model.actuator_trntype[:42]!=mj.mjtTrn.mjTRN_JOINT):
        raise ContractError('unit hinge transmission required')
    unit=np.zeros((42,6)); unit[:,0]=1.
    if not np.array_equal(model.actuator_gear[:42],unit): raise ContractError('actuator gear changed')
    if (np.any(model.actuator_gaintype[:42]!=mj.mjtGain.mjGAIN_FIXED) or np.any(model.actuator_biastype[:42]!=mj.mjtBias.mjBIAS_AFFINE)
            or np.any(model.actuator_gainprm[:42,0]!=45.) or np.any(model.actuator_biasprm[:42,1]!=-45.)
            or np.any(model.actuator_biasprm[:42,0]!=0.) or np.any(model.actuator_biasprm[:42,2]!=0.)
            or np.any(model.actuator_dyntype[:42]!=mj.mjtDyn.mjDYN_NONE)
            or not np.all(model.actuator_forcelimited[:42]) or not np.array_equal(model.actuator_forcerange[:42],np.tile([-65.,65.],(42,1)))
            or np.any(model.actuator_gainprm[42:,0]!=40.) or np.any(model.actuator_trntype[42:]!=mj.mjtTrn.mjTRN_BODY)):
        raise ContractError('native gain/force/adhesion contract changed')
    lower=np.full(42,-np.inf); upper=np.full(42,np.inf)
    for index,joint in enumerate(joints):
        for enabled,limits in ((model.jnt_limited[joint],model.jnt_range[joint]),(model.actuator_ctrllimited[index],model.actuator_ctrlrange[index])):
            if enabled:
                if not np.isfinite(limits).all() or limits[0]>limits[1]: raise ContractError('enabled native interval')
                lower[index]=max(lower[index],limits[0]); upper[index]=min(upper[index],limits[1])
    lookup=lambda kind,name: int(mj.mj_name2id(model,kind,name))
    foot=np.array([[lookup(mj.mjtObj.mjOBJ_GEOM,f'{fly_name}/{leg}_tarsus{j}') for j in range(1,6)] for leg in LEGS],dtype=np.int64)
    ground=lookup(mj.mjtObj.mjOBJ_GEOM,'ground_plane')
    thorax=lookup(mj.mjtObj.mjOBJ_BODY,f'{fly_name}/c_thorax')
    if np.any(foot<0) or ground<0 or thorax<0: raise ContractError('missing owned native geometry')
    if model.geom_type[ground]!=mj.mjtGeom.mjGEOM_PLANE or int(model.geom_bodyid[ground])!=0 or not np.array_equal(model.geom_pos[ground],np.zeros(3)) or not np.array_equal(model.geom_quat[ground],np.array([1.,0.,0.,0.])):
        raise ContractError('registered fixed plane required')
    if np.any(model.geom_type[foot]!=mj.mjtGeom.mjGEOM_MESH): raise ContractError('owned mesh type')
    if not np.array_equal(np.asarray(model.opt.gravity)[:2],np.zeros(2)) or model.opt.gravity[2]>=0:
        raise ContractError('native gravity orientation')
    fly_geoms=tuple(i for i in range(model.ngeom) if (mj.mj_id2name(model,mj.mjtObj.mjOBJ_GEOM,i) or '').startswith(fly_name+'/'))
    bodies=tuple(i for i in range(model.nbody) if (mj.mj_id2name(model,mj.mjtObj.mjOBJ_BODY,i) or '').startswith(fly_name+'/'))
    masses=np.asarray(model.body_mass[list(bodies)],dtype=np.float64)
    if not len(bodies) or not np.isfinite(masses).all() or np.any(masses<=0): raise ContractError('fly body masses')
    roots=[j for j in range(model.njnt) if model.jnt_type[j]==mj.mjtJoint.mjJNT_FREE and int(model.jnt_bodyid[j]) in bodies]
    if len(roots)!=1: raise ContractError('one floating root required')
    root_start=int(model.jnt_dofadr[roots[0]])
    meshes=model.geom_dataid[foot]
    if np.any(meshes<0): raise ContractError('mesh data map')
    total=int(np.sum(model.mesh_vertnum[meshes]))
    if total>MAX_VERTICES: raise ContractError('foot vertex capacity')
    beta=np.array([steps.swing_period[leg][1]+np.pi/4 for leg in LEGS],dtype=np.float64)
    if any(steps.swing_period[leg][0]!=0 for leg in LEGS): raise ContractError('native swing start')
    pattern=np.array([[0,1,0,1,0,1],[1,0,1,0,1,0]]*3,dtype=np.float64)
    binding=Binding(expected_model_hash,asset_hash,input_hash,int(model.nq),int(model.nv),
                    np.asarray(model.jnt_qposadr[joints][indices],dtype=np.int64),
                    np.asarray(model.jnt_dofadr[joints][indices],dtype=np.int64),
                    np.arange(root_start,root_start+6,dtype=np.int64),foot,ground,fly_geoms,
                    lower[indices],upper[indices],beta,pattern*10,pattern*np.pi,total).validate()
    # Native adhesion inputs are ordered by leg. Bind every transmission to the
    # distal body rather than assuming the last six inputs happen to match.
    if not np.array_equal(model.actuator_trnid[42:,0],model.geom_bodyid[foot[:,4]]):
        raise ContractError('adhesion transmission leg order')
    return NativeAdapter(model,steps,binding,indices,thorax,bodies)


class NativeAdapter:
    def __init__(self,model,steps,binding,indices,thorax,bodies):
        self.model=model; self.steps=steps; self.binding=deepcopy(binding)
        self.indices=np.asarray(indices,dtype=np.int64).copy(); self.thorax=int(thorax); self.bodies=tuple(bodies)
        self.vertices={}
        for geom in binding.foot_geoms.flat:
            mesh=int(model.geom_dataid[geom]); start=int(model.mesh_vertadr[mesh]); count=int(model.mesh_vertnum[mesh])
            if count<=0: raise ContractError('empty foot mesh')
            self.vertices[int(geom)]=np.asarray(model.mesh_vert[start:start+count],dtype=np.float64).copy()
        # Immutable config only. Observation workspaces are private and disposable;
        # no native workspace state changes on controller rejection or silence.

    def capture_completed(self,data,pre_qpos,pre_qvel,interval_tick):
        """Recorder hook immediately after one physics step; never calls forward."""
        b=self.binding
        array(pre_qpos,(b.nq,),'saved prestate qpos'); array(pre_qvel,(b.nv,),'saved prestate qvel')
        if type(interval_tick) is not int or interval_tick<0: raise ContractError('interval tick')
        owners={int(g):i for i,row in enumerate(b.foot_geoms) for g in row}
        selected=[]
        for index in range(int(data.ncon)):
            con=data.contact[index]; g1=int(con.geom1); g2=int(con.geom2)
            if g1 in b.fly_geoms and g2==b.ground_geom: geom=g1
            elif g2 in b.fly_geoms and g1==b.ground_geom: geom=g2
            else: continue
            selected.append((index,geom))
        if len(selected)>MAX_CONTACTS: raise ContractError('owned contact capacity; no truncation')
        mj=_mj(); rows=[]
        for index,geom in selected:
            con=data.contact[index]; force=np.empty(6,dtype=np.float64)
            mj.mj_contactForce(self.model,data,index,force)
            rows.append(IntervalRow(index,geom,b.ground_geom,owners.get(geom,-1),
                                    np.asarray(con.pos,dtype=np.float64).copy(),
                                    np.asarray(con.frame,dtype=np.float64).reshape(3,3).copy(),float(con.dist),force))
        packet=CompletedInterval(interval_tick,b.model_hash,pre_qpos.copy(),pre_qvel.copy(),tuple(rows))
        return packet.validate(b,interval_tick+1)

    def _geometry(self,qpos):
        mj=_mj(); data=mj.MjData(self.model)
        data.qpos[:]=qpos; mj.mj_kinematics(self.model,data); mj.mj_comPos(self.model,data)
        return data

    def _jac(self,data,point,body):
        J=np.zeros((3,self.binding.nv)); _mj().mj_jac(self.model,data,J,None,point,int(body)); return J

    def observe(self,qpos,qvel,tick,interval,actuator_force):
        b=self.binding
        # Capacity, clock and full packet validity are checked before workspaces.
        qpos=array(qpos,(b.nq,),'current qpos'); qvel=array(qvel,(b.nv,),'current qvel')
        array(actuator_force,(48,),'actuator force')
        if not isinstance(interval,CompletedInterval): raise ContractError('completed native packet required')
        interval.validate(b,tick)
        current=self._geometry(qpos); prior=self._geometry(interval.qpos)
        minima=np.empty((6,5,3)); ids=np.empty((6,5),dtype=np.int64); jac=np.empty((6,5,3,b.nv))
        distal=np.empty((6,3)); dJ=np.empty((6,3,b.nv))
        for i in range(6):
            for j,geom in enumerate(b.foot_geoms[i]):
                vertices=self.vertices[int(geom)]; R=current.geom_xmat[geom].reshape(3,3); position=current.geom_xpos[geom]
                world=vertices@R.T+position
                index=int(np.argmin(world[:,2])); point=world[index]
                minima[i,j]=point; ids[i,j]=index
                jac[i,j]=self._jac(current,point,self.model.geom_bodyid[geom])
                if j==4:
                    distal[i]=position+R@vertices.mean(axis=0)
                    dJ[i]=self._jac(current,distal[i],self.model.geom_bodyid[geom])
        contacts=[]
        for row in interval.rows:
            body=int(self.model.geom_bodyid[row.geom])
            local,point=transport_material(row.point,prior.xpos[body],prior.xmat[body].reshape(3,3),current.xpos[body],current.xmat[body].reshape(3,3))
            J=self._jac(current,point,body); Jprior=self._jac(prior,row.point,body)
            contacts.append(Contact(row.index,row.geom,row.ground,row.leg,interval.tick,row.force.copy(),row.distance,row.frame.copy(),row.point.copy(),local,point,J,J@qvel,J[:,b.passive_dofs]@qvel[b.passive_dofs],Jprior@interval.qvel))
        mj=_mj(); Jthorax=np.zeros((3,b.nv)); Rthorax=np.zeros((3,b.nv))
        mj.mj_jacBody(self.model,current,Jthorax,Rthorax,self.thorax)
        masses=np.asarray(self.model.body_mass[list(self.bodies)],dtype=np.float64); total=float(masses.sum())
        com=(masses[:,None]*current.xipos[list(self.bodies)]).sum(axis=0)/total
        Jcom=np.zeros((3,b.nv))
        for body,mass in zip(self.bodies,masses):
            J=np.zeros((3,b.nv)); mj.mj_jacBodyCom(self.model,current,J,None,body); Jcom+=(mass/total)*J
        obs=Observation(tick,b.model_hash,qpos,qvel,interval.qpos.copy(),interval.qvel.copy(),
                        current.xpos[self.thorax].copy(),current.xmat[self.thorax].reshape(3,3).copy(),
                        Jthorax@qvel,Rthorax@qvel,com,Jcom@qvel,float(np.linalg.norm(self.model.opt.gravity)),
                        minima,ids,jac,distal,dJ,tuple(contacts),actuator_force.copy())
        return obs.validate(b,-1)

    def angles(self,phi,magnitude):
        result=np.array([self.steps.get_joint_angles(leg,phi[i],magnitude[i]) for i,leg in enumerate(LEGS)],dtype=np.float64)
        return result

    def excursion(self,i,obs,magnitude):
        b=self.binding; geom=int(b.foot_geoms[i,4]); values=[]
        # Two expendable poses; actual root, passive and other-leg positions exact.
        for phase in (0.,float(self.steps.swing_period[LEGS[i]][1])):
            q=obs.qpos.copy()
            angles=np.asarray(self.steps.get_joint_angles(LEGS[i],phase,1.),dtype=np.float64)
            q[b.qadr[i]]=np.clip(angles,b.lower[i],b.upper[i])
            data=self._geometry(q)
            point=data.geom_xpos[geom]+data.geom_xmat[geom].reshape(3,3)@self.vertices[geom].mean(axis=0)
            values.append(float(obs.thorax_rotation[:,0]@(point-obs.thorax_pos)))
        return float(magnitude*abs(values[1]-values[0]))

    def action_ctrl(self,old_ctrl,action):
        result=array(old_ctrl,(48,),'native ctrl')
        result[self.indices]=action.angles
        result[42:48]=action.adhesion.astype(np.float64)
        return result


def native_cache_manifest(data):
    """Read every exposed numeric array and contact array, plus native scalars."""
    result={}
    def add(name,value):
        if isinstance(value,np.ndarray) and value.dtype.kind in 'fiub':
            if value.dtype.kind=='f' and not np.isfinite(value).all(): raise ContractError('nonfinite native cache '+name)
            a=np.ascontiguousarray(value)
            result[name]={'dtype':a.dtype.str,'shape':list(a.shape),'sha256':hashlib.sha256(a.tobytes()).hexdigest()}
    for name in sorted(n for n in dir(data) if not n.startswith('_')):
        add(name,getattr(data,name))
    for name in sorted(n for n in dir(data.contact) if not n.startswith('_')):
        add('contact.'+name,getattr(data.contact,name))
    for name in ('time','ncon','nefc','nJ','nA','nisland'):
        if hasattr(data,name):
            value=getattr(data,name)
            if isinstance(value,(float,int)):
                if not np.isfinite(value): raise ContractError('nonfinite native scalar')
                result['scalar.'+name]=value
    return result


class NativePort:
    """Atomic action/observation/controller boundary; the caller alone steps physics.

    body must expose model,data,tick,drives. The initial neutral native action and
    unchanged source controller reset must be established by the prospective runner.
    """
    VERSION='contact-realization-native-port/v1'
    def __init__(self,body,adapter,controller,registration_binding):
        if controller.binding.token()!=adapter.binding.token(): raise ContractError('adapter/controller binding')
        self.body=body; self.adapter=adapter; self.controller=controller
        self.registration_binding=deepcopy(registration_binding)
        self.sensor_state=None; self.recorder_state={}

    def record_pre_step(self):
        """Copy actual state immediately before the caller's sole physics step.

        This is recorder-only bookkeeping, including silence. No controller,
        sensor, native API or physics call occurs. Return an isolated copy for
        adapter.capture_completed; record_completed checks it against our copy.
        """
        tick=self.body.tick
        saved={'tick':tick,'model_hash':self.controller.binding.model_hash,
               'qpos':np.asarray(self.body.data.qpos).copy(),
               'qvel':np.asarray(self.body.data.qvel).copy()}
        validate_pre_step(saved,self.controller.binding,tick)
        self.recorder_state={'pre_step':deepcopy(saved)}
        return saved

    def record_completed(self,packet):
        """Physics recorder state, including silent intervals; not controller state."""
        if not isinstance(packet,CompletedInterval): raise ContractError('recorder interval type')
        packet.validate(self.controller.binding,int(self.body.tick))
        if set(self.recorder_state)!={'pre_step'}: raise ContractError('missing/past actual pre-step capture')
        new=deepcopy(self.recorder_state)
        new['completed_interval']=interval_state(packet)
        validate_recorder(new,self.controller.binding,int(self.body.tick))
        self.recorder_state=new

    def prepare(self,u,interval=None):
        common,_=drives(u)
        if common<=SILENCE: return None
        recorded=validate_recorder(self.recorder_state,self.controller.binding,int(self.body.tick))
        if recorded is None: raise ContractError('missing completed recorder interval')
        if interval is not None:
            if not isinstance(interval,CompletedInterval) or encode(interval_state(interval))!=encode(interval_state(recorded)):
                raise ContractError('explicit interval differs from owned recorder packet')
        interval=recorded
        self.controller.validate_prestate(int(self.body.tick),interval.qpos,interval.qvel)
        obs=self.adapter.observe(self.body.data.qpos,self.body.data.qvel,int(self.body.tick),interval,np.asarray(self.body.data.actuator_force,dtype=np.float64))
        return self.controller.propose(u,obs,self.adapter)

    def apply(self,prepared):
        if prepared is None: return self.controller.action()
        if not isinstance(prepared,Proposal): raise ContractError('prepared transaction')
        c=self.controller; b=self.body
        c.validate_proposal(prepared)
        obs=observation_from_state(prepared.state['last_observation'])
        if obs.tick!=b.tick or not np.array_equal(obs.qpos,b.data.qpos) or not np.array_equal(obs.qvel,b.data.qvel): raise ContractError('authoritative state moved since proposal')
        packet=validate_recorder(self.recorder_state,c.binding,int(b.tick))
        validate_observed_packet(obs,packet)
        ctrl=self.adapter.action_ctrl(np.asarray(b.data.ctrl,dtype=np.float64),prepared.action)
        staged_state=deepcopy(prepared.state); staged_sensor=observation_state(obs)
        old_ctrl=b.data.ctrl.copy(); old_state=c.state; old_sensor=self.sensor_state; old_revision=c._revision
        try:
            # Same unit transmission/output map as apply_locomotion_action, one
            # complete ctrl assignment; no world step or native cache refresh.
            b.data.ctrl[:]=ctrl; c.state=staged_state; self.sensor_state=staged_sensor
            c._revision+=1
        except BaseException:
            b.data.ctrl[:]=old_ctrl; c.state=old_state; self.sensor_state=old_sensor; c._revision=old_revision
            raise
        return c.action()

    def checkpoint(self):
        validate_recorder(self.recorder_state,self.controller.binding,int(self.body.tick))
        mj=_mj(); copied=mj.MjData(self.body.model)
        mj.mj_copyData(copied,self.body.model,self.body.data)
        signature=mj.mjtState.mjSTATE_INTEGRATION
        integration=np.empty(mj.mj_stateSize(self.body.model,signature))
        mj.mj_getState(self.body.model,copied,integration,signature)
        return {'version':self.VERSION,'registration':deepcopy(self.registration_binding),
                'binding':self.controller.binding.token(),'data':copied,
                'cache':native_cache_manifest(copied),'integration':integration,
                'controller':self.controller.checkpoint(),'sensor':encode(deepcopy(self.sensor_state)),
                'recorder':encode(deepcopy(self.recorder_state)),'tick':int(self.body.tick),
                'drives':np.asarray(self.body.drives,dtype=np.float64).copy()}

    def restored_payload(self,checkpoint):
        """Pure shadow validation before any native cache/API access or assignment."""
        required={'version','registration','binding','data','cache','integration','controller','sensor','recorder','tick','drives'}
        if not isinstance(checkpoint,dict) or set(checkpoint)!=required or checkpoint['version']!=self.VERSION or checkpoint['registration']!=self.registration_binding or checkpoint['binding']!=self.controller.binding.token():
            raise ContractError('native checkpoint identity/schema')
        try:
            state=self.controller.restored_state(checkpoint['controller'])
            sensor=decode(deepcopy(checkpoint['sensor'])); recorder=decode(deepcopy(checkpoint['recorder']))
            tick=checkpoint['tick']; binding=self.controller.binding
            if type(tick) is not int or tick<0 or tick<state['last_tick']: raise ContractError('native checkpoint clock')
            if encode(sensor)!=encode(state['last_observation']): raise ContractError('sensor/controller exact observation')
            packet=validate_recorder(recorder,binding,tick)
            data=checkpoint['data']
            q=array(data.qpos,(binding.nq,),'native checkpoint qpos')
            v=array(data.qvel,(binding.nv,),'native checkpoint qvel')
            if not np.isfinite(data.time) or abs(float(data.time)-tick*DT)>1e-9:
                raise ContractError('native data/tick clock')
            if state['initialized'] and tick==state['last_tick']:
                obs=observation_from_state(state['last_observation'])
                if not np.array_equal(q,obs.qpos) or not np.array_equal(v,obs.qvel):
                    raise ContractError('native/sensor endpoint mismatch')
                validate_observed_packet(obs,packet)
            elif state['initialized'] and tick==state['last_tick']+1:
                obs=state['last_observation']
                if not np.array_equal(packet.qpos,obs['qpos']) or not np.array_equal(packet.qvel,obs['qvel']):
                    raise ContractError('checkpoint consecutive prestate')
            desired_drives=array(checkpoint['drives'],self.body.drives.shape,'checkpoint drives')
            if desired_drives.shape!=(1,2): raise ContractError('native body drive shape')
            drives(desired_drives[0])
            ctrl=array(data.ctrl,(48,),'native checkpoint ctrl')
            action=type(self.controller.action())(state['angles'],state['adhesion'])
            if not np.array_equal(ctrl,self.adapter.action_ctrl(ctrl,action)):
                raise ContractError('native ctrl/controller action')
        except (TypeError,KeyError,ValueError,AttributeError,OverflowError) as exc:
            raise ContractError('invalid native checkpoint payload: '+str(exc)) from exc
        return state,sensor,recorder,desired_drives

    def restore(self,checkpoint):
        state,sensor,recorder,desired_drives=self.restored_payload(checkpoint)
        if native_cache_manifest(checkpoint['data'])!=checkpoint['cache']: raise ContractError('native cache altered')
        mj=_mj(); signature=mj.mjtState.mjSTATE_INTEGRATION
        size=mj.mj_stateSize(self.body.model,signature)
        expected=array(checkpoint['integration'],(size,),'integration')
        staged=mj.MjData(self.body.model); mj.mj_copyData(staged,self.body.model,checkpoint['data'])
        actual=np.empty(size); mj.mj_getState(self.body.model,staged,actual,signature)
        if not np.array_equal(actual,expected) or native_cache_manifest(staged)!=checkpoint['cache']: raise ContractError('staged native restore mismatch')
        backup=mj.MjData(self.body.model); mj.mj_copyData(backup,self.body.model,self.body.data)
        old_state=self.controller.state; old_sensor=self.sensor_state; old_recorder=self.recorder_state
        old_tick=self.body.tick; old_drives=self.body.drives.copy(); old_revision=self.controller._revision
        try:
            mj.mj_copyData(self.body.data,self.body.model,staged)
            self.controller.state=state; self.sensor_state=sensor; self.recorder_state=recorder
            self.body.tick=checkpoint['tick']; self.body.drives[:]=desired_drives
            if native_cache_manifest(self.body.data)!=checkpoint['cache']: raise ContractError('committed native restore mismatch')
            self.controller._revision+=1
        except BaseException:
            mj.mj_copyData(self.body.data,self.body.model,backup)
            self.controller.state=old_state; self.sensor_state=old_sensor; self.recorder_state=old_recorder
            self.body.tick=old_tick; self.body.drives[:]=old_drives; self.controller._revision=old_revision
            raise
