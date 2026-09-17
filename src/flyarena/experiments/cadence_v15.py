"""Registered minimum-vertex normal retraction allocation; engineering only."""
from copy import deepcopy, copy
from dataclasses import dataclass
import numpy as np
from flygym_demo.complex_terrain.common import LocomotionAction, dof_spec_to_jointdof, get_default_locomotion_dof_order
from flygym_demo.complex_terrain.hybrid_controller import (
    HybridControllerObservation, _CORRECTION_VECTORS, _RIGHT_LEG_CORRECTION_SIGN, _step_phase_gain,
)
from .cadence_v12 import ExcursionHybridController
from .cadence_v10 import SILENCE

PROFILE = 'minimum-vertex-normal-retraction-v15'
CONTROL = 'whole-foot-retraction-feedback-v14'
STATE_VERSION = 'cadence-controller-state/v15'
OBSERVATION_VERSION = 'whole-foot-observation/v15'


@dataclass(frozen=True)
class AllocationObservation:
    native: HybridControllerObservation
    clearance: np.ndarray
    minimum_geom: np.ndarray
    minimum_vertex: np.ndarray
    angles: np.ndarray
    jacobian: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    tick: int
    model_hash: str
    version: str = OBSERVATION_VERSION

    def validate(self):
        if self.version != OBSERVATION_VERSION or not isinstance(self.native,HybridControllerObservation):
            raise ValueError('unsupported clearance observation')
        for value, shape in ((self.clearance,(6,)), (self.native.tarsus5_z,(6,)),
                             (self.native.stumbling_contact_forces,(6,3,3)), (self.native.fly_heading,(3,)), (self.angles,(6,7)), (self.jacobian,(6,3,7))):
            a = np.asarray(value)
            if a.shape != shape or a.dtype.kind not in 'fi' or not np.isfinite(a).all():
                raise ValueError('malformed/nonfinite clearance/native observation')
        if np.asarray(self.native.thorax_z).shape!=() or not np.isfinite(self.native.thorax_z):
            raise ValueError('nonfinite thorax height')
        for value in (self.minimum_geom,self.minimum_vertex):
            a=np.asarray(value)
            if a.shape!=(6,) or a.dtype.kind not in 'iu' or np.any(a<0):
                raise ValueError('malformed minimum vertex identity')
        for value in (self.lower,self.upper):
            a=np.asarray(value)
            if a.shape!=(6,7) or a.dtype.kind!='f' or np.isnan(a).any():
                raise ValueError('malformed compiled intervals')
        if np.any(self.lower>self.upper) or np.isposinf(self.lower).any() or np.isneginf(self.upper).any():
            raise ValueError('empty compiled interval')
        if type(self.tick) is not int or self.tick<0 or not isinstance(self.model_hash,str) or len(self.model_hash)!=64:
            raise ValueError('invalid prestate identity')


def normal_allocation(J, h, q, q0, lower, upper, budget):
    """One bounded angular step, with no change to native scalar integration."""
    if (not all(np.isfinite(x).all() for x in (J,q,q0)) or not np.isfinite([h,budget]).all()
            or budget<0 or np.any(q0<lower) or np.any(q0>upper)):
        raise ValueError('infeasible/nonfinite native target')
    _,singular,Vh=np.linalg.svd(J[:2],full_matrices=True)
    tau=64*np.finfo(np.float64).eps*max(1.,float(np.linalg.norm(J,2)))
    rank=int(np.count_nonzero(singular>tau));N=Vh[rank:].T
    w=N@(N.T@J[2]);authority=float(np.linalg.norm(w))
    h0=float(h+J[2]@(q0-q))
    if not np.isfinite([authority,h0,tau]).all():raise ValueError('nonfinite allocation calculation')
    if authority<=tau:
        if h0<.05:
            raise ValueError('infeasible normal realization: rank/authority')
        return np.zeros(7),np.array([h0,authority,0.,budget,-1.,0.,rank,0.])
    direction=w/authority
    requested=max(0.,(.05-h0)/authority)
    limits=np.full(7,np.inf)
    positive=direction>0;negative=direction<0
    limits[positive]=(upper[positive]-q0[positive])/direction[positive]
    limits[negative]=(lower[negative]-q0[negative])/direction[negative]
    limit=float(limits.min());distance=min(requested,budget,limit)
    offset=distance*direction
    residual=max(0.,.05-(h0+authority*distance))
    flags=int(distance<requested and distance==budget)+2*int(distance<requested and distance==limit)
    return offset,np.array([h0,authority,requested,budget,limit if np.isfinite(limit) else -1.,residual,rank,flags])


