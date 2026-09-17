"""FIX1 regressions: authored protocol evidence is not scientific attestation."""
import ast,json,pathlib,tempfile,unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import mechanics_source_tests as s
from flyarena.experiments.contact_mechanics_v1 import verify as v,budget as b,proof,io
from flyarena.experiments.contact_mechanics_v1.control_evidence import control_snapshot,CONTROL_REQUIRED,CPG_FIELDS,REFERENCE_FIELDS
from flyarena.experiments.contact_mechanics_v1.registration import inventory,protocol
from flyarena.experiments.contact_mechanics_v1.io import sha,BudgetEvidence,digest
ROOT=pathlib.Path('/tmp/fly-contact-mechanics-fix1');np=s.np

def reports():
    result={}
    for t in s.panel('development'):
        gates=dict(finite=True,upright=True,stop=True)
        if t.case[1]>0:gates.update({'turn' if t.case[2] else 'straight_yaw':True,'recovery':True,'support_slip':True})
        result[t.identity]=dict(report_schema='contact-mechanics-analysis/v2',trial_id=t.identity,complete=True,all_original_gates_pass=True,
          realized_passed=True,inconclusive=False,controller_failure=False,missing_remainder=False,candidate_passed=True,
          independent_numeric_pass=True,integration_passed=True,retention_passed=True,verification_closure_validated=True,
          scheduled_ticks=40000,retained_completed_ticks=40000,missing_ticks=0,gates=gates,primary=dict(recovery_passed=True,support_slip_passed=True,invalid_interior_phase_episodes=0),
          realized=dict(recovery_passed=True,support_slip_passed=True,phase_valid=True),
          summary={'forward_mean_mm_s':{'straight-008':1.,'straight-02':2.,'straight-04':3.}.get(t.case[0],1.)})
    return result

