"""Authored fixtures only: no native or production intent execution."""
import importlib.abc,importlib.util,pathlib,sys,unittest,tempfile,json
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('mujoco','flygym','flygym_demo') or fullname.startswith(('flyarena.neural','flyarena.connectome','flyarena.body')):raise AssertionError('scientific import forbidden: '+fullname)
sys.meta_path.insert(0,Guard())
import numpy as np
from copy import deepcopy
from dataclasses import replace
from flyarena.experiments.contact_mechanics_v1.schema import *
from flyarena.experiments.contact_mechanics_v1.metrics import *
from flyarena.experiments.contact_mechanics_v1.oracle import agree,verify_candidate
from flyarena.experiments.contact_mechanics_v1.io import Writers,read,stream_rows,write
from flyarena.experiments.contact_mechanics_v1.budget import Budget,ResourceStop
from flyarena.experiments.contact_mechanics_v1.verify import candidate_state,panel_admission
ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mechanics_authored_contact',ROOT/'tests/contact_v1/test_contract.py')
f=importlib.util.module_from_spec(spec);sys.modules[spec.name]=f;spec.loader.exec_module(f)

def forecast(theta,r,b,c,a):
    # All fixture phases equal and bilateral drive=.2: authored symmetric oracle.
    return theta+np.full(6,.002513274122871835),r+.002*(1-r)
def core(c,tick,obs=None):
    obs=f.observation(max(1,tick)) if obs is None else obs
    ctrl=np.r_[c.state['angles'].reshape(-1),c.state['adhesion'].astype(float)]
    return pack(CORE,{'qpos':obs.qpos,'qvel':obs.qvel,'ctrl':ctrl,'force':np.zeros(48),'input':np.zeros(2),'theta':c.state['theta'],'magnitude':c.state['magnitude'],'time':tick*DT,'action_tick':tick-1,'observation_tick':c.state['last_tick'],'interval_present':tick>0,'contact_offset':0,'contact_count':0})

