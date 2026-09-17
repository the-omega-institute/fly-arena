"""Unqualified explicit intent3 controller; source-only, no runtime registration.

The v15 advancement is copied verbatim except its excursion argument and one
amplitude assignment. No extra CPG advance, phase injection or global patch.
Importing this module loads the physical controller dependencies; contract tests
inspect it as source and never import or instantiate it.
"""
from copy import deepcopy, copy
import numpy as np
from flygym_demo.complex_terrain.common import LocomotionAction, dof_spec_to_jointdof, get_default_locomotion_dof_order
from flygym_demo.complex_terrain.hybrid_controller import (
    _CORRECTION_VECTORS, _RIGHT_LEG_CORRECTION_SIGN, _step_phase_gain,
)
from .cadence_v15 import AllocationHybridController, AllocationObservation, normal_allocation
from .cadence_v10 import SILENCE
from .rich_bridge_v1 import array, intent_parameters


class RichBridgeController(AllocationHybridController):
    def step(self, intent, obs):
        # Explicit three-axis interface: never forwarded to the legacy step2.
        u=array(intent,(3,))
        intent_parameters(u,self._base_intrinsic_freqs,self._base_coupling)
        common,asymmetry,excursion=map(float,u)
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
        action=shadow._advance(common,asymmetry,excursion,obs)
        if not all(np.isfinite(x).all() for x in (action.joint_angles,shadow.last_allocation,shadow.last_allocation_diagnostics,shadow.last_native_template)):
            raise ValueError('nonfinite proposed action')
        self.__dict__=shadow.__dict__
        return action

    def _advance(self,common,asymmetry,excursion,obs):
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
        self.cpg_network.intrinsic_amps=excursion*np.repeat([1-asymmetry,1+asymmetry],3)
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
        # Complete controller-owned state, including CPG/RNG/native reflex state.
        # This alone cannot restore the native physical engine or neural model.
        return {'schema':'rich-bridge-controller-state/v1',
                'model_hash':self.model_hash,'state':deepcopy(self.__dict__)}

    def restore(self,checkpoint):
        # The inherited v15 restore validates keys only. Do not accept it as an
        # atomic full restoration contract for this new profile.
        raise ValueError('controller restore unavailable until qualified native-body atomic restore is bound')