def replace_json(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')

def prefix(root, *, seal='full', changed_start=False, wrong_time=False):
    """A one-row deliberately failed synthetic protocol; never native proof."""
    trials=[t for stage in ('development','heldout','repeat') for t in s.panel(stage)]
    closure=inventory();s.write(root/'source-closure.json',closure)
    (root/'approved-plan.md').write_bytes((s.ROOT/'docs/contact-mechanics-v1/approved-plan.md').read_bytes())
    pre={'schema':'contact-mechanics-preregistration/v1','source_root':str(s.ROOT),'source':closure,
      'trials':[t.record() for t in trials],'dt':s.DT,'profiles':[s.CONTROL,s.PROFILE],'cases':[list(c) for c in s.CASES],
      'plan_sha256':sha(root/'approved-plan.md'),'dependencies':{},'model_locator':{'registered_model_mjb_sha256':s.MODEL_SHA}}
    pre.update(protocol())
    s.write(root/'preregistration.json',pre);s.write(root/'preflight-terminal.json',{'passed':True,'authored_protocol_only':True})
    binding=s.replace(s.f.binding(),asset_hash=digest({}),input_hash=digest({'cases':pre['cases'],'active':[3000,25000],'dt':s.DT}))
    c=s.f.Controller(binding,np.full(6,4.),np.zeros((6,7)),np.ones(6,dtype=bool),('MT19937',np.ones(624,dtype=np.uint32),0,0,0.));row=s.core(c,0);reset={k:s.f.encode(s.unpack(s.CORE,row)[k]) for k in ('qpos','qvel','ctrl','theta','magnitude')}
    for seed in (42,43,31042,31043):s.write(root/f'reset-{seed}.json',reset)
    reg={'schema':'contact-mechanics-registration/v1','binding':s.f.encode(binding.__dict__),
      'preregistration_sha256':sha(root/'preregistration.json'),'source_closure_sha256':sha(root/'source-closure.json'),
      'preflight_sha256':sha(root/'preflight-terminal.json'),'model_sha256':s.MODEL_SHA,'model_digest':'a'*64,
      'asset_hash':digest({}),'input_hash':digest({'cases':pre['cases'],'active':[3000,25000],'dt':s.DT}),
      'experiment_binding':{'preregistration':sha(root/'preregistration.json'),'model':'a'*64},
      'resets':{str(seed):sha(root/f'reset-{seed}.json') for seed in (42,43,31042,31043)}}
    s.write(root/'registration.json',reg);anchor=sha(root/'registration.json');trial=s.panel('development')[1];dest=root/trial.stage/trial.name
    statuses={t.identity:{'status':'unstarted_due_stop'} for t in trials};statuses[trial.identity]={'status':'failed_incomplete'}
    s.write(root/'panel-terminal.json',{'registration_sha256':anchor,'trials':statuses})
    budget=s.Budget(root);meta=proof.metadata(root,trial,reg);writer=s.Writers(dest,trial,anchor,budget,metadata=meta)
    if wrong_time:row[s.slices(s.CORE)['time']]=123.
    writer.append(0,row,s.candidate_row(c.state),[])
    writer.finish(ValueError('authored integration failure'),dict(completed_ticks=0,scheduled_ticks=40000,missing_remainder=40000,failure_kind='integration',registration_sha256=anchor))
    s.write(dest/'initial-controller.json',c.checkpoint())
    derived=BudgetEvidence(dest/'derived',s.width(v.DERIVED),metadata=meta,budget=budget)
    derived.append(0,np.zeros(s.width(v.DERIVED)));derived.finish();derived.release()
    a=np.zeros((1,6));result=v.analyze_arrays(trial,{},s.read(dest/'trial-terminal.json'),a,a,a,a,a,a,np.zeros((1,3)),np.zeros((1,3,3)),None)
    result.update(independent_numeric_pass=True,integration_passed=True,retention_passed=True,endpoint_rows_checked=1,contacts_checked=0,active_actions_checked=0)
    s.write(dest/'analysis-verification.json',result)
    if seal!='none':
        proof.write_seal(root,trial,reg,result);p=dest/'numeric-verification-seal.json';value=s.read(p)
        if seal=='empty':value['files']={}
        if seal=='missing_flag':value.pop('single_native_reconstruction')
        if seal=='false_flag':value['single_native_reconstruction']=False
        replace_json(p,value)
    if changed_start:
        p=dest/'core/start.json';value=s.read(p);value['seed']=999;replace_json(p,value)
    return dest

class ReviewContracts(unittest.TestCase):
    def assert_not_admitted(self, report):
        try:result=v.panel_admission(report,'development')
        except (ValueError,KeyError):return
        self.assertFalse(result['passed'])

    def test_valid_full_panel_admitted(self):
        self.assertTrue(v.panel_admission(reports(),'development')['passed'])

    def test_unverified_comparator_rejected(self):
        r=reports();r[s.panel('development')[0].identity]['independent_numeric_pass']=False
        self.assert_not_admitted(r)

    def test_missing_comparator_report_rejected(self):
        r=reports();r[s.panel('development')[0].identity]={}
        self.assert_not_admitted(r)

    def test_wrong_report_trial_identity_rejected(self):
        r=reports();r[s.panel('development')[1].identity]['trial_id']='wrong/identity'
        self.assert_not_admitted(r)

    def test_incomplete_candidate_with_stale_pass_flag_rejected(self):
        r=reports();r[s.panel('development')[1].identity].update(complete=False,missing_remainder=True)
        self.assert_not_admitted(r)

    def test_original_failure_cannot_be_waived_by_stale_pass_flag(self):
        r=reports();r[s.panel('development')[1].identity]['all_original_gates_pass']=False
        self.assert_not_admitted(r)

    def test_failed_comparator_physical_metric_is_reported_not_candidate_waiver(self):
        r=reports();r[s.panel('development')[0].identity].update(candidate_passed=False,all_original_gates_pass=False);r[s.panel('development')[0].identity]['gates']['upright']=False
        self.assertTrue(v.panel_admission(r,'development')['passed'])

    def test_missing_exact_panel_condition_rejected(self):
        r=reports();r.pop(s.panel('development')[0].identity)
        with self.assertRaises(ValueError):v.panel_admission(r,'development')

    def test_failed_dose_rejected(self):
        r=reports()
        for t in s.panel('development'):
            if t.case[0]=='straight-04':r[t.identity]['summary']['forward_mean_mm_s']=2.
        self.assert_not_admitted(r)

    def run_prefix(self, **kw):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            root=pathlib.Path(d);prefix(root,**kw);return v.independent_saved_review(root)

    def test_sealed_authored_prefix_fixture_is_readable(self):
        r=self.run_prefix();self.assertEqual(r['numeric_metrics_recomputed'],1)
        self.assertEqual(r['admission'],{});self.assertEqual(r['native_calls'],0)

    def test_unsealed_prefix_has_no_native_attestation(self):
        r=self.run_prefix(seal='none');self.assertEqual(r['numeric_metrics_recomputed'],0)
        self.assertEqual(len(r['prefixes_without_complete_native_verification']),1)

    def test_empty_native_seal_manifest_rejected(self):
        with self.assertRaises((ValueError,KeyError)):self.run_prefix(seal='empty')

    def test_missing_native_pass_attestation_rejected(self):
        with self.assertRaises((ValueError,KeyError)):self.run_prefix(seal='missing_flag')

    def test_false_native_pass_attestation_rejected(self):
        with self.assertRaises((ValueError,KeyError)):self.run_prefix(seal='false_flag')

    def test_changed_stream_seed_identity_rejected(self):
        with self.assertRaises((ValueError,KeyError)):self.run_prefix(changed_start=True)

    def test_wrong_saved_physical_time_rejected(self):
        with self.assertRaises((ValueError,KeyError)):self.run_prefix(wrong_time=True)

    def test_pending_allocation_respects_remaining_rss(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d);budget.stage='execution';rss=int(1.9*1024**3)
            with patch.object(b.resource,'getrusage',return_value=SimpleNamespace(ru_maxrss=rss)),patch.object(b.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)):
                with self.assertRaises(b.ResourceStop):budget.check(pending=int(.2*1024**3))

    def test_forecast_sums_disjoint_remaining_work(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d,start=0);budget.stage='execution'
            with patch.object(b.time,'time',return_value=0):
                budget.forecast('runtime',4000,1,1)
                with self.assertRaises(b.ResourceStop):budget.forecast('reconstruction',4000,1,1)

    def test_all_dynamic_calls_forbidden_during_preflight(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d)
            for name in ('mj_step','candidate_active','candidate_propose','control_active','independent_candidate','cpg_step','candidate_solve','candidate_shared_fit'):
                with self.subTest(name=name),self.assertRaises(b.ResourceStop):budget.charge(name)
            self.assertEqual(budget.attempted,{})

    def test_unregistered_calls_and_unearned_completion_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d);budget.stage='execution'
            with self.assertRaises(b.ResourceStop):budget.charge('unknown_native_call')
            with self.assertRaises(ValueError):budget.complete('mj_step')

