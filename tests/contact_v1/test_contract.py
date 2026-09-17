"""Authored fixtures only. No native, canonical graph, asset or old evidence import."""
import importlib.abc
import sys

FORBIDDEN=('mujoco','flygym','flygym_demo','flyarena.neural','flyarena.connectome',
           'flyarena.body','flyarena.experiments.cadence','flyarena.experiments.mechanical')
class ScientificImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(fullname==p or fullname.startswith(p+'.') or fullname.startswith(p+'_') for p in FORBIDDEN):
            raise RuntimeError('scientific import forbidden in fixture flight: '+fullname)
        return None
sys.meta_path.insert(0,ScientificImportGuard())

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from types import SimpleNamespace
import numpy as np
from flyarena.experiments.contact_v1.contracts import (Binding, Contact, Observation, ContractError,
    DT, CORRECTION_NORMS, encode, decode, observation_state)
from flyarena.experiments.contact_v1.law import (Controller, task_rows, shared_twist, regularized_velocity,
    capped_command, inside_eroded_hull, release_order)
from flyarena.experiments.contact_v1.native import transport_material, CompletedInterval, IntervalRow, NativePort, interval_state, interval_from_state
from flyarena.experiments.contact_v1.prospective import plan, require_admission

POSITIONS=np.array([[-1.,1.],[0.,1.],[1.,1.],[-1.,-1.],[0.,-1.],[1.,-1.]])
FRAME=np.array([[0.,0.,1.],[1.,0.,0.],[0.,1.,0.]])

def binding():
    pattern=np.array([[0,1,0,1,0,1],[1,0,1,0,1,0]]*3,dtype=np.float64)
    return Binding('a'*64,'b'*64,'c'*64,73,72,np.arange(7,49,dtype=np.int64).reshape(6,7),
        np.arange(6,48,dtype=np.int64).reshape(6,7),np.arange(6,dtype=np.int64),
        np.arange(30,dtype=np.int64).reshape(6,5),30,tuple(range(30))+(31,),
        np.full((6,7),-5.),np.full((6,7),5.),np.full(6,3.),pattern*10,pattern*np.pi,300)


def observation(tick=1,loads=None,height=0.,nonfoot=False):
    b=binding(); loads=range(6) if loads is None else loads
    q=np.zeros(73); v=np.zeros(72); minima=np.zeros((6,5,3)); J=np.zeros((6,5,3,72))
    distal=np.zeros((6,3)); dJ=np.zeros((6,3,72)); contacts=[]
    for i in range(6):
        minima[i,:,:2]=POSITIONS[i]; minima[i,:,2]=height; distal[i]=minima[i,4]
        for j in range(5): J[i,j][:,b.vadr[i][:3]]=np.eye(3)
        dJ[i]=J[i,4]
        if i in loads:
            force=np.array([1.,0.,0.,0.,0.,0.]); point=distal[i].copy()
            contacts.append(Contact(i,int(b.foot_geoms[i,4]),30,i,tick-1,force,0.,FRAME.copy(),point.copy(),point.copy(),point.copy(),dJ[i].copy(),np.zeros(3),np.zeros(3),np.zeros(3)))
    if nonfoot:
        contacts.append(Contact(99,31,30,-1,tick-1,np.array([1.,0.,0.,0.,0.,0.]),0.,FRAME.copy(),np.zeros(3),np.zeros(3),np.zeros(3),np.zeros((3,72)),np.zeros(3),np.zeros(3),np.zeros(3)))
    return Observation(tick,b.model_hash,q,v,q.copy(),v.copy(),np.array([0.,0.,.5]),np.eye(3),np.zeros(3),np.zeros(3),np.array([0.,0.,.5]),np.zeros(3),9810.,minima,np.zeros((6,5),dtype=np.int64),J,distal,dJ,tuple(contacts),np.zeros(48))


class References:
    def __init__(self): self.calls=0
    def angles(self,phi,r): self.calls+=1; return np.zeros((6,7))
    def excursion(self,i,obs,r): self.calls+=1; return float(r*.1)


def fixture_intent(theta,r,b,c,a):
    # Authored one-tick forecast; does NOT evaluate the native CPG equations.
    return theta+1e-4,np.full(6,.5)


