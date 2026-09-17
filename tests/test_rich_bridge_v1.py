"""Tiny authored contracts only: never import/advance a scientific engine.

Controller consumption is inspected as source; intent_parameters is algebra.
No neural response, controller step, model construction, kinematics or physical
trajectory is exercised by this suite. The 100 contact ticks are authored rows.
"""
import ast
from copy import deepcopy
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
from types import SimpleNamespace

# Install before importing candidate code, not merely before individual tests.
FORBIDDEN=('mujoco','flygym','flygym_demo','torch','jax','numba',
           'flyarena.neural','flyarena.backend','flyarena.connectome',
           'flyarena.body','flyarena.experiments.cadence_',
           'flyarena.experiments.mechanical_',
           'flyarena.experiments.rich_bridge_v1_controller')
class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(fullname.startswith(prefix) for prefix in FORBIDDEN):
            raise AssertionError('forbidden scientific import: '+fullname)
sys.meta_path.insert(0,NoScience())
assert not any(any(name.startswith(prefix) for prefix in FORBIDDEN) for name in sys.modules)

import numpy as np
import pytest
from flyarena.experiments import rich_bridge_v1 as r
from flyarena.experiments import rich_bridge_v1_body as b
from flyarena.experiments.sensor import encode_odor

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/flyarena/experiments'
H='a'*64


def state(subject='fly-a'):
    mapping=r.NeuralMap(9,((0,),(1,),(2,),(3,),(4,5),(6,)),H)
    names=('fly-a/lf_tibia','fly-a/rf_tibia','obstacle-0','ground_plane','fly-c/lf_tibia','fly-c/rf_tibia','fly-other/lf_tibia','fly-a/c_thorax','fly-c/c_thorax')
    sides=tuple('L' if n==subject+'/lf_tibia' else 'R' if n==subject+'/rf_tibia' else 'excluded' for n in names)
    geometry=r.GeometryBinding(H,subject,names,sides,(2,),'b'*64)
    decoder=r.FrozenDecoder((4,5),np.zeros((1,2)),np.array([[.6,.8]]),1.,'c'*64)
    return r.BridgeState(mapping,geometry,decoder,'d'*64)


def commit(s,rates=None,odor=(0.,0.),off=False):
    if rates is None:rates=np.zeros(9)
    tick=s.boundary_tick+100
    frames,rs=r.snapshot_boundary([s],tick,[np.array(odor)],[rates])
    external=np.full(9,9.)
    result=r.commit_boundary([s],frames,rs,[external],off)
    return external,result


def contacts(s,rows=None):
    for tick in range(s.latch.next_tick,s.latch.start_tick+100):
        s.latch.observe(tick,H,() if rows is None else rows.get(tick,()))


def checkpoint_values(s):
    """Complete value/type comparison independent of object memoization."""
    def normalize(value):
        if isinstance(value,np.ndarray):return ('array',value.dtype.str,value.shape,value.tobytes())
        if isinstance(value,dict):return ('dict',tuple((k,normalize(v)) for k,v in sorted(value.items())))
        if isinstance(value,(list,tuple)):return (type(value).__name__,tuple(normalize(v) for v in value))
        return (type(value).__name__,value)
    return normalize(s.checkpoint())


@pytest.fixture(autouse=True)
def no_science_loaded():
    yield
    assert not any(any(name.startswith(prefix) for prefix in FORBIDDEN) for name in sys.modules)


def test_canonical_exact_membership_and_seal():
    mapping=r.load_maps();raw=(SOURCE/'rich_bridge_v1_maps.json').read_bytes();value=json.loads(raw)
    from flyarena.experiments.rich_bridge_v1_seals import MAP_SHA256
    assert hashlib.sha256(raw).hexdigest()==MAP_SHA256
    assert list(map(len,mapping.populations))==[884,1344,1264,1294,1314,49]
    assert value['q_type_counts']=={'Ti flexor MN':37,'Ti extensor MN':12}
    assert value['q_side_counts']=={'L':25,'R':24}
    expected=['80868cc78449562ea8591d60d6bb3d332048fd007b9dbc127ffa12510e39f855','7f6ed3ff72c87d3ff7e890d229f6924b637b9a792b4e58562743fbbb7096465b','fe540a903abe0e6b7439241a0a6b2b512cca015bd9e5f120299ebfeb0a0c3af7']
    for index,want in zip((2,3,5),expected):
        pop=value['populations'][index]
        assert hashlib.sha256(json.dumps([int(x) for x in pop['body_ids']],separators=(',',':')).encode()).hexdigest()==want
        assert [int(x) for x in pop['body_ids']]==sorted(map(int,pop['body_ids']))
    assert value['populations'][2]['selector']=={'superclass':'vnc_sensory','class':'mechanosensory_tactile','side':'L'}
    assert value['populations'][3]['selector']['side']=='R'


