"""Bounded regressions for the three registered fix1 source-contract defects."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import json
import unittest
import numpy as np
import contact_v1_fixture_tests as f
from flyarena.experiments.contact_v1.contracts import ContractError, encode, decode, observation_state, DT
from flyarena.experiments.contact_v1.native import NativePort, CompletedInterval, IntervalRow, interval_state


def port_fixture(c=None, tick=2):
    c=f.initialize() if c is None else c
    obs=f.observation(tick)
    data=SimpleNamespace(qpos=obs.qpos.copy(),qvel=obs.qvel.copy(),ctrl=np.zeros(48),time=tick*DT)
    class Adapter:
        binding=c.binding
        calls=0
        def action_ctrl(self,old,action):
            self.calls+=1
            new=old.copy(); new[:42]=action.angles.reshape(42); new[42:]=action.adhesion
            return new
        def observe(self,*args): raise AssertionError('observation/native geometry must not run')
    port=NativePort(SimpleNamespace(tick=tick,data=data,drives=np.zeros((1,2))),Adapter(),c,{})
    port.recorder_state={'pre_step':{'tick':tick-1,'model_hash':obs.model_hash,'qpos':obs.prior_qpos.copy(),'qvel':obs.prior_qvel.copy()},'completed_interval':interval_state(packet_for(obs))}
    return port


def snapshot(port):
    return (port.controller.checkpoint_json(),port.body.data.ctrl.tobytes(),
            json.dumps(encode(port.sensor_state),sort_keys=True),json.dumps(encode(port.recorder_state),sort_keys=True))


def packet_for(obs):
    rows=tuple(IntervalRow(c.index,c.geom,c.ground,c.leg,c.point_prior.copy(),c.frame.copy(),c.distance,c.force.copy()) for c in obs.contacts)
    return CompletedInterval(obs.tick-1,obs.model_hash,obs.prior_qpos.copy(),obs.prior_qvel.copy(),rows)


class Fix1Contracts(unittest.TestCase):
    def assert_restore_rejected(self,mutate):
        c=f.initialize(); before=c.checkpoint_json(); cp=c.checkpoint(); state=decode(cp['state'])
        mutate(state); cp['state']=encode(state)
        with self.assertRaises(ContractError): c.restore(cp)
        self.assertEqual(before,c.checkpoint_json())
        # The failed restore cannot rewind time or count its prior interval again.
        refs=f.References()
        with self.assertRaises(ContractError): c.step([.2,.2],f.observation(1),refs,intent=f.fixture_intent)
        self.assertEqual(refs.calls,0); self.assertEqual(before,c.checkpoint_json())

    def test_regression_foreign_commit(self):
        a=f.initialize(f.controller(4.)); b=f.initialize(f.controller(3.5))
        p=a.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent); before=b.checkpoint_json()
        with self.assertRaises(ContractError): b.commit(p)
        self.assertEqual(before,b.checkpoint_json())

    def test_regression_foreign_port(self):
        a=f.initialize(f.controller(4.)); port=port_fixture(f.initialize(f.controller(4.5)))
        p=a.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent); before=snapshot(port)
        with self.assertRaises(ContractError): port.apply(p)
        self.assertEqual(before,snapshot(port)); self.assertEqual(port.adapter.calls,0)

    def test_regression_same_state_restore_commit(self):
        c=f.initialize(); p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        c.restore(c.checkpoint()); before=c.checkpoint_json()
        with self.assertRaises(ContractError): c.commit(p)
        self.assertEqual(before,c.checkpoint_json())

    def test_regression_aba_restore_port(self):
        port=port_fixture(); c=port.controller; original=c.checkpoint()
        p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        c.commit(p); c.restore(original); before=snapshot(port)
        with self.assertRaises(ContractError): port.apply(p)
        self.assertEqual(before,snapshot(port)); self.assertEqual(port.adapter.calls,0)

    def test_regression_predecessor_state_mutation(self):
        c=f.initialize(); p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        c.state['rng_state'][1][0]=123; before=c.checkpoint_json()
        with self.assertRaises(ContractError): c.commit(p)
        self.assertEqual(before,c.checkpoint_json())

    def test_regression_rng_none(self): self.assert_restore_rejected(lambda s:s.update(rng_state=None))
    def test_regression_rng_string(self): self.assert_restore_rejected(lambda s:s.update(rng_state='malformed-rng'))
    def test_regression_empty_diagnostics(self): self.assert_restore_rejected(lambda s:s.update(diagnostics={}))
    def test_regression_observation_none(self): self.assert_restore_rejected(lambda s:s.update(last_observation=None))
    def test_regression_future_observation(self):
        def mutate(s):
            s['last_observation']['tick']=99
            for c in s['last_observation']['contacts']: c['interval_tick']=98
        self.assert_restore_rejected(mutate)
    def test_regression_rewound_last_tick(self): self.assert_restore_rejected(lambda s:s.update(last_tick=0))
    def test_regression_negative_magnitude(self): self.assert_restore_rejected(lambda s:s['magnitude'].__setitem__(5,-1.))
    def test_regression_negative_release_magnitude(self): self.assert_restore_rejected(lambda s:s['release_magnitude'].__setitem__(5,-.1))
    def test_regression_negative_excursion(self): self.assert_restore_rejected(lambda s:s['excursion'].__setitem__(5,-.1))
    def test_regression_negative_total_load(self): self.assert_restore_rejected(lambda s:s['total_force'].__setitem__(5,-.1))
    def test_regression_negative_distal_load(self): self.assert_restore_rejected(lambda s:s['distal_force'].__setitem__(5,-.1))
    def test_regression_mode_adhesion(self): self.assert_restore_rejected(lambda s:s['adhesion'].__setitem__(5,False))

    def reject_prestate(self,key):
        c=f.initialize(); obs=f.observation(2); bad=np.ones_like(getattr(obs,key)); refs=f.References(); before=c.checkpoint_json(); calls=[]
        def forecast(*args): calls.append(1); return f.fixture_intent(*args)
        with self.assertRaises(ContractError): c.step([.2,.2],replace(obs,**{key:bad}),refs,intent=forecast)
        self.assertEqual(before,c.checkpoint_json()); self.assertEqual(refs.calls,0); self.assertEqual(calls,[])
    def test_regression_qpos_prestate(self): self.reject_prestate('prior_qpos')
    def test_regression_qvel_prestate(self): self.reject_prestate('prior_qvel')

    def test_positive_restore_continuation_and_initial(self):
        c=f.controller(); cp=c.checkpoint(); other=f.controller(); other.restore(cp)
        self.assertEqual(c.checkpoint_json(),other.checkpoint_json())
        c=f.initialize(c); other.restore(c.checkpoint())
        for obj in (c,other): obj.step([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        self.assertEqual(c.checkpoint_json(),other.checkpoint_json())

    def test_positive_consecutive_and_deliberate_silence_gap(self):
        c=f.initialize(); refs=f.References()
        c.step([.2,.2],f.observation(2),refs,intent=f.fixture_intent)
        self.assertTrue(np.all(c.state['load_count']==2))
        before=c.checkpoint_json(); c.step([0.,0.],None,None)
        self.assertEqual(before,c.checkpoint_json())
        obs=replace(f.observation(5),prior_qpos=np.ones(73),prior_qvel=np.ones(72))
        c.step([.2,.2],obs,refs,intent=f.fixture_intent)
        self.assertTrue(np.all(c.state['load_count']==1)); self.assertEqual(c.state['generation'],3)

    def test_positive_fresh_port_commit_and_stale_rollback(self):
        port=port_fixture(); c=port.controller
        p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        port.apply(p); before=snapshot(port)
        with self.assertRaises(ContractError): port.apply(p)
        self.assertEqual(before,snapshot(port))

    def test_additional_semantic_schema_mutations(self):
        mutations=[lambda s:s.update(initialized=False),lambda s:s.update(generation=0),
          lambda s:s['magnitude'].__setitem__(0,1.81),lambda s:s['release_magnitude'].__setitem__(0,1.81),
          lambda s:s['resume_modes'].__setitem__(0,'LIFT'),lambda s:s['cycle'].__setitem__(0,2),
          lambda s:s['diagnostics']['legs'][5].pop('b'),lambda s:s['diagnostics'].update(legs=[]),
          lambda s:s.update(rng_state=('MT19937',np.ones(2,dtype=np.uint32),0,0,0.)),
          lambda s:s.update(rng_state=('MT19937',np.ones(624,dtype=np.uint32),625,0,0.)),
          lambda s:s.update(rng_state=('MT19937',np.ones(624,dtype=np.uint32),0,2,0.)),
          lambda s:s['last_observation']['contacts'][0].update(interval_tick=88)]
        for i,mutate in enumerate(mutations):
            with self.subTest(case=i): self.assert_restore_rejected(mutate)

    def test_recorder_actual_prestep_and_silence(self):
        port=port_fixture(tick=1); before=port.controller.checkpoint_json(); sensor=port.sensor_state
        saved=port.record_pre_step(); saved['qpos'][0]=22. # returned storage is isolated
        port.body.tick=2; good=packet_for(f.observation(2)); old=deepcopy(port.recorder_state)
        with self.assertRaises(ContractError): port.record_completed(replace(good,qpos=saved['qpos']))
        self.assertEqual(encode(old),encode(port.recorder_state))
        port.record_completed(good)
        self.assertEqual(before,port.controller.checkpoint_json()); self.assertIs(sensor,port.sensor_state)
        self.assertIsNone(port.prepare([0.,0.],object()))
        with self.assertRaises(ContractError): port.prepare([.2,.2],replace(good,qvel=np.ones(72)))
        self.assertEqual(before,port.controller.checkpoint_json())

    def test_port_prestate_rejected_before_observer(self):
        port=port_fixture(tick=1); port.body.data.qpos[0]=2.
        port.record_pre_step(); port.body.tick=2
        packet=replace(packet_for(f.observation(2)),qpos=port.body.data.qpos.copy())
        port.record_completed(packet); before=snapshot(port)
        with self.assertRaisesRegex(ContractError,'prestate'): port.prepare([.2,.2])
        self.assertEqual(before,snapshot(port))

    def native_payload(self):
        port=port_fixture(tick=1); c=port.controller; obs=f.observation(1); packet=packet_for(obs)
        port.body.data.ctrl[42:]=1.
        recorder={'pre_step':{'tick':0,'model_hash':obs.model_hash,'qpos':obs.prior_qpos.copy(),'qvel':obs.prior_qvel.copy()},'completed_interval':interval_state(packet)}
        cp={'version':port.VERSION,'registration':{},'binding':c.binding.token(),'data':deepcopy(port.body.data),
            'cache':{},'integration':np.zeros(1),'controller':c.checkpoint(),'sensor':encode(observation_state(obs)),
            'recorder':encode(recorder),'tick':1,'drives':np.zeros((1,2))}
        return port,cp

    def test_pure_native_payload_validation_and_rollback(self):
        port,cp=self.native_payload(); before=snapshot(port)
        state,sensor,recorder,drives=port.restored_payload(cp)
        self.assertEqual(encode(state),cp['controller']['state']); self.assertEqual(before,snapshot(port))
        mutations=[lambda x:x.update(sensor=None),lambda x:x.update(tick=2),
                   lambda x:x['data'].qpos.__setitem__(0,99.),lambda x:x['data'].__setattr__('time',1.),
                   lambda x:x['data'].ctrl.__setitem__(42,0.),lambda x:x.update(recorder=encode({})),
                   lambda x:x['controller']['state'].update(last_tick=0)]
        for mutate in mutations:
            bad=deepcopy(cp); mutate(bad)
            with self.assertRaises(ContractError): port.restored_payload(bad)
            self.assertEqual(before,snapshot(port))
        # Post-silence physical tick may exceed the held sensor/controller clock.
        gap=deepcopy(cp); gap['tick']=5; gap['data'].time=5*DT
        obs=replace(f.observation(5),prior_qpos=np.ones(73),prior_qvel=np.ones(72))
        packet=packet_for(obs); gap['recorder']=encode({'pre_step':{'tick':4,'model_hash':obs.model_hash,'qpos':obs.prior_qpos,'qvel':obs.prior_qvel},'completed_interval':interval_state(packet)})
        port.restored_payload(gap); self.assertEqual(before,snapshot(port))

    def test_regression_same_state_restore_port(self):
        port=port_fixture(); c=port.controller
        p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        c.restore(c.checkpoint()); before=snapshot(port)
        with self.assertRaises(ContractError): port.apply(p)
        self.assertEqual(before,snapshot(port)); self.assertEqual(port.adapter.calls,0)

    def test_regression_aba_restore_commit(self):
        c=f.initialize(); old=c.checkpoint()
        p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        c.commit(p); c.restore(old); before=c.checkpoint_json()
        with self.assertRaises(ContractError): c.commit(p)
        self.assertEqual(before,c.checkpoint_json())

    def test_port_assignment_failure_rolls_back_revision_and_state(self):
        class FailOnce(np.ndarray):
            failed=False
            def __setitem__(self,key,value):
                if not self.failed:
                    self.failed=True
                    np.ndarray.__setitem__(self,slice(0,3),np.array([99.,88.,77.]))
                    raise RuntimeError('authored partial assignment failure')
                np.ndarray.__setitem__(self,key,value)
        port=port_fixture(); port.body.data.ctrl=port.body.data.ctrl.view(FailOnce)
        c=port.controller; p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        before=snapshot(port); revision=c._revision
        with self.assertRaisesRegex(RuntimeError,'partial assignment'): port.apply(p)
        self.assertEqual(before,snapshot(port)); self.assertEqual(revision,c._revision)
        port.apply(p); self.assertEqual(c.state['last_tick'],2)

    def test_apply_requires_actual_recorder_packet(self):
        port=port_fixture(); c=port.controller
        p=c.propose([.2,.2],f.observation(2),f.References(),intent=f.fixture_intent)
        port.recorder_state['pre_step']['qpos'][0]=1.; before=snapshot(port)
        with self.assertRaises(ContractError): port.apply(p)
        self.assertEqual(before,snapshot(port)); self.assertEqual(port.adapter.calls,0)

    def test_pure_native_initial_and_post_physics_boundaries(self):
        port,cp=self.native_payload()
        # Initial native state can precede all active controller observations.
        initial=f.controller(); initial_port=port_fixture(initial,tick=1)
        first=deepcopy(cp); first['controller']=initial.checkpoint(); first['sensor']=None
        first['recorder']=encode({}); first['tick']=0; first['data'].time=0.
        initial_port.restored_payload(first)
        # Same active state held across one completed step uses its endpoint as prestate.
        following=deepcopy(cp); following['tick']=2; following['data'].time=2*DT
        obs=f.observation(2); packet=packet_for(obs)
        following['data'].qpos[0]=.25  # endpoint is allowed to move during that physics interval
        following['recorder']=encode({'pre_step':{'tick':1,'model_hash':obs.model_hash,'qpos':obs.prior_qpos,'qvel':obs.prior_qvel},'completed_interval':interval_state(packet)})
        before=snapshot(port); port.restored_payload(following); self.assertEqual(before,snapshot(port))