class GridContracts(unittest.TestCase):
    def contact_rows(self, specifications):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            root=pathlib.Path(d);budget=s.Budget(root)
            writer=BudgetEvidence(root/'contacts',s.width(s.CONTACT),metadata={},budget=budget)
            for tick,index,start,end in specifications:
                values={key:np.zeros(size) for key,size in s.CONTACT};values.update(index=index,leg=-1,interval_start=start,interval_end=end)
                writer.append(tick,s.pack(s.CONTACT,values))
            writer.finish();get,done=v.contacts_by_tick(root);rows=get(1)
            return rows,done()

    def test_sparse_native_indices_preserved_in_order(self):
        rows,done=self.contact_rows([(1,2,0,1),(1,7,0,1)])
        self.assertTrue(done);self.assertEqual([s.unpack(s.CONTACT,r)['index'][0] for r in rows],[2.,7.])

    def test_duplicate_contact_index_rejected(self):
        with self.assertRaises(ValueError):self.contact_rows([(1,2,0,1),(1,2,0,1)])

    def test_nonmonotonic_native_contact_order_rejected(self):
        with self.assertRaises(ValueError):self.contact_rows([(1,7,0,1),(1,2,0,1)])

    def test_fractional_contact_identity_rejected(self):
        with self.assertRaises(ValueError):self.contact_rows([(1,2.5,0,1)])

    def test_wrong_completed_interval_rejected(self):
        with self.assertRaises(ValueError):self.contact_rows([(1,2,1,2)])

    def test_negative_native_contact_index_rejected(self):
        with self.assertRaises(ValueError):self.contact_rows([(1,-1,0,1)])

    def test_513_contact_rows_rejected_without_truncation(self):
        with self.assertRaises(ValueError):self.contact_rows([(1,i,0,1) for i in range(513)])

    def test_missing_endpoint_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            root=pathlib.Path(d);c=s.f.controller();w=s.Writers(root/'trial',s.panel('development')[1],'a'*64,s.Budget(root))
            w.append(0,s.core(c,0),s.candidate_row(c.state),[]);w.append(2,s.core(c,2),s.candidate_row(c.state),[])
            w.finish(ValueError('authored prefix'),{'completed_ticks':2,'scheduled_ticks':40000,'missing_remainder':39998,'failure_kind':'integration'})
            with self.assertRaises(ValueError):list(v.paired_rows(root/'trial',s.PROFILE))

    def test_completed_prefix_cycles_remain_analyzed_on_late_failure(self):
        n=12001;k=np.arange(n);theta=np.tile((k*.004)[:,None],(1,6));phase=np.mod(theta,2*np.pi)
        realized=dict(phi=theta,modes=np.where(phase<1,2,np.where(phase<2,3,np.where(phase<3,4,0))),cycle=np.floor(theta/(2*np.pi)),resume_modes=np.zeros_like(theta),wait_count=np.zeros_like(theta),lag=np.zeros_like(theta))
        reg={'beta':[3.]*6,'legacy_controller':{'swing_periods_strict_modulo':{leg:[0.,3.] for leg in ('lf','lm','lh','rf','rm','rh')}}}
        result=v.analyze_arrays(s.panel('development')[3],reg,{'complete':False,'failure_kind':'controller_infeasible'},theta,-np.cos(theta),np.where(phase<3,.05,0.),np.where(phase<3,0.,1.),np.zeros_like(theta),np.zeros_like(theta),np.zeros((n,3)),np.tile(np.eye(3),(n,1,1)),realized)
        self.assertFalse(result['candidate_passed']);self.assertTrue(result['missing_remainder'])
        self.assertIn('primary',result,'Completed prefix cycles and partials must remain classified')
        self.assertIn('realized',result,'Failed prefix must preserve the realized physical partition')