class Contracts(unittest.TestCase):
    def test_panel_and_exact_waveform(self):
        self.assertEqual([len(panel(x)) for x in ('development','heldout','repeat')],[32,16,1])
        self.assertEqual(panel('development')[0].profile,CONTROL);self.assertEqual(panel('development')[1].profile,PROFILE)
        self.assertTrue(np.array_equal(waveform(CASES[6],2999),[0,0]));np.testing.assert_allclose(waveform(CASES[6],3000),[.36,.04]);self.assertTrue(np.array_equal(waveform(CASES[6],25000),[0,0]))
    def test_numeric_schema_no_legacy_padding(self):
        c=f.controller();row=candidate_row(c.state)
        self.assertEqual(row.shape,(width(CANDIDATE),));self.assertNotIn('retraction',slices(CANDIDATE))
        c.state.pop('phi')
        with self.assertRaises((ValueError,KeyError)):candidate_row(c.state)
    def test_fractional_integer_rejected(self):
        c=f.controller();r=candidate_row(c.state)
        for key in ('cycle','clear_count','load_count','distal_count','wait_count','last_tick','generation'):
            bad=r.copy();bad[slices(CANDIDATE)[key].start]=.5
            with self.subTest(key=key),self.assertRaises(ValueError):state_from_rows(core(c,0),bad)
    def test_non_boolean_rejected(self):
        c=f.controller();r=candidate_row(c.state)
        for key in ('partial','initialized','admitted','release_veto','positive_nonfoot','range_flags'):
            bad=r.copy();bad[slices(CANDIDATE)[key].start]=2
            with self.subTest(key=key),self.assertRaises(ValueError):state_from_rows(core(c,0),bad)
    def test_candidate_oracle_support(self):self.compare_oracle(4.)
    def test_candidate_oracle_lift(self):self.compare_oracle(.5)
    def test_candidate_oracle_transfer(self):self.compare_oracle(1.5)
    def test_candidate_oracle_land(self):self.compare_oracle(2.5)
    def compare_oracle(self,phase):
        c=f.controller(phase);obs=f.observation(1);before=candidate_state(core(c,0),candidate_row(c.state),np.arange(42).reshape(6,7))
        proposal=c.propose([.2,.2],obs,f.References(),intent=forecast);c.commit(proposal)
        after=candidate_state(core(c,1),candidate_row(c.state),np.arange(42).reshape(6,7))
        verify_candidate(before,after,obs,np.array([.2,.2]),c.binding,f.References())
        broken=deepcopy(after);broken['angles'][5,6]+=.0001
        with self.assertRaises(ValueError):verify_candidate(before,broken,obs,np.array([.2,.2]),c.binding,f.References())
    def test_oracle_continuation_and_reacquire(self):
        c=f.controller(4.);c.step([.2,.2],f.observation(1),f.References(),intent=forecast)
        old=candidate_state(core(c,1),candidate_row(c.state),np.arange(42).reshape(6,7));obs=f.observation(2,loads=[1,2,3,4,5])
        c.step([.2,.2],obs,f.References(),intent=forecast);post=candidate_state(core(c,2),candidate_row(c.state),np.arange(42).reshape(6,7))
        verify_candidate(old,post,obs,np.array([.2,.2]),c.binding,f.References());self.assertEqual(post['modes'][0],'REACQUIRE')
    def test_missing_diagnostics_fails(self):
        c=f.initialize();c.state['diagnostics']={}
        with self.assertRaises(ValueError):candidate_row(c.state)
    def phase_arrays(self):
        phi=np.tile(np.array([6.28,2*np.pi,2*np.pi,2*np.pi,2*np.pi+.001,2*np.pi+.002])[:,None],(1,6));mode=np.tile(np.array([0,0,1,2,2,2])[:,None],(1,6));cycle=np.tile(np.array([0,0,0,1,1,1])[:,None],(1,6));resume=np.zeros_like(mode);wait=np.zeros_like(mode);lag=np.ones_like(phi)*.01
        return phi,mode,cycle,resume,np.full(6,3.),wait,lag
    def test_legal_release_hold_not_intent_strict_increase(self):
        p=realized_partition(*self.phase_arrays(),lo=0,hi=5)
        self.assertTrue(all(not x['invalid_ticks'] for x in p))
    def test_illegal_interior_hold(self):
        args=list(self.phase_arrays());args[0][4:]=2*np.pi+.001
        p=realized_partition(*args,lo=0,hi=5);self.assertTrue(all(x['invalid_ticks'] for x in p))
    def test_cycle_skip_invalid(self):
        args=list(self.phase_arrays());args[2][3:]+=1
        self.assertTrue(any(x['invalid_ticks'] for x in realized_partition(*args,lo=0,hi=5)))
    def test_reacquire_hold_support_interval(self):
        args=list(self.phase_arrays());args[0][:]=4.;args[1][:]=5;args[2][:]=0
        result=realized_partition(*args,lo=0,hi=5);self.assertTrue(all(not p['invalid_ticks'] and not p['swing'] for p in result))
    def test_physical_failure_despite_legal_labels(self):
        partitions=[{'swing':[(20,120)],'stance':[(120,220)],'partials':[],'invalid_ticks':[]} for _ in range(6)]
        ap=np.tile(np.linspace(0,1,240)[:,None],(1,6));height=np.zeros_like(ap);normal=np.ones_like(ap);weighted=normal*100;peak=weighted.copy()
        result=physical_runs(partitions,ap,height,normal,weighted,peak)
        self.assertFalse(result['recovery_passed']);self.assertFalse(result['support_slip_passed'])
    def test_median_ties_preserve_original_failure(self):
        p=[{'swing':[(20,100)],'stance':[(100,200)],'partials':[],'invalid_ticks':[]} for _ in range(6)]
        zeros=np.zeros((240,6));result=physical_runs(p,zeros,zeros,zeros,zeros,zeros)
        self.assertEqual(result['swing_cycles'][0][0]['status'],'fail')
        descending=np.tile(-np.arange(240,dtype=float)[:,None],(1,6))
        result=physical_runs(p,descending,zeros,zeros,zeros,zeros)
        self.assertEqual(result['swing_cycles'][0][0]['status'],'inconclusive')
    def test_independent_realized_quadrature(self):
        n=240;mode=np.zeros((n,6));mode[20:120]=2;cyc=np.zeros_like(mode);phi=np.tile(np.linspace(0,5,n)[:,None],(1,6));ap=phi*.1;h=np.ones_like(phi)*.05;normal=np.zeros_like(phi);normal[120:220]=1.;weighted=np.zeros_like(phi)
        parts=[{'swing':[(20,120)],'stance':[(120,220)],'partials':[],'invalid_ticks':[]} for _ in range(6)]
        # Explicit finite window ending inside an opposite swing makes stance complete.
        mode[220:]=2
        want=physical_runs(parts,ap,h,normal,weighted,weighted);other=independent_realized_gate(phi,mode,cyc,ap,h,normal,weighted,lo=0,hi=239)
        self.assertEqual((want['recovery_passed'],want['support_slip_passed']),other[:2])
    def test_exact_failure_taxonomy(self):
        self.assertEqual(classify(f.ContractError('stall: active gate wait exceeded500'),PROFILE),'controller_infeasible')
        self.assertEqual(classify(f.ContractError('task Cholesky failed'),PROFILE),'integration')
        self.assertEqual(classify(f.ContractError('bad packet'),PROFILE),'integration')
        self.assertEqual(classify(FloatingPointError('nonfinite'),PROFILE),'unsafe')
    def test_pending_allocation_budget(self):
        with tempfile.TemporaryDirectory(dir='/tmp/fly-contact-mechanics-fix1') as d:
            b=Budget(d)
            with self.assertRaises(ResourceStop):b.check(pending=8*1024**3)
            with self.assertRaises(ResourceStop):b.charge('mj_step')
            b.stage='execution';b.caps['mj_step']=1;b.charge('mj_step')
            with self.assertRaises(ResourceStop):b.charge('mj_step')
    def test_stream_failure_retains_exact_prefix(self):
        with tempfile.TemporaryDirectory(dir='/tmp/fly-contact-mechanics-fix1') as d:
            b=Budget(d);c=f.controller();t=panel('development')[1];w=Writers(pathlib.Path(d)/'trial',t,'a'*64,b)
            w.append(0,core(c,0),candidate_row(c.state),[]);w.finish(ValueError('authored late failure'),{'completed_ticks':0,'scheduled_ticks':40000,'missing_remainder':40000,'failure_kind':'integration'})
            records=list(stream_rows(pathlib.Path(d)/'trial/core',CORE,allow_partial=True));self.assertEqual(len(records),1);np.testing.assert_array_equal(records[0][1],core(c,0))
            with self.assertRaises(ValueError):list(stream_rows(pathlib.Path(d)/'trial/core',CORE))
    def test_panel_missing_condition_rejected(self):
        with self.assertRaises(ValueError):panel_admission({},'development')
    def test_failed_remainder_blocks_heldout(self):
        from mechanics_fix1_tests import reports
        values=reports();trial=panel('development')[1]
        values[trial.identity].update(complete=False,retained_completed_ticks=0,missing_ticks=40000,missing_remainder=True,inconclusive=True,candidate_passed=False,all_original_gates_pass=False,realized_passed=False)
        self.assertFalse(panel_admission(values,'development')['passed'])