def controller(phase=4.):
    return Controller(binding(),np.full(6,phase),np.zeros((6,7)),np.ones(6,dtype=bool),
                      ('MT19937',np.concatenate((np.array([7,11],dtype=np.uint32),np.ones(622,dtype=np.uint32))),0,0,0.))


def initialize(c=None):
    c=controller() if c is None else c
    c.step([.2,.2],observation(),References(),intent=fixture_intent)
    return c


class ContactContracts(unittest.TestCase):
    def test_material_transport_uses_previous_body_frame(self):
        prior=np.array([2.,1.,0.]); oldpos=np.array([1.,1.,0.]); newpos=np.array([5.,4.,3.])
        turn=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
        local,current=transport_material(prior,oldpos,np.eye(3),newpos,turn)
        np.testing.assert_array_equal(local,[1.,0.,0.]); np.testing.assert_array_equal(current,[5.,5.,3.])
        np.testing.assert_array_equal(prior,[2.,1.,0.])

    def test_interval_clock_capacity_and_ownership(self):
        b=binding(); row=IntervalRow(0,4,30,0,np.zeros(3),FRAME.copy(),0.,np.array([1.,0.,0.,0.,0.,0.]))
        packet=CompletedInterval(7,b.model_hash,np.zeros(73),np.zeros(72),(row,))
        packet.validate(b,8)
        restored=interval_from_state(decode(encode(interval_state(packet))))
        restored.validate(b,8)
        np.testing.assert_array_equal(restored.qpos,packet.qpos)
        for invalid,endpoint in ((packet,7),(replace(packet,rows=(row,)*513),8),
                                 (replace(packet,rows=(replace(row,leg=5),)),8)):
            with self.assertRaises(ContractError): invalid.validate(b,endpoint)

    def test_late_leg_invalid_observation_has_no_mutation(self):
        c=initialize(); before=c.checkpoint_json(); obs=observation(2)
        jac=obs.minimum_jacobians.copy(); jac[5,4,2,71]=np.nan
        refs=References()
        with self.assertRaises(ContractError): c.step([.2,.2],replace(obs,minimum_jacobians=jac),refs,intent=fixture_intent)
        self.assertEqual(c.checkpoint_json(),before); self.assertEqual(refs.calls,0)

    def test_late_leg_reference_failure_is_atomic(self):
        class Bad(References):
            def angles(self,phi,r):
                x=np.zeros((6,7)); x[5,6]=6.; return x
        c=initialize(); before=c.checkpoint_json()
        with self.assertRaises(ContractError): c.step([.2,.2],observation(2),Bad(),intent=fixture_intent)
        self.assertEqual(before,c.checkpoint_json())

    def test_exact_silence_before_observation_and_provider(self):
        class Bomb:
            def __getattribute__(self,name): raise AssertionError('silence read provider')
        c=initialize(); before=c.checkpoint_json()
        action=c.step([1e-4,1e-4],Bomb(),Bomb(),intent=Bomb())
        self.assertEqual(before,c.checkpoint_json())
        action.angles[:]=123.; self.assertEqual(before,c.checkpoint_json())
        with self.assertRaises(ContractError): c.step([-1.,1.],None,None)
        self.assertEqual(before,c.checkpoint_json())

    def test_all_five_mesh_lift_rows_and_passive_compensation(self):
        c=initialize(controller(.5)); s=deepcopy(c.state); s['modes'][0]='LIFT'
        obs=observation(2,loads=[],height=.01)
        v=obs.qvel.copy(); v[48]=2.
        jac=obs.minimum_jacobians.copy(); jac[0,:,2,48]=3.
        obs=replace(obs,qvel=v,minimum_jacobians=jac)
        A,b=task_rows(binding(),obs,s,0,np.zeros(6),np.zeros(3),np.zeros(3))
        self.assertEqual(A.shape,(7,7))
        np.testing.assert_allclose(b[:5],(min((.05-.01)/.003,.05/.003)-6.)/np.sqrt(5))
        self.assertTrue(np.all(A[:5,2]>0))

    def test_landing_damps_every_proximal_contact(self):
        c=initialize(controller(2.5)); s=deepcopy(c.state); s['modes'][0]='LAND'
        obs=observation(2); con=obs.contacts[0]
        proximal=replace(con,index=10,geom=0)
        obs=replace(obs,contacts=obs.contacts+(proximal,))
        A,b=task_rows(binding(),obs,s,0,np.zeros(6),np.zeros(3),np.zeros(3))
        self.assertEqual(len(A),7)  # XY+normal +2 tangents for EACH of two contacts
        np.testing.assert_allclose(b[3:],0.)

    def test_regularized_solve_independent_closed_form(self):
        A=np.zeros((1,7)); A[0,0]=2.; z0=np.zeros(7)
        z,residual=regularized_velocity(A,np.array([3.]),z0)
        self.assertAlmostEqual(z[0],6/(4+.02**2)); np.testing.assert_array_equal(z[1:],np.zeros(6))
        self.assertAlmostEqual(residual[0],2*z[0]-3.)

    def test_correction_radius_rate_and_compiled_range(self):
        old=np.zeros(7); native=np.zeros(7); next_native=np.full(7,.001)
        z=np.array([1e6,-1e6,0.,0.,0.,0.,0.]); lo=np.full(7,-.002); hi=np.full(7,.002)
        cmd,d=capped_command(old,native,next_native,z,np.zeros(7),lo,hi,0)
        self.assertTrue(np.all(cmd>=lo)&np.all(cmd<=hi))
        self.assertLessEqual(np.linalg.norm(cmd-next_native),80*CORRECTION_NORMS[0])
        self.assertLessEqual(np.linalg.norm(cmd-old),np.linalg.norm(next_native-native)+800*DT*CORRECTION_NORMS[0]+1e-14)
        self.assertAlmostEqual(np.linalg.norm(d['limited_increment']),800*DT*CORRECTION_NORMS[0])

    def test_capture_requires_margin_and_geometry(self):
        square=np.array([[-1.,-1.],[1.,-1.],[1.,1.],[-1.,1.]])
        self.assertTrue(inside_eroded_hull(square,np.zeros(2)))
        self.assertFalse(inside_eroded_hull(square,np.array([.99,0.])))
        self.assertFalse(inside_eroded_hull(square[:2],np.zeros(2)))
        self.assertEqual(release_order(np.array([3.,4.,4.,0.,0.,0.]),np.zeros(6),[2,0,1]),[1,2,0])

    def test_nonfoot_veto_and_release_removal_arbitration(self):
        c=initialize(); s=c.state
        s['phi'][:]=2*np.pi; s['theta'][:]=2*np.pi+.01; s['modes']=['RELEASE_WAIT']*6
        s['load_count'][:]=30; s['distal_count'][:]=30
        s['last_tick']=1
        before=c.checkpoint_json()
        proposal=c.propose([.2,.2],observation(2,nonfoot=True),References(),intent=fixture_intent)
        self.assertEqual(proposal.state['diagnostics']['admitted'],[])
        self.assertEqual(before,c.checkpoint_json())
        proposal=c.propose([.2,.2],observation(2),References(),intent=fixture_intent)
        admitted=proposal.state['diagnostics']['admitted']
        self.assertGreater(len(admitted),0); self.assertLessEqual(len(admitted),3)
        remaining=set(range(6))-set(admitted)
        self.assertTrue(inside_eroded_hull(POSITIONS[sorted(remaining)],np.zeros(2)))

    def test_phase_arrival_does_not_spend_extra_in_next_segment(self):
        c=initialize(controller(.99995)); c.state['phi'][:]=.99995; c.state['theta'][:]=.99995
        p=c.propose([.2,.2],observation(2,loads=[],height=.05),References(),intent=fixture_intent)
        np.testing.assert_array_equal(p.state['phi'],np.ones(6)); self.assertEqual(p.state['modes'],['LIFT']*6)
        self.assertTrue(np.all(p.state['clear_count']<30))

    def test_dwell_gate_then_transfer_and_distal_gate(self):
        c=initialize(controller(1.)); c.state['phi'][:]=1.; c.state['theta'][:]=1.01
        c.state['modes']=['LIFT']*6; c.state['clear_count'][:]=29
        p=c.propose([.2,.2],observation(2,loads=[],height=.05),References(),intent=fixture_intent)
        self.assertEqual(p.state['modes'],['TRANSFER']*6); np.testing.assert_array_equal(p.state['phi'],np.ones(6))
        # Proximal force alone cannot satisfy the selected distal transition.
        c=initialize(controller(3.)); c.state['phi'][:]=3.; c.state['theta'][:]=3.01; c.state['modes']=['LAND']*6
        obs=observation(2); obs=replace(obs,contacts=tuple(replace(con,geom=int(binding().foot_geoms[con.leg,0])) for con in obs.contacts))
        p=c.propose([.2,.2],obs,References(),intent=fixture_intent)
        self.assertEqual(p.state['modes'],['LAND']*6); self.assertTrue(np.all(p.state['distal_count']==0))

    def test_support_loss_reacquires_before_other_release(self):
        c=initialize(); c.state['phi'][1]=2*np.pi; c.state['theta'][1]=2*np.pi+.001; c.state['modes'][1]='RELEASE_WAIT'
        c.state['load_count'][:]=30
        p=c.propose([.2,.2],observation(2,loads=[1,2,3,4,5]),References(),intent=fixture_intent)
        self.assertEqual(p.state['modes'][0],'REACQUIRE'); self.assertEqual(p.state['diagnostics']['admitted'],[])
        self.assertEqual(p.state['phi'][0],c.state['phi'][0])

    def test_stall_and_phase_lag_do_not_commit(self):
        c=initialize(controller(1.)); c.state['modes']=['LIFT']*6; c.state['phi'][:]=1.; c.state['theta'][:]=1.01; c.state['wait_count'][:]=500
        before=c.checkpoint_json()
        with self.assertRaisesRegex(ContractError,'stall'): c.step([.2,.2],observation(2),References(),intent=fixture_intent)
        self.assertEqual(before,c.checkpoint_json())
        c.state['wait_count'][:]=0; c.state['theta'][:]=c.state['phi']+np.pi/2
        before=c.checkpoint_json()
        with self.assertRaisesRegex(ContractError,'phase_lag'): c.step([.2,.2],observation(2),References(),intent=fixture_intent)
        self.assertEqual(before,c.checkpoint_json())

    def test_checkpoint_json_restore_and_unsupported_payload_rollback(self):
        c=initialize(); serialized=c.checkpoint_json(); checkpoint=json.loads(serialized)
        c.step([.2,.2],observation(2),References(),intent=fixture_intent)
        c.restore(checkpoint); self.assertEqual(c.checkpoint_json(),serialized)
        saved=deepcopy(c.state); checkpoint['state']['wait_count']=encode(np.full(6,501,dtype=np.int64))
        with self.assertRaises(ContractError): c.restore(checkpoint)
        self.assertEqual(c.checkpoint_json(),serialized)
        checkpoint=json.loads(serialized); checkpoint['state']['angles']['__array__']='<f4'
        with self.assertRaises(ContractError): c.restore(checkpoint)
        self.assertEqual(c.checkpoint_json(),serialized)
        c.state['rng_state'][1][0]=99
        self.assertEqual(saved['rng_state'][1][0],7)

    def test_stale_proposal_cannot_commit(self):
        c=initialize(); p=c.propose([.2,.2],observation(2),References(),intent=fixture_intent)
        c.commit(p); before=c.checkpoint_json()
        with self.assertRaises(ContractError): c.commit(p)
        self.assertEqual(before,c.checkpoint_json())

    def test_plan_denominators_and_both_window_admission(self):
        p=plan(); self.assertEqual(len(p['development']),32); self.assertEqual(p['conditional_total_seconds'],196.01)
        self.assertFalse(p['science_authorized']); self.assertFalse(p['ready'])
        row={'trial_id':'fixture','complete':True,'all_original_gates_pass':True,'inconclusive':False,'controller_failure':False,'missing_remainder':False,'partials_retained':True}
        result=require_admission([row],[dict(row,controller_failure=True)],['fixture'])
        self.assertFalse(result['mechanical_admission'])
        with self.assertRaises(ContractError): require_admission([],[],['fixture'])

    def test_native_port_commit_fixture_and_silence(self):
        c=initialize(); obs=observation(2)
        body=SimpleNamespace(tick=2,data=SimpleNamespace(qpos=obs.qpos.copy(),qvel=obs.qvel.copy(),ctrl=np.zeros(48)),drives=np.zeros((1,2)))
        class FixtureAdapter:
            binding=c.binding
            def observe(self,*args): raise AssertionError('native observation must not run')
            def action_ctrl(self,old,action):
                new=old.copy(); new[:42]=action.angles.reshape(42); new[42:]=action.adhesion; return new
        port=NativePort(body,FixtureAdapter(),c,{'fixture':'not a physical checkpoint'})
        before=c.checkpoint_json(); self.assertIsNone(port.prepare([0.,0.],object()))
        self.assertEqual(before,c.checkpoint_json()); self.assertIsNone(port.sensor_state)
        proposal=c.propose([.2,.2],obs,References(),intent=fixture_intent)
        rows=tuple(IntervalRow(x.index,x.geom,x.ground,x.leg,x.point_prior,x.frame,x.distance,x.force) for x in obs.contacts)
        packet=CompletedInterval(1,obs.model_hash,obs.prior_qpos,obs.prior_qvel,rows)
        port.recorder_state={'pre_step':{'tick':1,'model_hash':obs.model_hash,'qpos':obs.prior_qpos.copy(),'qvel':obs.prior_qvel.copy()},'completed_interval':interval_state(packet)}
        port.apply(proposal)
        np.testing.assert_array_equal(body.data.ctrl[42:],np.ones(6))
        self.assertEqual(port.sensor_state['tick'],2)
        committed=c.checkpoint_json(); ctrl=body.data.ctrl.copy()
        with self.assertRaises(ContractError): port.apply(proposal)
        self.assertEqual(committed,c.checkpoint_json()); np.testing.assert_array_equal(ctrl,body.data.ctrl)

    def test_native_port_rejects_moved_authoritative_fixture(self):
        c=initialize(); obs=observation(2)
        body=SimpleNamespace(tick=2,data=SimpleNamespace(qpos=obs.qpos.copy(),qvel=obs.qvel.copy(),ctrl=np.zeros(48)),drives=np.zeros((1,2)))
        adapter=SimpleNamespace(binding=c.binding)
        port=NativePort(body,adapter,c,{})
        proposal=c.propose([.2,.2],obs,References(),intent=fixture_intent)
        body.data.qpos[0]=1.; before=c.checkpoint_json()
        with self.assertRaises(ContractError): port.apply(proposal)
        self.assertEqual(before,c.checkpoint_json()); np.testing.assert_array_equal(body.data.ctrl,np.zeros(48))

    def test_finite_binding_capacity_and_unsigned_rng_roundtrip(self):
        b=binding()
        for invalid in (replace(b,nq=1025),replace(b,nv=1025),replace(b,total_vertices=100001)):
            with self.assertRaises(ContractError): invalid.validate()
        rng=np.array([0,2**32-1],dtype=np.uint32)
        np.testing.assert_array_equal(decode(encode(rng)),rng)

    def test_shared_body_twist_uses_all_legs_without_world_goal(self):
        b=binding(); obs=observation(); native=np.zeros((6,7)); native[:,0]=-2.
        velocity,omega=shared_twist(b,obs,['SUPPORT']*6,native,.5)
        np.testing.assert_allclose(velocity,[2.,0.,0.],atol=1e-14)
        np.testing.assert_allclose(omega,np.zeros(3),atol=1e-14)
        tilted=replace(obs,thorax_pos=np.array([0.,0.,.45]))
        velocity,omega=shared_twist(b,tilted,['SUPPORT']*6,native,.5)
        self.assertAlmostEqual(velocity[2],1.)

    def test_guard_native_unexecuted(self):
        self.assertNotIn('mujoco',sys.modules); self.assertNotIn('flygym',sys.modules)
        self.assertNotIn('flygym_demo',sys.modules)

if __name__=='__main__': unittest.main(verbosity=2)