@pytest.mark.parametrize('fault',['id','side','order','dtype'])
def test_tiny_layout_rejects_misbound_identity(fault):
    ids=np.array([10,20,30],dtype=np.int64);sides=np.array([1,-1,0],dtype=np.int8)
    artifact={'neuron_count':3,'populations':[{'indices':[0,1],'body_ids':['10','20'],'selector':{}} ,{'indices':[0],'body_ids':['10'],'selector':{'side':'L'}}]}
    r.validate_layout(ids,sides,artifact)
    if fault=='id':ids[0]=11
    elif fault=='side':sides[0]=-1
    elif fault=='order':ids=ids[::-1]
    else:ids=ids.astype(np.float64)
    with pytest.raises(ValueError):r.validate_layout(ids,sides,artifact)


def test_canonical_layout_hash_rejection(tmp_path):
    (tmp_path/'ids.npy').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='hash'):r.bind_canonical_neurons(tmp_path)


def test_decoder_hash_and_neuron_order_rejection(tmp_path):
    path=tmp_path/'fake.npz';path.write_bytes(b'authored-invalid-asset')
    with pytest.raises(ValueError,match='changed'):r.FrozenDecoder.from_asset(path,H)
    s=state()
    bad=r.FrozenDecoder((5,4),np.zeros((1,2)),np.ones((1,2)),1.,H)
    with pytest.raises(ValueError,match='binding'):r.BridgeState(s.mapping,s.geometry,bad,H)
    with pytest.raises(ValueError):s.decoder.weights.flags.writeable=True
    with pytest.raises(AttributeError):s.decoder.bandwidth=2.


def test_input_order_distinctness_zeroing_and_original_odor():
    s=state();external,_=commit(s,odor=(.1,.4))
    assert np.array_equal(external[:2],48*encode_odor(.1,.4))
    assert not external[2:].any()
    contacts(s,{17:[(0,3,-.1),(0,4,-.1),(0,2,-.01)],18:[(1,2,.01)]})
    frame=s.latch.frame(100,np.array([.1,.4]),s.binding)
    assert frame['channels']==r.CHANNELS and frame['values'][2:]==(1.,0.)
    assert frame['events']==((17,2,0,2,-.01),)
    external,_=commit(s,odor=(.1,.4))
    assert external[2]==48 and external[3]==0 and not external[7:].any()
    contacts(s,{151:[(1,2,-.01)]});external,_=commit(s)
    assert external[2]==0 and external[3]==48 and not external[:2].any()
    contacts(s);external,_=commit(s)
    assert not external.any()  # No tonic and no retained external current.


@pytest.mark.parametrize('fault',['missing','extra','channels','tick','model','geometry','binding','touch','events','nonfinite','string','interval'])
def test_invalid_frame_atomicity(fault):
    s=state();frame=s.latch.frame(0,np.array([0.,0.]),s.binding)
    before=checkpoint_values(s);external=np.full(9,7.)
    if fault=='missing':del frame['values']
    elif fault=='extra':frame['vision']=1.
    elif fault=='channels':frame['channels']=r.CHANNELS[::-1]
    elif fault=='tick':frame['tick']=100
    elif fault in ('model','geometry','binding'):frame[fault]='f'*64
    elif fault=='touch':frame['values']=(0.,0.,1.,0.)
    elif fault=='events':frame['events']=((0,0,0,2,-.1),)
    elif fault=='nonfinite':frame['values']=(np.nan,0.,0.,0.)
    elif fault=='string':frame['values']=('0',0.,0.,0.)
    else:frame['contact_start']=False
    with pytest.raises(ValueError):r.commit_boundary([s],[frame],[np.zeros(9)],[external])
    assert checkpoint_values(s)==before and np.array_equal(external,np.full(9,7.))