class CorrectionContracts(unittest.TestCase):
    def test_inventory_contains_all_195_accepted_payloads(self):
        accepted=s.read(s.ROOT/'docs/contact-mechanics-v1/accepted-source-manifest.json');actual=inventory()
        self.assertEqual(len(accepted),195);self.assertTrue(set(accepted)<=set(actual))
        self.assertTrue(all(actual[k]==v['sha256'] for k,v in accepted.items()))

    def test_control_objects_have_complete_numeric_adapter(self):
        class Steps:
            legs=('lf','lm','lh','rf','rm','rh');dofs_per_leg=(('coxa','roll','x'),)
        class RNG:
            def get_state(self):return ('MT19937',np.arange(624,dtype=np.uint32),3,0,0.)
        steps=Steps();steps.__dict__.update(_length=3,_timestep=.01,duration=.03,
          neutral_pos={leg:np.zeros((7,1)) for leg in steps.legs},swing_period={leg:np.array([0.,3.]) for leg in steps.legs},
          _psi_funcs={leg:SimpleNamespace(x=np.array([0.,1.,2.]),c=np.zeros((4,2,7)),axis=1,extrapolate=True) for leg in steps.legs})
        cp={key:np.ones(6) for key in CPG_FIELDS};cp.update(timestep=s.DT,num_cpgs=6,coupling_weights=np.eye(6),phase_biases=np.eye(6),random_state=RNG())
        state={key:np.zeros(6) for key in CONTROL_REQUIRED};state.update(legs=steps.legs,timestep=s.DT,last_info={},model_hash='a'*64,observation_version='authored',last_observation_tick=-1,
          output_dof_order=None,cpg_network=SimpleNamespace(**cp),preprogrammed_steps=steps)
        control=SimpleNamespace(**state)
        tree=ast.parse((s.ROOT/'src/flyarena/experiments/cadence_v16.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AllocationHybridController');method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='checkpoint')
        scope={'deepcopy':deepcopy,'STATE_VERSION':'authored'};exec(compile(ast.Module(body=[method],type_ignores=[]),'authored_old_checkpoint.py','exec'),scope)
        with self.assertRaises(s.f.ContractError):s.f.encode(scope['checkpoint'](control))
        identity={key:'a'*64 for key in ('asset_hash','model_digest','input_hash')};value=control_snapshot(control,identity)
        self.assertFalse(value['portable_native_restore']);self.assertEqual(set(value['controller']),set(CONTROL_REQUIRED))
        self.assertEqual(s.f.decode(value['cpg'])['rng'][2],3)
        before=digest(value);control.cpg_network.curr_phases[0]+=1
        self.assertNotEqual(before,digest(control_snapshot(control,identity)))
        control.unknown_object=object()
        with self.assertRaises(s.f.ContractError):control_snapshot(control,identity)

    def test_compound_release_reached_by_accepted_proposals(self):
        c=s.f.controller(2*np.pi-.00001);records=[]
        for tick in range(1,34):
            obs=s.f.observation(tick,loads=([1,2,3,4,5] if tick==3 else None),nonfoot=tick<=2)
            c.step([.2,.2],obs,s.f.References(),intent=s.f.fixture_intent)
            records.append(s.unpack(s.CANDIDATE,s.candidate_row(c.state)))
        self.assertEqual(records[-2]['modes'][0],s.MODES.index('REACQUIRE'))
        self.assertEqual(records[-2]['resume_modes'][0],s.MODES.index('RELEASE_WAIT'))
        self.assertEqual(records[-1]['modes'][0],s.MODES.index('LIFT'))
        self.assertEqual(records[-1]['cycle'][0],1)
        data={key:np.asarray([r[key] for r in records]) for key in v.REALIZED_FIELDS}
        def partition(values):return s.realized_partition(values['phi'],values['modes'],values['cycle'],values['resume_modes'],np.full(6,3.),values['wait_count'],values['lag'],lo=0,hi=len(records)-1,admitted=values['admitted'],distal_count=values['distal_count'],load_count=values['load_count'])
        self.assertFalse(partition(data)[0]['invalid_ticks'])
        for key,value in [('admitted',0),('distal_count',1),('load_count',29),('cycle',2),('wait_count',1)]:
            bad=deepcopy(data);bad[key][-1,0]=value
            with self.subTest(key=key):self.assertIn(len(records)-1,partition(bad)[0]['invalid_ticks'])
        bad=deepcopy(data);bad['resume_modes'][-2,0]=s.MODES.index('SUPPORT');self.assertIn(len(records)-1,partition(bad)[0]['invalid_ticks'])

    def test_phase_failure_separate_from_physical_agreement(self):
        n=12001;k=np.arange(n);theta=np.tile((k*.004)[:,None],(1,6));phase=theta%(2*np.pi)
        real=dict(phi=theta.copy(),modes=np.where(phase<1,2,np.where(phase<2,3,np.where(phase<3,4,0))),cycle=np.floor(theta/(2*np.pi)),resume_modes=np.zeros_like(theta),wait_count=np.zeros_like(theta),lag=np.zeros_like(theta))
        real['wait_count'][7000,0]=501
        reg={'beta':[3.]*6,'legacy_controller':{'swing_periods_strict_modulo':{leg:[0.,3.] for leg in ('lf','lm','lh','rf','rm','rh')}}}
        value=v.analyze_arrays(s.panel('development')[3],reg,{'complete':False,'failure_kind':'controller_infeasible'},theta,-np.cos(theta),np.where(phase<3,.05,0.),np.where(phase<3,0.,1.),np.zeros_like(theta),np.zeros_like(theta),np.zeros((n,3)),np.tile(np.eye(3),(n,1,1)),real)
        self.assertFalse(value['realized']['phase_valid']);self.assertTrue(value['realized']['recovery_passed']);self.assertTrue(value['realized']['support_slip_passed'])
        self.assertEqual(value['retained_active_window'],[6000,12000]);self.assertEqual(value['missing_ticks'],28000)
        self.assertTrue(value['primary']['swing_cycles'][0]);self.assertTrue(value['realized']['swing_cycles'][0]);self.assertTrue(value['realized']['phase_partitions'][0]['partials'])

    def test_flush_failure_retains_checked_emergency_prefix(self):
        for primary in (None,ValueError('authored primary')):
            with self.subTest(primary=primary),tempfile.TemporaryDirectory(dir=ROOT) as d:
                root=pathlib.Path(d);trial=s.panel('development')[1];budget=s.Budget(root);writer=s.Writers(root/'trial',trial,'a'*64,budget);c=s.f.controller();row=s.core(c,0)
                writer.append(0,row,s.candidate_row(c.state),[])
                with patch.object(writer.items['core'],'flush',side_effect=OSError('authored final flush')):
                    with self.assertRaises(RuntimeError):writer.finish(primary,dict(completed_ticks=0,scheduled_ticks=40000,missing_remainder=40000,failure_kind='integration' if primary else None))
                terminal=s.read(root/'trial/trial-terminal.json');self.assertFalse(terminal['complete']);self.assertFalse(terminal['retention_passed']);self.assertEqual(terminal['failure_kind'],'retention');self.assertEqual(s.classify(io.RetentionError('authored'),s.PROFILE),'retention')
                self.assertEqual(terminal['failure'] is None,primary is None);self.assertTrue(terminal['retention_failures']);self.assertEqual(terminal['retained_rows']['core'],1)
                rows=list(s.stream_rows(root/'trial/core',s.CORE,allow_partial=True));self.assertEqual(len(rows),1);np.testing.assert_array_equal(rows[0][1],row)
                self.assertEqual(budget.pending_buffers,0)
                with self.assertRaises(ValueError):list(s.stream_rows(root/'trial/core',s.CORE))
                with (root/'trial/core/emergency-prefix.npz').open('ab') as handle:handle.write(b'changed')
                with self.assertRaises(ValueError):list(s.stream_rows(root/'trial/core',s.CORE,allow_partial=True))

    def test_required_secondary_snapshot_failure_is_retention_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            trial=s.panel('development')[1];writer=s.Writers(pathlib.Path(d)/'trial',trial,'a'*64,s.Budget(d))
            with self.assertRaises(RuntimeError):writer.finish(ValueError('primary'),dict(completed_ticks=0,scheduled_ticks=40000,missing_remainder=40000,failure_kind='integration',secondary_failures=[{'stage':'failure_snapshot','message':'authored snapshot error'}]))
            t=s.read(pathlib.Path(d)/'trial/trial-terminal.json');self.assertFalse(t['retention_passed']);self.assertEqual(t['failure_kind'],'retention');self.assertEqual(t['primary_failure_kind'],'integration');self.assertEqual(t['failure']['message'],'primary')

    def test_partial_writer_initialization_finalizes_opened_streams(self):
        real=io.BudgetEvidence;calls=[]
        def construct(*args,**kw):
            calls.append(args[0].name)
            if len(calls)==2:raise OSError('authored second stream initialization')
            return real(*args,**kw)
        with tempfile.TemporaryDirectory(dir=ROOT) as d,patch.object(io,'BudgetEvidence',side_effect=construct):
            dest=pathlib.Path(d)/'trial';budget=s.Budget(d)
            with self.assertRaises(RuntimeError):s.Writers(dest,s.panel('development')[1],'a'*64,budget)
            t=s.read(dest/'trial-terminal.json');self.assertFalse(t['complete']);self.assertFalse(t['retention_passed']);self.assertEqual(t['streams']['core']['initialized_rows'],0);self.assertEqual(budget.pending_buffers,0)

    def test_disk_buffer_reserve_does_not_count_as_new_memory(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d);budget.stage='execution';budget.pending_buffers=int(.2*1024**3)
            with patch.object(b.resource,'getrusage',return_value=SimpleNamespace(ru_maxrss=int(1.9*1024**3))),patch.object(b.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)):
                self.assertEqual(budget.check(pending_disk=int(.2*1024**3))['pending_memory_bytes'],0)

    def test_projection_unknowns_maxima_reserve_and_stop_receipt(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d,patch.object(b.time,'time',return_value=0):
            budget=b.Budget(d,start=0);budget.stage='execution';budget.set_remaining({'runtime':1,'reconstruction':1,'analysis_finalization':1})
            self.assertEqual(set(budget.projection()['unknown_categories']),set(budget.remaining))
            budget.forecast('runtime',4000,1,1);budget.forecast('runtime',1,1,1);self.assertEqual(budget.rates['runtime'],4000)
            budget.note_finalization(40);self.assertEqual(budget.finalization_reserve(),80)
            with self.assertRaises(b.ResourceStop):budget.forecast('reconstruction',4000,1,1)
            with patch.object(budget,'check',side_effect=b.ResourceStop('authored stop')):budget.persist()
            report=s.read(pathlib.Path(d)/'resource-terminal.json');self.assertEqual(report['projection']['known_total_seconds'],16000)

class ClosureAndSetupContracts(unittest.TestCase):
    def test_mutated_closure_components_rejected(self):
        mutations=[('numeric-verification-seal.json',lambda x:x['files'].pop('trial-terminal.json')),
          ('numeric-verification-seal.json',lambda x:x['coverage'].update(endpoint_rows_checked=2)),
          ('numeric-verification-seal.json',lambda x:x['context'].update(reset_sha256='f'*64)),
          ('analysis-verification.json',lambda x:x.update(independent_numeric_pass=False)),
          ('trial-terminal.json',lambda x:x.update(complete=True)),
          ('initial-controller.json',lambda x:x.update(binding='wrong')),
          ('core/terminal.json',lambda x:x.update(initialized_rows=2))]
        for relative,mutate in mutations:
            with self.subTest(relative=relative),tempfile.TemporaryDirectory(dir=ROOT) as d:
                root=pathlib.Path(d);dest=prefix(root);path=dest/relative;value=s.read(path);mutate(value);replace_json(path,value)
                with self.assertRaises((ValueError,KeyError)):v.independent_saved_review(root)

    def test_changed_core_with_unchanged_derived_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            root=pathlib.Path(d);dest=prefix(root);path=dest/'core/chunk-00000.npz'
            with np.load(path,allow_pickle=False) as archive:ticks=archive['ticks'].copy();values=archive['values'].copy()
            values[0,s.slices(s.CORE)['qpos'].start]=123.
            with path.open('wb') as handle:np.savez_compressed(handle,ticks=ticks,values=values)
            with self.assertRaises(ValueError):v.independent_saved_review(root)

    def test_registration_plan_source_reset_binding_mutations_rejected(self):
        for filename,mutate in [('registration.json',lambda x:x.update(experiment_binding={})),
            ('registration.json',lambda x:x.update(asset_hash='e'*64)),
            ('preregistration.json',lambda x:x.update(plan_sha256='f'*64)),
            ('preregistration.json',lambda x:x['limits'].update(physics_steps=2600000)),
            ('source-closure.json',lambda x:x.pop('README.md')),
            ('reset-42.json',lambda x:x.update(qpos=[])),
            ('panel-terminal.json',lambda x:x['trials'].pop(s.panel('development')[0].identity))]:
            with self.subTest(filename=filename),tempfile.TemporaryDirectory(dir=ROOT) as d:
                root=pathlib.Path(d);prefix(root);path=root/filename;value=s.read(path);mutate(value);replace_json(path,value)
                with self.assertRaises((ValueError,KeyError)):v.independent_saved_review(root)

    def test_fractional_physical_clock_rejected(self):
        trial=s.panel('development')[1];c=s.f.controller();state=s.candidate_row(c.state)
        for name in ('action_tick','observation_tick','interval_present','contact_offset','contact_count'):
            row=s.core(c,0);row[s.slices(s.CORE)[name]]=.5
            with self.subTest(name=name),self.assertRaises(ValueError):proof.check_core(trial,0,row,state,0,0)

    def test_factory_and_initial_serialization_failures_finalize(self):
        tree=ast.parse((s.ROOT/'src/flyarena/experiments/contact_mechanics_v1/runtime.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_trial')
        # Only the integration exception/finalization boundary executes; every science dependency is an authored stub.
        fn.body=[n for n in fn.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
        for at in ('factory','serialization'):
            with self.subTest(at=at),tempfile.TemporaryDirectory(dir=ROOT) as d:
                root=pathlib.Path(d);s.write(root/'registration.json',{});s.write(root/'reset-42.json',{})
                data=SimpleNamespace(qpos=np.zeros(73),qvel=np.zeros(72),qacc=np.zeros(72),qfrc_actuator=np.zeros(72),ctrl=np.zeros(48),actuator_force=np.zeros(48))
                body=SimpleNamespace(tick=0,data=data,model=object(),controllers=[object()]);reg={'model_digest':'a'*64,'resets':{'42':sha(root/'reset-42.json')},'binding':s.f.encode(s.f.binding().__dict__),'asset_hash':'b'*64,'input_hash':'c'*64}
                def make(*args):
                    if at=='factory':raise ValueError('authored factory failure')
                    return body
                def snapshot(*args):raise ValueError('authored serialization failure')
                scope={'Path':pathlib.Path,'time':b.time,'np':np,'validate':lambda *a,**k:None,'make_body':make,'model_digest':lambda m:'a'*64,
                  'sha':sha,'reset_record':lambda b:{},'read':s.read,'PROFILE':s.PROFILE,'Binding':s.f.Binding,'decode':s.f.decode,'encode':s.f.encode,
                  'Writers':s.Writers,'metadata':lambda *a:{},'control_snapshot':snapshot,'write':s.write,'classify':s.classify,
                  'export_failure':lambda *a:None}
                exec(compile(ast.Module(body=[fn],type_ignores=[]),'authored_run_trial_boundary.py','exec'),scope)
                trial=s.panel('development')[0]
                with self.assertRaisesRegex(ValueError,'authored '+at):scope['run_trial'](root,trial,reg,s.Budget(root),{})
                terminal=s.read(root/trial.stage/trial.name/'trial-terminal.json');self.assertFalse(terminal['complete']);self.assertTrue(terminal['setup_failed']);self.assertEqual(terminal['completed_ticks'],0)
                if at=='serialization':self.assertEqual(set(terminal['streams']),{'core','contacts','state'});self.assertTrue(all(t['initialized_rows']==0 for t in terminal['streams'].values()))
                else:self.assertFalse(terminal['retention_passed']);self.assertEqual(terminal['failure_kind'],'retention');self.assertEqual(s.classify(io.RetentionError('authored'),s.PROFILE),'retention')

    def test_native_data_pending_allocation_stops_before_authored_constructor(self):
        dimensions={name:1 for name in b.DATA_ELEMENT_MULTIPLIERS};dimensions.update(nplugin=0,narena=int(.1*1024**3));model=SimpleNamespace(**dimensions)
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d);budget.stage='execution';called=[]
            with patch.object(b.resource,'getrusage',return_value=SimpleNamespace(ru_maxrss=int(1.9*1024**3))),patch.object(b.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)):
                with self.assertRaises(b.ResourceStop):budget.call('MjData',lambda m:called.append(True),model)
            self.assertEqual(called,[]);self.assertEqual(budget.attempted,{})

    def test_control_observation_accounting_uses_all_three_families(self):
        self.assertEqual(b.LEAF_CAPS['mj_contactForce'],512*b.N+512*(16*40001+b.AV));self.assertEqual(b.LEAF_CAPS['control_observation'],16*40001+b.AV)
        tree=ast.parse((s.ROOT/'src/flyarena/experiments/contact_mechanics_v1/budget.py').read_text());fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='observation')
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            budget=b.Budget(d);budget.stage='execution'
            def reader(cls,sim,*args,**kw):
                for i in range(int(sim.mj_data.ncon)):budget.call('mj_contactForce',lambda:None)
            scope={'np':np,'self':budget,'descriptor':SimpleNamespace(__func__=reader),'ResourceStop':b.ResourceStop}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'authored_observation_wrapper.py','exec'),scope)
            sim=SimpleNamespace(mj_data=SimpleNamespace(ncon=2,contact=SimpleNamespace(geom1=np.array([1,2]),geom2=np.array([30,30]))),_internal_ground_geom_ids=[30])
            for family in ('row0','active_preaction','endpoint'):scope['observation'](object,sim)
            # Recorded completed contacts are a separate leaf family.
            for i in range(2):budget.call('mj_contactForce',lambda:None)
            self.assertEqual(budget.attempted['control_observation'],3);self.assertEqual(budget.attempted['mj_contactForce'],8)
            sim.mj_data.ncon=513;sim.mj_data.contact=SimpleNamespace(geom1=np.ones(513),geom2=np.full(513,30))
            with self.assertRaises(b.ResourceStop):scope['observation'](object,sim)
            self.assertEqual(budget.attempted['control_observation'],3)

    def test_inconsistent_original_and_realized_gate_evidence_rejected(self):
        for field,change in [('primary',{'recovery_passed':False}),('realized',{'phase_valid':False})]:
            values=reports();trial=s.panel('development')[3];values[trial.identity][field].update(change)
            with self.subTest(field=field),self.assertRaises(ValueError):v.panel_admission(values,'development')

    def test_ledger_caps_hashes_and_data_array_coefficients(self):
        import re,collections
        table=s.read(s.ROOT/'docs/contact-mechanics-v1/leaf-call-table.json')
        self.assertEqual({k:v['maximum_attempts'] for k,v in table['leaves'].items()},b.LEAF_CAPS)
        for path,record in table['source_files'].items():self.assertEqual(sha(path),record['sha256'],path)
        provenance=table['data_allocation_provenance'];header=pathlib.Path(provenance['header']);self.assertEqual(sha(header),provenance['header_sha256'])
        section=header.read_text().split('#define MJDATA_POINTERS ',1)[1].split('// macro for annotating',1)[0]
        rows=re.findall(r'X(?:NV)?\s*\(\s*(\w+),\s*(\w+),\s*(\w+),\s*(\d+)\s*\)',section);self.assertEqual(len(rows),92)
        coefficients=collections.Counter()
        for typ,name,dim,n in rows:self.assertIn(typ,('mjtNum','mjtBool','int','uintptr_t'));coefficients[dim]+=int(n)
        self.assertEqual(dict(coefficients),b.DATA_ELEMENT_MULTIPLIERS)
