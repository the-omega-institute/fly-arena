"""Explicit intent3 body adapter. Physical admission is deliberately closed.

Factories inspect already compiled metadata only; they never construct a model,
run detached kinematics, or integrate. The authored step path consumes prepared
same-tick AllocationObservations and three-value intents on private controllers.
A qualified mechanical base and a refrozen profile must precede physical use.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import numpy as np
from .rich_bridge_v1 import (DT, PROFILE, GeometryBinding, array, digest, hexhash,
                             intent_parameters, need, admit)

LEGS=('lf','lm','lh','rf','rm','rh')
LINKS=('coxa','trochanterfemur','tibia','tarsus1','tarsus2','tarsus3','tarsus4','tarsus5')
COMPILED_ARRAYS=(
    'jnt_axis','jnt_pos','jnt_type','jnt_limited','jnt_range','jnt_qposadr','jnt_dofadr',
    'actuator_trntype','actuator_trnid','actuator_gear','actuator_gainprm',
    'actuator_biasprm','actuator_forcerange','actuator_forcelimited',
    'actuator_ctrlrange','actuator_ctrllimited','geom_type','geom_dataid',
    'geom_bodyid','geom_contype','geom_conaffinity','geom_friction','mesh_vert',
    'mesh_vertadr','mesh_vertnum','mesh_face','mesh_faceadr','mesh_facenum',
    'body_mass','body_inertia','dof_damping','qpos0')


def _array_hash(value):
    value=np.ascontiguousarray(value)
    h=hashlib.sha256(value.dtype.str.encode())
    h.update(np.asarray(value.shape,dtype=np.int64).tobytes());h.update(value.tobytes())
    return h.hexdigest()


def allocation_model_hash(model):
    """Same static compiled-array hash as the preserved v15 observation sensor."""
    return digest({name:_array_hash(getattr(model,name)) for name in COMPILED_ARRAYS})


def bind_geometry_metadata(model_sha256,subject,geom_names,geom_bodies,segments,obstacle_names,dt,actuator_sha256):
    """Bind every geom of all 48 required leg segments, without CNS inference.

    segments maps source-owned segment names to *all* actual compiled geom names.
    geom_bodies supplies a separate compiled ownership check, including detection
    of omitted geoms. Declared obstacles must belong to the compiled world body,
    as in the preserved Bodies builder. Ground, self and other flies stay excluded.
    """
    names=tuple(geom_names);bodies=tuple(geom_bodies)
    need(len(names)==len(bodies) and len(set(names))==len(names),'compiled geometry rows')
    required={leg+'_'+link for leg in LEGS for link in LINKS}
    need(type(segments) is dict and required<=set(segments),'missing required leg segment')
    lookup={name:i for i,name in enumerate(names)};sides=['excluded']*len(names);seen=set()
    for segment in sorted(required):
        members=segments[segment]
        need(isinstance(members,(tuple,list)) and len(members)>0,'missing required leg geometry')
        for name in members:
            need(name in lookup and name not in seen,'unresolved/duplicate leg geometry')
            i=lookup[name]
            need(bodies[i]==subject+'/'+segment,'compiled leg geometry ownership mismatch')
            seen.add(name);sides[i]=segment[0].upper()
    actual={name for name,owner in zip(names,bodies) if owner in {subject+'/'+s for s in required}}
    need(actual==seen,'required compiled leg geometry omitted')
    need(isinstance(obstacle_names,tuple) and len(set(obstacle_names))==len(obstacle_names),'explicit obstacle names')
    need(all(name in lookup and name.startswith('obstacle-') and '/' not in name for name in obstacle_names),'unknown/nonexternal obstacle')
    need(all(bodies[lookup[name]]=='world' for name in obstacle_names),'compiled obstacle ownership must be world')
    return GeometryBinding(model_sha256,subject,names,tuple(sides),tuple(lookup[n] for n in obstacle_names),actuator_sha256,dt)


def geometry_from_existing(body,subject,obstacle_names,controller):
    """Read an existing FlyGym compiled model and complete source-owned geom map."""
    need(body.model is body.sim.mj_model and body.data is body.sim.mj_data,'shared native body binding')
    model=body.model
    names=tuple(model.geom(i).name for i in range(model.ngeom))
    bodies=tuple(model.body(int(model.geom_bodyid[i])).name for i in range(model.ngeom))
    fly=body.sim.world.fly_lookup[subject]
    segments={segment.name:tuple(g.name for g in geoms) for segment,geoms in fly.bodyseg_to_mjcfgeom.items()}
    actuators=actuators_from_existing(body,subject,controller)
    return bind_geometry_metadata(allocation_model_hash(model),subject,names,bodies,segments,obstacle_names,float(model.opt.timestep),actuators.identity)


@dataclass(frozen=True)
class ActuatorBinding:
    model_sha256: str
    subject: str
    position_ids: tuple
    adhesion_ids: tuple
    dof_names: tuple
    compiled_sha256: str

    def __post_init__(self):
        need(hexhash(self.model_sha256) and hexhash(self.compiled_sha256),'actuator/model hash')
        need(isinstance(self.subject,str) and self.subject,'actuator subject')
        need(type(self.position_ids) is tuple and type(self.adhesion_ids) is tuple and len(self.position_ids)==42 and len(self.adhesion_ids)==6,'42 position and 6 adhesion actuators')
        ids=self.position_ids+self.adhesion_ids
        need(all(type(i) is int and i>=0 for i in ids) and len(set(ids))==48,'actuator ID overlap')
        need(type(self.dof_names) is tuple and len(self.dof_names)==42 and len(set(self.dof_names))==42,'named output DOF order')

    @property
    def identity(self):return digest(self.__dict__)


def actuators_from_existing(body,subject,controller):
    """Read actual transmission addresses, order and enabled compiled limits.

    This method is source-only in this delivery. No controller is constructed.
    The ordinary FlyGym default order helper is used only when the already
    existing controller did not explicitly set output_dof_order.
    """
    from flygym_demo.complex_terrain.common import get_default_locomotion_dof_order
    model=body.model;fly=body.sim.world.fly_lookup[subject]
    kinds=[key for key in fly.jointdof_to_mjcfactuator_by_type if key.name=='POSITION']
    need(len(kinds)==1,'position actuator type')
    kind=kinds[0]
    entries=fly.jointdof_to_mjcfactuator_by_type[kind]
    order=controller.output_dof_order
    if order is None:order=get_default_locomotion_dof_order()
    dofs=tuple(d.name for d in order)
    need(tuple(d.name for d in entries)==dofs,'controller/actual actuator order mismatch')
    pos=tuple(int(i) for i in body.sim._intern_actuatorids_by_type_by_fly[kind][subject])
    adh=tuple(int(i) for i in body.sim._intern_adhesionactuatorids_by_fly[subject])
    need(tuple(fly.get_legs_order())==LEGS,'adhesion leg order mismatch')
    need(all(0<=i<model.nu for i in pos+adh),'compiled actuator range')
    for aid,(dof,element) in zip(pos,entries.items()):
        jid=int(model.actuator_trnid[aid,0])
        need(model.actuator(aid).name==element.name and model.joint(jid).name==fly.jointdof_to_mjcfjoint[dof].name,'actuator name/transmission mismatch')
        need(int(model.jnt_type[jid])==3 and int(model.actuator_trntype[aid])==0,'position transmission must target a hinge')
    rows={name:_array_hash(getattr(model,name)) for name in COMPILED_ARRAYS if name.startswith(('actuator_','jnt_'))}
    rows['names']=digest({'position':[model.actuator(i).name for i in pos],'adhesion':[model.actuator(i).name for i in adh],'dof_names':dofs})
    binding=ActuatorBinding(allocation_model_hash(model),subject,pos,adh,dofs,digest(rows))
    need(controller.model_hash==binding.model_sha256,'controller/model binding mismatch')
    return binding


class RichBodyAdapter:
    """Wrap an existing shared world with a distinct three-axis source path.

    No registration flag, request or fixture can authorize this candidate's
    physical step. The guarded implementation is provided for independent source
    review and must be refrozen with a qualified mechanical base before use.
    """
    def __init__(self,body,controllers,geometry_bindings,actuator_bindings):
        need(len(body.names)>0 and len(body.names)==len(controllers)==len(geometry_bindings)==len(actuator_bindings),'body subject batch')
        need(len(set(body.names))==len(body.names) and len({id(c) for c in controllers})==len(controllers),'shared subject/controller')
        need(float(body.model.opt.timestep)==DT,'body timestep')
        for name,controller,g,a in zip(body.names,controllers,geometry_bindings,actuator_bindings):
            need(type(g) is GeometryBinding and type(a) is ActuatorBinding and g.subject==a.subject==name,'body binding subject')
            need(g.model_sha256==a.model_sha256==controller.model_hash,'body model identity')
            need(g.actuator_sha256==a.identity,'geometry/actuator binding mismatch')
        all_ids=sum((a.position_ids+a.adhesion_ids for a in actuator_bindings),())
        need(len(set(all_ids))==len(all_ids),'shared subject actuators')
        self.body=body;self.controllers=list(controllers)
        self.geometry=tuple(geometry_bindings);self.actuators=tuple(actuator_bindings)
        self.binding=digest({'geometry':[g.identity for g in self.geometry],'actuators':[a.identity for a in self.actuators]})
        self.last_intents=np.tile([0.,0.,1.],(len(controllers),1))

    def _propose_actions(self,intents,observations):
        from .rich_bridge_v1_controller import RichBridgeController
        from .cadence_v15 import AllocationObservation
        values=array(intents,(len(self.controllers),3))
        need(len(observations)==len(self.controllers),'all-subject observation snapshot')
        # Freeze and validate ALL observations/intent domains before any advance.
        snapshots=deepcopy(tuple(observations));shadows=[]
        for c,u,obs,g in zip(self.controllers,values,snapshots,self.geometry):
            need(type(c) is RichBridgeController and type(obs) is AllocationObservation,'explicit rich controller/observation required')
            intent_parameters(u,c._base_intrinsic_freqs,c._base_coupling);obs.validate()
            need(obs.tick==self.body.tick and obs.model_hash==g.model_sha256,'synchronous prestate tick/model')
            need(np.array_equal(obs.lower,c.compiled_lower) and np.array_equal(obs.upper,c.compiled_upper),'compiled allocation intervals')
            shadows.append(deepcopy(c))
        actions=[c.step(u,obs) for c,u,obs in zip(shadows,values,snapshots)]
        ctrl=self.body.data.ctrl.copy()
        for action,a in zip(actions,self.actuators):
            targets=array(action.joint_angles,(42,))
            adhesion=np.asarray(action.adhesion_onoff)
            need(adhesion.dtype==np.bool_ and adhesion.shape==(6,),'adhesion action')
            ctrl[list(a.position_ids)]=targets;ctrl[list(a.adhesion_ids)]=adhesion
        need(np.isfinite(ctrl).all(),'finite proposed controls')
        return shadows,ctrl,values

    def step(self,intents,observations):
        admit({'profile':PROFILE})  # Always refuses; no physical trial admission.
        # Executable realization for later qualified/refrozen source: all private
        # actions first, then one shared-world step. No call to legacy Bodies.step.
        shadows,ctrl,values=self._propose_actions(intents,observations)
        self.body.data.ctrl[:]=ctrl
        self.controllers=shadows;self.body.controllers=shadows
        self.last_intents=values
        self.body.sim.step()
        self.body.tick+=1

    def observe_completed_contacts(self,states,source_tick):
        """Copy current solver cache, tagged with the actual solve prestate tick.

        Called immediately after the authoritative shared step, before another
        solve/forward can replace the cache. No contact inference from endpoint
        geometry, and no kinematics or simulation calls occur here.
        """
        need(type(source_tick) is int and self.body.tick==source_tick+1,'completed solve provenance')
        need(len(states)==len(self.geometry),'contact subject batch')
        rows=tuple((int(c.geom1),int(c.geom2),float(c.dist)) for c in self.body.data.contact)
        proposed=[]
        for state,g in zip(states,self.geometry):
            need(state.geometry==g,'contact geometry binding')
            latch=deepcopy(state.latch);latch.observe(source_tick,g.model_sha256,rows);proposed.append(latch)
        for state,latch in zip(states,proposed):state.latch=latch

    def checkpoint(self):
        return {'schema':'rich-body-owned-state/v1','binding':self.binding,
                'tick':self.body.tick,'held_intents':self.last_intents.copy(),
                'controllers':tuple(c.checkpoint() for c in self.controllers),
                'full_restore_supported':False}

    def restore(self,checkpoint):
        raise ValueError('native body restore unavailable: integration, solver cache, RNG, controller and neural bindings must validate and commit atomically')