def test_synchronous_all_subject_invalid_batch_is_atomic():
    a=state('fly-a');c=state('fly-c')
    frames,rates=r.snapshot_boundary([a,c],0,[np.array([.2,.1]),np.array([.1,.2])],[np.ones(9),np.ones(9)*2])
    before=[checkpoint_values(a),checkpoint_values(c)];external=[np.ones(9)*7,np.ones(9)*8]
    frames[1]['binding']='f'*64
    with pytest.raises(ValueError):r.commit_boundary([a,c],frames,rates,external)
    assert [checkpoint_values(a),checkpoint_values(c)]==before
    assert np.array_equal(external[0],np.ones(9)*7) and np.array_equal(external[1],np.ones(9)*8)


def test_snapshot_precedes_input_commit_and_no_array_aliases():
    a=state('fly-a');c=state('fly-c');original=[np.arange(9,dtype=float),np.arange(9,dtype=float)*2]
    odors=[np.array([.2,.1]),np.array([.1,.2])]
    frames,rates=r.snapshot_boundary([a,c],0,odors,original)
    original[0][:]=0;odors[0][:]=0
    assert np.array_equal(rates[0],np.arange(9,dtype=float))
    external=[np.zeros(9),np.zeros(9)];intent=r.commit_boundary([a,c],frames,rates,external)
    intent[:]=0;external[0][:]=0;frames[0]['values']=(0.,0.,0.,0.)
    assert a.intent[0]>0 and a.held_current[0]>0 and c.intent[0]>0
    assert not np.shares_memory(a.intent,c.intent)


def test_external_rate_alias_rejected_before_writes():
    s=state();f=s.latch.frame(0,np.zeros(2),s.binding);rates=np.zeros(9)
    with pytest.raises(ValueError,match='aliases'):r.commit_boundary([s],[f],[rates],[rates])
    assert s.boundary_tick==-100


def test_contact_tick_identity_and_atomic_rows():
    s=state();commit(s);before=checkpoint_values(s)
    with pytest.raises(ValueError):s.latch.observe(1,H,())
    with pytest.raises(ValueError):s.latch.observe(0,'e'*64,())
    with pytest.raises(ValueError):s.latch.observe(0,H,[(0,2,-.1),(99,2,0.)])
    assert checkpoint_values(s)==before
    s.latch.observe(0,H,())
    with pytest.raises(ValueError):s.latch.frame(100,np.zeros(2),s.binding)
    contacts(s)
    with pytest.raises(ValueError):s.latch.observe(100,H,())


def test_independent_q_filter_and_fixed_drive_turn():
    low=state();high=state();rates=np.zeros(9);rates[4:6]=[30.,40.]
    elevated=rates.copy();elevated[6]=100.
    _,u0=commit(low,rates);_,u1=commit(high,elevated)
    assert np.array_equal(u0[0,:2],u1[0,:2])
    assert high.q==pytest.approx(1-r.BETA) and u1[0,2]==pytest.approx(1-.25*(1-r.BETA))
    basefreq=np.full(6,12.);coupling=np.arange(36,dtype=float).reshape(6,6)
    f0,k0,a0=r.intent_parameters(u0[0],basefreq,coupling)
    f1,k1,a1=r.intent_parameters(u1[0],basefreq,coupling)
    assert np.array_equal(f0,f1) and np.array_equal(k0,k1)
    assert np.allclose(a1,a0*u1[0,2]) and not np.array_equal(a0,a1)
    assert np.allclose(a1[3:]/a1[:3],a0[3:]/a0[:3])


@pytest.mark.parametrize('off',[False,True])
def test_silence_or_outputoff_clears_both_filters(off):
    s=state();rates=np.ones(9)*100.;commit(s,rates)
    assert s.q>0 and s.motor.state.any() and s.motor.decoded_state.any()
    contacts(s);commit(s,rates if off else np.zeros(9),off=off)
    assert s.q==0 and not s.motor.state.any() and not s.motor.decoded_state.any()
    assert np.array_equal(s.intent,[0.,0.,1.])


