"""Engineered whole-foot retraction trigger; unchanged native realization law."""
from copy import deepcopy
from dataclasses import dataclass
import numpy as np
from flygym_demo.complex_terrain.common import LocomotionAction, dof_spec_to_jointdof, get_default_locomotion_dof_order
from flygym_demo.complex_terrain.hybrid_controller import (
    HybridControllerObservation, _CORRECTION_VECTORS, _RIGHT_LEG_CORRECTION_SIGN, _step_phase_gain,
)
from .cadence_v12 import ExcursionHybridController
from .cadence_v10 import SILENCE

PROFILE = 'whole-foot-retraction-feedback-v14'
CONTROL = 'source-native-excursion-v12'
STATE_VERSION = 'cadence-controller-state/v14'
OBSERVATION_VERSION = 'whole-foot-observation/v14'


@dataclass(frozen=True)
class ClearanceObservation:
    native: HybridControllerObservation
    clearance: np.ndarray
    minimum_geom: np.ndarray
    minimum_vertex: np.ndarray
    version: str = OBSERVATION_VERSION

    def validate(self):
        if self.version != OBSERVATION_VERSION or not isinstance(self.native,HybridControllerObservation):
            raise ValueError('unsupported clearance observation')
        for value, shape in ((self.clearance,(6,)), (self.native.tarsus5_z,(6,)),
                             (self.native.stumbling_contact_forces,(6,3,3)), (self.native.fly_heading,(3,))):
            a = np.asarray(value)
            if a.shape != shape or a.dtype.kind not in 'fi' or not np.isfinite(a).all():
                raise ValueError('malformed/nonfinite clearance/native observation')
        if np.asarray(self.native.thorax_z).shape!=() or not np.isfinite(self.native.thorax_z):
            raise ValueError('nonfinite thorax height')
        for value in (self.minimum_geom,self.minimum_vertex):
            a=np.asarray(value)
            if a.shape!=(6,) or a.dtype.kind not in 'iu' or np.any(a<0):
                raise ValueError('malformed minimum vertex identity')


class ClearanceHybridController(ExcursionHybridController):
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
            raise ValueError('native source constants differ from approved v14 contract')

    def reset(self, **kwargs):
        super().reset(**kwargs)
        self.last_clearance=np.zeros(6)
        self.last_trigger=np.zeros(6,dtype=bool)
        self.last_minimum_geom=np.full(6,-1,dtype=np.int64)
        self.last_minimum_vertex=np.full(6,-1,dtype=np.int64)

    def step(self, descending_signal, obs):
        u=np.asarray(descending_signal,dtype=float)
        if u.shape!=(2,) or not np.isfinite(u).all() or np.any(u<0):
            raise ValueError('v14 requires two finite nonnegative v4 outputs')
        common=float(u.mean());asymmetry=float((u[1]-u[0])/(2*common)) if common else 0.
        if common>.4+1e-12 or abs(asymmetry)>.8+1e-12:
            raise ValueError('outside registered v4 output domain')
        if common<=SILENCE:
            return LocomotionAction(self._last_angles.copy(),self._last_adhesion.copy())
        if not isinstance(obs,ClearanceObservation):
            raise ValueError('v14 requires a versioned whole-foot observation')
        obs.validate()  # Atomic rejection before any controller, RNG or action mutation.
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
        angles={};adhesion=[];net=np.zeros(6)
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
            leg_angles=leg_angles+correction*gain*vector
            net[index]=correction*gain
            for j,spec in enumerate(self.preprogrammed_steps.dofs_per_leg):
                angles[dof_spec_to_jointdof(leg,spec)]=leg_angles[j]
            adhesion.append(self._get_adhesion_onoff(leg,phase) if self.enable_adhesion else False)
        order=self.output_dof_order if self.output_dof_order is not None else get_default_locomotion_dof_order()
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
            raise ValueError('unsupported/incomplete v14 checkpoint')
        self.__dict__=deepcopy(checkpoint['state'])