class AdditionalContracts(unittest.TestCase):
    def test_original_strict_phase_rejects_hold_while_event_partition_keeps_it(self):
        from flyarena.experiments.contact_mechanics_v1.original_metrics import helpers
        _,_,contract=helpers();phase=np.tile(np.arange(25001,dtype=float)[:,None]*.001,(1,6))
        self.assertEqual(contract(phase,True)['failures'],[])
        phase[7001]=phase[7000];self.assertEqual(len(contract(phase,True)['failures']),6)
        self.assertFalse(contract(phase,False)['strict_increment_rule_applied'])
    def test_analyzer_incomplete_has_full_missing_denominator(self):
        from flyarena.experiments.contact_mechanics_v1.verify import analyze_arrays
        trial=panel('development')[1];a=np.zeros((12,6));rot=np.tile(np.eye(3),(12,1,1))
        result=analyze_arrays(trial,{},dict(complete=False,failure_kind='controller_infeasible'),a,a,a,a,a,a,np.zeros((12,3)),rot,None)
        self.assertFalse(result['candidate_passed']);self.assertTrue(result['missing_remainder']);self.assertEqual(result['prefix_rows_checked'],12)
    def test_all_numeric_command_diagnostics_detect_mutations(self):
        c=f.controller(.5);obs=f.observation(1);pre=candidate_state(core(c,0),candidate_row(c.state),np.arange(42).reshape(6,7))
        c.step([.2,.2],obs,f.References(),intent=forecast);post=candidate_state(core(c,1),candidate_row(c.state),np.arange(42).reshape(6,7))
        for name in ('z','correction','requested_increment','limited_increment','before_ball','after_ball','native_reference','body_velocity','body_omega','capture_point','phase_increment','lag','residual_norm','residual_max'):
            bad=deepcopy(post);bad[name].flat[0]+=.0001
            with self.subTest(name=name),self.assertRaises(ValueError):verify_candidate(pre,bad,obs,np.array([.2,.2]),c.binding,f.References())
    def test_saved_review_checks_authored_prefix_without_claiming_science(self):
        from flyarena.experiments.contact_mechanics_v1.verify import independent_saved_review
        from flyarena.experiments.contact_mechanics_v1.io import sha
        with tempfile.TemporaryDirectory(dir='/tmp/fly-contact-mechanics-fix1') as d:
            from mechanics_fix1_tests import prefix
            root=pathlib.Path(d);trial=panel('development')[1];prefix(root,seal='none')
            result=independent_saved_review(root)
            self.assertEqual(result['scheduled_ids'],49);self.assertEqual(result['numeric_metrics_recomputed'],0);self.assertEqual(result['native_calls'],0)
            self.assertEqual(result['prefixes_without_complete_native_verification'][trial.identity]['missing_remainder'],40000)
    def test_pack_per_field_width_is_exact(self):
        with self.assertRaises(ValueError):pack((('a',2),('b',2)),{'a':[1.],'b':[2.,3.,4.]})

    def test_cli_source_check_preserves_all_accepted_files(self):
        from flyarena.experiments.contact_mechanics_v1.__main__ import main
        from unittest.mock import patch
        import contextlib,io
        output=io.StringIO()
        with patch.object(sys,'argv',['contact_mechanics_v1','source-check']),contextlib.redirect_stdout(output):main()
        result=json.loads(output.getvalue());self.assertEqual(result['preserved'],195);self.assertFalse(result['ready'])

    def test_authored_full_array_analysis_requires_both_physical_partitions(self):
        from flyarena.experiments.contact_mechanics_v1.verify import analyze_arrays
        n=40001;k=np.arange(n);theta=np.tile((k*.004)[:,None],(1,6));phase=np.mod(theta,2*np.pi)
        modes=np.where(phase<1,2,np.where(phase<2,3,np.where(phase<3,4,0)))
        realized={'phi':theta,'modes':modes,'cycle':np.floor(theta/(2*np.pi)),'resume_modes':np.zeros_like(theta),'wait_count':np.zeros_like(theta),'lag':np.zeros_like(theta)}
        ap=-np.cos(theta);height=np.where(phase<3,.05,0.);normal=np.where(phase<3,0.,1.);weighted=np.zeros_like(theta)
        position=np.zeros((n,3));position[:,0]=np.clip((k-3000)*DT,0,2.2);rotation=np.tile(np.eye(3),(n,1,1))
        reg={'beta':[3.]*6,'legacy_controller':{'swing_periods_strict_modulo':{leg:[0.,3.] for leg in ('lf','lm','lh','rf','rm','rh')}}}
        trial=panel('development')[3];terminal={'complete':True}
        result=analyze_arrays(trial,reg,terminal,theta,ap,height,normal,weighted,weighted,position,rotation,realized)
        self.assertTrue(result['all_original_gates_pass']);self.assertTrue(result['realized_passed']);self.assertTrue(result['candidate_passed'])
        normal[:]=1.;failed=analyze_arrays(trial,reg,terminal,theta,ap,height,normal,weighted,weighted,position,rotation,realized)
        self.assertFalse(failed['candidate_passed']);self.assertFalse(failed['primary']['recovery_passed']);self.assertFalse(failed['realized']['recovery_passed'])

    def test_attempt_completion_ledger_keeps_failed_calls(self):
        with tempfile.TemporaryDirectory(dir='/tmp/fly-contact-mechanics-fix1') as d:
            budget=Budget(d,caps={'authored_arithmetic':2});budget.stage='execution'
            self.assertEqual(budget.call('authored_arithmetic',lambda:7),7)
            def fail():raise ArithmeticError('authored failure')
            with self.assertRaises(ArithmeticError):budget.call('authored_arithmetic',fail)
            self.assertEqual(budget.attempted['authored_arithmetic'],2);self.assertEqual(budget.completed['authored_arithmetic'],1)
            with self.assertRaises(ResourceStop):budget.call('authored_arithmetic',lambda:9)

if __name__=='__main__':unittest.main()