def test_excursion_alone_cannot_start_movement():
    s=state();rates=np.zeros(9);rates[6]=100.
    commit(s,rates)
    assert s.intent[0]==0 and s.intent[1]==0 and s.intent[2]<1
    frequency,coupling,_=r.intent_parameters(s.intent,np.ones(6),np.ones((6,6)))
    assert not frequency.any() and not coupling.any()


@pytest.mark.parametrize('intent',[[.41,0.,1.],[.2,.81,1.],[.2,0.,.74],[.2,0.,1.01],[np.nan,0.,1.],[.2,0.]])
def test_three_axis_bounds(intent):
    with pytest.raises(ValueError):r.intent_parameters(np.array(intent),np.ones(6),np.ones((6,6)))


def test_valid_checkpoint_roundtrip_and_copies():
    s=state();commit(s,np.ones(9)*30.);contacts(s,{17:[(0,2,-.01)]});commit(s,np.ones(9)*40.)
    s.latch.observe(100,H,[(1,3,-.1),(1,2,-.01)])
    checkpoint=s.checkpoint();target=state();target.restore_owned(checkpoint)
    assert checkpoint_values(target)==checkpoint_values(s)
    target_arrays=(target.intent,target.held_current,target.motor.state,target.motor.decoded_state)
    source_arrays=(s.intent,s.held_current,s.motor.state,s.motor.decoded_state)
    for key,destination,original in zip(('intent','held_current','motor_state','decoded_state'),target_arrays,source_arrays):
        assert not np.shares_memory(destination,checkpoint[key]) and not np.shares_memory(destination,original)
    checkpoint['intent'][:]=0;checkpoint['held_current'][:]=0;checkpoint['events'].clear()
    checkpoint['held_frame']['events']=();checkpoint['touches'][:]=[False,False]
    assert target.intent[0]>0 and target.latch.events==[(100,1,1,2,-.01)]
    assert target.held_frame['events']==((17,0,0,2,-.01),) and target.latch.touches==[False,True]
    target.intent[:]=0
    assert s.intent[0]>0


@pytest.mark.parametrize('fault',['q','intent','motor','binding','touch','event','held_model','held_events','held_interval','held_current','extra'])
def test_restore_malformed_is_atomic(fault):
    s=state();commit(s,np.ones(9)*30.);contacts(s,{17:[(0,2,-.01)]});commit(s,np.ones(9)*30.)
    s.latch.observe(100,H,[(1,2,-.01)])
    checkpoint=s.checkpoint();before=checkpoint_values(s)
    if fault=='q':checkpoint['q']=2.
    elif fault=='intent':checkpoint['intent'][0]=.3
    elif fault=='motor':checkpoint['motor_state'][0]=np.nan
    elif fault=='binding':checkpoint['binding']='e'*64
    elif fault=='touch':checkpoint['touches']=[False,False]
    elif fault=='event':checkpoint['events']=[(100,0,1.,2,-.01)]
    elif fault=='held_model':checkpoint['held_frame']['model']='e'*64
    elif fault=='held_events':checkpoint['held_frame']['events']=((99,0,0,3,-.01),)
    elif fault=='held_interval':checkpoint['held_frame']['contact_start']=100
    elif fault=='held_current':checkpoint['held_current'][8]=1.
    else:checkpoint['arbitrary']=1
    with pytest.raises(ValueError):s.restore_owned(checkpoint)
    assert checkpoint_values(s)==before


def test_initial_owned_restore_and_full_restore_refusal():
    s=state();s.restore_owned(s.checkpoint())
    before=checkpoint_values(s)
    with pytest.raises(ValueError,match='full restore unavailable'):s.restore_full({})
    assert checkpoint_values(s)==before


def metadata():
    segments={leg+'_'+link:['fly-a/'+leg+'_'+link+'_geom'] for leg in b.LEGS for link in b.LINKS}
    names=tuple(v[0] for v in segments.values())+('obstacle-0','ground_plane','fly-b/lf_tibia_geom','fly-a/c_thorax_geom')
    owners=tuple('fly-a/'+s for s in segments)+('world','world','fly-b/lf_tibia','fly-a/c_thorax')
    return names,owners,segments