class AllocationHybridController(ExcursionHybridController):
    def __post_init__(self):
        super().__post_init__()
        self.release_start = np.array([self.preprogrammed_steps.swing_period[leg][0] for leg in self.legs])
        self.release_end = np.array([self.preprogrammed_steps.swing_period[leg][1]+self.swing_extension for leg in self.legs])
        if (not np.array_equal(self.release_start,np.zeros(6)) or np.any(self.release_end<=0)
                or np.any(self.release_end>=2*np.pi) or self.retraction_height_threshold!=.05
                or self.retraction_rates!=(800.,700.) or self.stumbling_rates!=(2200.,1800.)
                or self.max_correction!=80 or self.retraction_persistence_steps!=20
                or self.retraction_persistence_initiation_threshold!=20 or self.swing_extension!=np.pi/4
                or not np.array_equal(self._base_intrinsic_freqs,np.full(6,12.))
                or not np.array_equal(self.cpg_network.convergence_coefs,np.full(6,20.))):
            raise ValueError('native source constants differ from approved v15 contract')

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.last_allocation=np.zeros((6,7))
        self.last_allocation_diagnostics=np.zeros((6,8))
        self.last_observation_tick=-1
        self.observation_version=OBSERVATION_VERSION
        self.model_hash=''
        self.compiled_lower=np.full((6,7),-np.inf)
        self.compiled_upper=np.full((6,7),np.inf)
        self.last_native_template=self._last_angles.copy()
        self.last_clearance=np.zeros(6)
        self.last_trigger=np.zeros(6,dtype=bool)
        self.last_minimum_geom=np.full(6,-1,dtype=np.int64)
        self.last_minimum_vertex=np.full(6,-1,dtype=np.int64)

    def step(self, descending_signal, obs):
        u=np.asarray(descending_signal,dtype=float)
        if u.shape!=(2,) or not np.isfinite(u).all() or np.any(u<0):
            raise ValueError('v15 requires two finite nonnegative v4 outputs')
        common=float(u.mean());asymmetry=float((u[1]-u[0])/(2*common)) if common else 0.
        if common>.4+1e-12 or abs(asymmetry)>.8+1e-12:
            raise ValueError('outside registered v4 output domain')
        if common<=SILENCE:
            return LocomotionAction(self._last_angles.copy(),self._last_adhesion.copy())
        if not isinstance(obs,AllocationObservation):
            raise ValueError('v15 requires a versioned whole-foot observation')
        obs.validate()  # Atomic rejection before any controller, RNG or action mutation.
        if obs.model_hash!=self.model_hash or obs.tick<=self.last_observation_tick:
            raise ValueError('observation model/tick identity mismatch')
        if not np.array_equal(obs.lower,self.compiled_lower) or not np.array_equal(obs.upper,self.compiled_upper):
            raise ValueError('observation compiled ranges mismatch')
        # Only these fields are mutated by native next-state equations. Asset
        # splines and configuration remain shared read-only; state is private.
        shadow=copy(self)
        shadow.__dict__={key:(value.copy() if isinstance(value,np.ndarray) else value) for key,value in self.__dict__.items()}
        shadow.cpg_network=deepcopy(self.cpg_network)
        shadow.last_info=deepcopy(self.last_info)
        action=shadow._advance(common,asymmetry,obs)
        if not all(np.isfinite(x).all() for x in (action.joint_angles,shadow.last_allocation,shadow.last_allocation_diagnostics,shadow.last_native_template)):
            raise ValueError('nonfinite proposed action')
        self.__dict__=shadow.__dict__
        return action

    def _advance(self,common,asymmetry,obs):
        self.last_observation_tick=obs.tick
        self.last_allocation=np.zeros((6,7))
        self.last_allocation_diagnostics=np.zeros((6,8))
        wrapped=self.cpg_network.curr_phases%(2*np.pi)
        mask=(wrapped>self.release_start)&(wrapped<self.release_end)&(np.asarray(obs.clearance)<self.retraction_height_threshold)
        self.last_clearance=np.asarray(obs.clearance,dtype=float).copy()
        self.last_trigger=mask.copy()
        self.last_minimum_geom=np.asarray(obs.minimum_geom,dtype=np.int64).copy()
        self.last_minimum_vertex=np.asarray(obs.minimum_vertex,dtype=np.int64).copy()
        self.cpg_network.intrinsic_freqs=self._base_intrinsic_freqs*(common/.6)
        self.cpg_network.coupling_weights=self._base_coupling*(common/.6)
        self.cpg_network.intrinsic_amps=np.repeat([1-asymmetry,1+asymmetry],3)
        # Native ordering: initiate persistence from OLD scalar, increment/expire
        # counters, observe stumbling, advance CPG, then update both reflex scalars.
        self.retraction_persistence_counter[mask & (self.retraction_correction>self.retraction_persistence_initiation_threshold)]=1
        self._update_persistence_counter()
        stumbling_mask=self._get_stumbling_mask(obs.native)
        self.cpg_network.step()
        angles={};native_angles={};adhesion=[];net=np.zeros(6)
        for index,leg in enumerate(self.legs):
            self._update_retraction_correction(index,index if mask[index] else None)
            self._update_stumbling_correction(index,stumbling_mask[index])
            if self.retraction_correction[index]>0:
                correction=self.retraction_correction[index]
                self.stumbling_correction[index]=0
            else:
                correction=self.stumbling_correction[index]
            phase=self.cpg_network.curr_phases[index]
            magnitude=self.cpg_network.curr_magnitudes[index]
            leg_angles=self.preprogrammed_steps.get_joint_angles(leg,phase,magnitude)
            correction=np.clip(correction,0,self.max_correction)
            gain=_step_phase_gain(phase%(2*np.pi),self.preprogrammed_steps.swing_period[leg],self.swing_extension)
            vector=_CORRECTION_VECTORS[leg[1]]
            if leg.startswith('r'):
                vector=vector*_RIGHT_LEG_CORRECTION_SIGN
            for j,spec in enumerate(self.preprogrammed_steps.dofs_per_leg):
                native_angles[dof_spec_to_jointdof(leg,spec)]=leg_angles[j]
            if np.any(leg_angles<obs.lower[index]) or np.any(leg_angles>obs.upper[index]):
                raise ValueError('native template outside enabled compiled intervals')
            if self.retraction_correction[index]>0:
                wrapped_phase=phase%(2*np.pi)
                if self.release_start[index]<wrapped_phase<self.release_end[index]:
                    budget=correction*max(gain,0.)*float(np.linalg.norm(vector))
                    offset,diagnostic=normal_allocation(obs.jacobian[index],obs.clearance[index],
                        obs.angles[index],leg_angles,obs.lower[index],obs.upper[index],budget)
                    self.last_allocation[index]=offset
                    self.last_allocation_diagnostics[index]=diagnostic
                    leg_angles=leg_angles+offset
            else:
                leg_angles=leg_angles+correction*gain*vector
                net[index]=correction*gain
            for j,spec in enumerate(self.preprogrammed_steps.dofs_per_leg):
                angles[dof_spec_to_jointdof(leg,spec)]=leg_angles[j]
            adhesion.append(self._get_adhesion_onoff(leg,phase) if self.enable_adhesion else False)
        order=self.output_dof_order if self.output_dof_order is not None else get_default_locomotion_dof_order()
        self.last_native_template=np.array([native_angles[dof] for dof in order])
        self._last_angles=np.array([angles[dof] for dof in order])
        self._last_adhesion=np.asarray(adhesion,dtype=bool)
        self.last_info={'net_corrections':net,'retraction_correction':self.retraction_correction.copy(),
                       'stumbling_correction':self.stumbling_correction.copy(),'stumbling_mask':stumbling_mask.copy(),
                       'retraction_mask':mask.copy()}
        return LocomotionAction(self._last_angles.copy(),self._last_adhesion.copy())

    def checkpoint(self):
        return {'version':STATE_VERSION,'state':deepcopy(self.__dict__)}

    def restore(self,checkpoint):
        if set(checkpoint)!={'version','state'} or checkpoint['version']!=STATE_VERSION or set(checkpoint['state'])!=set(self.__dict__):
            raise ValueError('unsupported/incomplete v15 checkpoint')
        self.__dict__=deepcopy(checkpoint['state'])
