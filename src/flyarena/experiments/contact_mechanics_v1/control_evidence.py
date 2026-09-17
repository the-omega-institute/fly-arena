"""Pure, explicit numeric evidence of v16 state; not its object checkpoint format."""
from dataclasses import fields,is_dataclass
from enum import Enum
import numpy as np
from ..contact_v1.contracts import encode
from .io import digest

CPG_FIELDS=('timestep','num_cpgs','intrinsic_freqs','intrinsic_amps','coupling_weights',
 'phase_biases','convergence_coefs','curr_phases','curr_magnitudes')
REFERENCE_FIELDS=('_length','_timestep','duration','neutral_pos','swing_period')
CONTROL_REQUIRED=('timestep','legs','retraction_correction','stumbling_correction',
 'retraction_persistence_counter','last_info','_base_intrinsic_freqs','_base_intrinsic_amps',
 '_base_coupling','_last_angles','_last_adhesion','release_start','release_end',
 'last_allocation','last_allocation_diagnostics','last_relaxation_diagnostics',
 'last_observation_tick','observation_version','model_hash','compiled_lower','compiled_upper',
 'last_native_template','last_clearance','last_trigger','last_minimum_geom','last_minimum_vertex',
 'stumbling_force_threshold','retraction_height_threshold','retraction_rates','stumbling_rates',
 'max_correction','swing_extension','retraction_persistence_steps',
 'retraction_persistence_initiation_threshold','enable_adhesion')

def descriptor(value):
    if isinstance(value,Enum):return {'enum':type(value).__qualname__,'value':descriptor(value.value)}
    if is_dataclass(value):return {'type':type(value).__qualname__,'fields':{f.name:descriptor(getattr(value,f.name)) for f in fields(value)}}
    if isinstance(value,(list,tuple)):return [descriptor(v) for v in value]
    return encode(value)

def control_snapshot(controller,reference_identity):
    """Complete mutable numeric state/configuration plus immutable spline identity.

    Inspect numeric attributes only; never call CPG, spline, checkpoint or physics.
    Unknown object-valued controller fields fail rather than silently disappear.
    """
    if not isinstance(reference_identity,dict) or set(reference_identity)!={'asset_hash','model_digest','input_hash'}:raise ValueError('control reference identity')
    if any(not isinstance(v,str) or len(v)!=64 for v in reference_identity.values()):raise ValueError('control reference digest')
    cpg=controller.cpg_network;steps=controller.preprogrammed_steps
    if set(vars(cpg))!=set(CPG_FIELDS)|{'random_state'}:raise ValueError('unregistered CPG state fields')
    cpg_state={name:getattr(cpg,name) for name in CPG_FIELDS};cpg_state['rng']=cpg.random_state.get_state()
    state=vars(controller)
    if not (set(CONTROL_REQUIRED)|{'cpg_network','preprogrammed_steps','output_dof_order'})<=set(state):raise ValueError('incomplete v16 evidence state')
    numeric={name:encode(value) for name,value in state.items() if name not in ('cpg_network','preprogrammed_steps','output_dof_order')}
    reference={name:encode(getattr(steps,name)) for name in REFERENCE_FIELDS}
    reference.update(legs=descriptor(steps.legs),dofs_per_leg=descriptor(steps.dofs_per_leg))
    if set(vars(steps))!=set(REFERENCE_FIELDS)|{'_psi_funcs'}:raise ValueError('unregistered native reference state')
    if set(steps._psi_funcs)!=set(steps.legs):raise ValueError('incomplete native spline set')
    reference['splines']={leg:{name:encode(getattr(spline,name)) for name in ('x','c','axis','extrapolate')} for leg,spline in steps._psi_funcs.items()}
    return {'schema':'contact-mechanics-v16-numeric-state/v1','controller':numeric,'cpg':encode(cpg_state),
      'output_dof_order':descriptor(controller.output_dof_order),'reference':reference,
      'reference_sha256':digest(reference),'reference_identity':reference_identity,'portable_native_restore':False}