def test_complete_leg_geometry_binding_and_exclusions():
    names,owners,segments=metadata()
    g=b.bind_geometry_metadata(H,'fly-a',names,owners,segments,('obstacle-0',),r.DT,'b'*64)
    assert g.leg_sides.count('L')==24 and g.leg_sides.count('R')==24
    assert g.leg_sides[-4:]==('excluded',)*4 and g.obstacles==(48,)
    assert g.actuator_sha256=='b'*64


@pytest.mark.parametrize('fault',['missing_segment','missing_geom','omitted_geom','wrong_owner','wrong_side','obstacle','dt'])
def test_geometry_metadata_rejects_incomplete_or_wrong_binding(fault):
    names,owners,segments=metadata();obstacles=('obstacle-0',);dt=r.DT
    if fault=='missing_segment':del segments['lf_tibia']
    elif fault=='missing_geom':segments['lf_tibia']=[]
    elif fault=='omitted_geom':names+=('fly-a/extra_geom',);owners+=('fly-a/lf_tibia',)
    elif fault=='wrong_owner':owners=('fly-b/lf_coxa',)+owners[1:]
    elif fault=='wrong_side':segments['rf_tibia']=segments['lf_tibia'].copy()
    elif fault=='obstacle':obstacles=('ground_plane',)
    else:dt=.001
    with pytest.raises(ValueError):b.bind_geometry_metadata(H,'fly-a',names,owners,segments,obstacles,dt,'b'*64)


def test_actuator_binding_requires_unique_named_order():
    good=b.ActuatorBinding(H,'fly-a',tuple(range(42)),tuple(range(42,48)),tuple('dof-'+str(i) for i in range(42)),'b'*64)
    assert r.hexhash(good.identity)
    with pytest.raises(ValueError):b.ActuatorBinding(H,'fly-a',tuple(range(42)),tuple(range(6)),good.dof_names,'b'*64)


def test_solver_contact_cache_reader_atomic_for_all_subjects():
    a=state('fly-a');c=state('fly-c');commit(a);commit(c)
    adapter=object.__new__(b.RichBodyAdapter)
    adapter.geometry=(a.geometry,c.geometry)
    adapter.body=SimpleNamespace(tick=1,data=SimpleNamespace(contact=[SimpleNamespace(geom1=0,geom2=2,dist=-.1)]))
    adapter.observe_completed_contacts([a,c],0)
    assert a.latch.events==[(0,0,0,2,-.1)] and c.latch.events==[]
    before=[checkpoint_values(a),checkpoint_values(c)]
    with pytest.raises(ValueError):adapter.observe_completed_contacts([a,c],0)
    assert [checkpoint_values(a),checkpoint_values(c)]==before


def test_unqualified_profile_and_body_admission_refused():
    manifest=r.profile_manifest()
    assert manifest['ready'] is False and manifest['research_only'] is True and manifest['qualified_base'] is False
    for request in ({'profile':r.PROFILE,'production':True},{'profile':r.PROFILE,'research':True},{'profile':r.PROFILE,'cuda':True},{'profile':'vision'}):
        with pytest.raises(ValueError):r.admit(request)
    adapter=object.__new__(b.RichBodyAdapter)
    with pytest.raises(ValueError,match='unqualified'):adapter.step(None,None)
    with pytest.raises(ValueError,match='native body restore unavailable'):adapter.restore({})


def method_text(path,cls,method):
    source=path.read_text();tree=ast.parse(source)
    owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    node=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name==method)
    return ast.get_source_segment(source,node)


def test_actual_controller_source_has_only_approved_amplitude_seam():
    old=method_text(SOURCE/'cadence_v15.py','AllocationHybridController','_advance')
    new=method_text(SOURCE/'rich_bridge_v1_controller.py','RichBridgeController','_advance')
    expected=old.replace('def _advance(self,common,asymmetry,obs):','def _advance(self,common,asymmetry,excursion,obs):').replace('intrinsic_amps=np.repeat','intrinsic_amps=excursion*np.repeat')
    assert new==expected
    assert new.count('self.cpg_network.step()')==1
    assert new.index('intrinsic_amps=excursion*')<new.index('self.cpg_network.step()')
    old_step=method_text(SOURCE/'cadence_v15.py','AllocationHybridController','step')
    new_step=method_text(SOURCE/'rich_bridge_v1_controller.py','RichBridgeController','step')
    tail='if common<=SILENCE:'
    assert new_step[new_step.index(tail):]==old_step[old_step.index(tail):].replace('shadow._advance(common,asymmetry,obs)','shadow._advance(common,asymmetry,excursion,obs)')
    assert 'u=array(intent,(3,))' in new_step and 'common,asymmetry,excursion=map(float,u)' in new_step


def test_body_source_has_explicit_three_axis_single_shared_step():
    source=(SOURCE/'rich_bridge_v1_body.py').read_text()
    assert source.count('self.body.sim.step()')==1
    assert 'self.body.step(' not in source
    assert 'values=array(intents,(len(self.controllers),3))' in source
    assert 'actions=[c.step(u,obs) for c,u,obs in zip(shadows,values,snapshots)]' in source
    assert source.index("admit({'profile':PROFILE})")<source.index('shadows,ctrl,values=self._propose_actions')
    for name in ('rich_bridge_v1.py','rich_bridge_v1_body.py','rich_bridge_v1_controller.py','rich_bridge_v1_seals.py'):
        tree=ast.parse((SOURCE/name).read_text())
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','exec','compile') for n in ast.walk(tree))


@pytest.mark.parametrize('layout',['zero_stride','overlapping_stride','strided','reversed'])
def test_fix1_late_unsupported_destination_rejects_whole_batch(layout):
    first=state('fly-a');second=state('fly-c')
    frames,rates=r.snapshot_boundary([first,second],0,[np.array([.1,.4]),np.array([.4,.1])],[np.ones(9),np.ones(9)*2])
    if layout=='zero_stride':
        backing=np.array([7.])
        bad=np.lib.stride_tricks.as_strided(backing,shape=(9,),strides=(0,),writeable=True)
    elif layout=='overlapping_stride':
        backing=np.zeros(10)
        bad=np.ndarray((9,),dtype=np.float64,buffer=backing,strides=(4,))
    elif layout=='strided':
        backing=np.full(18,7.);bad=backing[::2]
    else:
        backing=np.full(9,7.);bad=backing[::-1]
    external=[np.full(9,3.),bad]
    before=[checkpoint_values(first),checkpoint_values(second)]
    backing_before=backing.tobytes();first_before=external[0].copy()
    with pytest.raises(ValueError,match='external destination'):
        r.commit_boundary([first,second],frames,rates,external)
    assert [checkpoint_values(first),checkpoint_values(second)]==before
    assert np.array_equal(external[0],first_before) and backing.tobytes()==backing_before


def test_fix1_native_contiguous_view_delivers_exact_held_current():
    subject=state();frame=subject.latch.frame(0,np.array([.1,.4]),subject.binding)
    backing=np.full(11,7.);external=backing[1:10]
    r.commit_boundary([subject],[frame],[np.zeros(9)],[external])
    assert np.array_equal(external,subject.held_current)
    assert np.array_equal(external[:2],48*encode_odor(.1,.4))
    assert not external[2:].any() and backing[0]==backing[-1]==7.


@pytest.mark.parametrize('owner',['fly-a/c_thorax','fly-b/lf_tibia'])
def test_fix1_obstacle_name_rejects_compiled_fly_owner(owner):
    names,owners,segments=metadata()
    owners=owners[:48]+(owner,)+owners[49:]
    before=deepcopy((names,owners,segments))
    with pytest.raises(ValueError,match='obstacle.*ownership'):
        b.bind_geometry_metadata(H,'fly-a',names,owners,segments,('obstacle-0',),r.DT,'b'*64)
    assert (names,owners,segments)==before


def test_fix1_world_obstacle_contact_keeps_ground_self_and_other_excluded():
    names,owners,segments=metadata()
    geometry=b.bind_geometry_metadata(H,'fly-a',names,owners,segments,('obstacle-0',),r.DT,'b'*64)
    latch=r.ContactLatch(geometry)
    latch.observe(0,H,[(0,49,-.01),(0,50,-.01),(0,51,-.01),(0,48,-.01),(24,48,.01)])
    assert latch.touches==[True,False] and latch.events==[(0,3,0,48,-.01)]
