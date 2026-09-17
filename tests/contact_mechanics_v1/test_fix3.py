"""Pure forwarding/accounting regressions; guard dependencies are authored stand-ins."""
import ast,contextlib,inspect,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
import mechanics_source_tests as s
from flyarena.experiments.contact_mechanics_v1 import budget as b,io
import flyarena.experiments.contact_v1 as contact_package

ROOT=pathlib.Path('/tmp/fly-contact-mechanics-fix3')

class ForwardingContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.temp.cleanup)
        self.budget=b.Budget(self.temp.name,caps={'authored':2})

    def test_old_signature_reproduces_collision_before_leaf_or_charge(self):
        tree=ast.parse(inspect.getsource(b))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='call')
        call.args.args=call.args.posonlyargs+call.args.args;call.args.posonlyargs=[]
        scope={'time':b.time};exec(compile(ast.Module(body=[call],type_ignores=[]),'old_budget_signature.py','exec'),scope)
        old=types.MethodType(scope['call'],self.budget);seen=[]
        with self.assertRaisesRegex(TypeError,"multiple values for argument 'name'"):
            old('authored',lambda **kw:seen.append(kw),name='neutral',time=0)
        self.assertEqual(seen,[]);self.assertEqual(self.budget.attempted,{})
        self.assertEqual(self.budget.completed,{});self.assertEqual(self.budget.timings,{})

    def test_all_internal_parameter_keywords_and_positional_payload_forward_unchanged(self):
        sentinel=object();seen=[];kwargs={'name':'neutral','time':0,'fn':sentinel,'self':sentinel}
        def leaf(*args,**kw):
            seen.append((args,kw));self.assertEqual(self.budget.attempted,{'authored':1})
            self.assertEqual(self.budget.completed,{});return sentinel
        with patch.object(b.time,'monotonic',side_effect=[10.,10.25]):
            result=self.budget.call('authored',leaf,sentinel,**kwargs)
        self.assertIs(result,sentinel);self.assertEqual(seen,[((sentinel,),kwargs)])
        self.assertEqual(self.budget.completed,{'authored':1})
        self.assertEqual(self.budget.timings,{'authored':{'calls':1,'seconds':.25,'max_seconds':.25}})

    def test_failure_propagates_same_exception_and_retains_attempt_and_timing(self):
        failure=KeyboardInterrupt('authored leaf failure');seen=[]
        def leaf(**kw):seen.append(kw);raise failure
        with patch.object(b.time,'monotonic',side_effect=[20.,20.5]):
            with self.assertRaises(KeyboardInterrupt) as caught:self.budget.call('authored',leaf,name='neutral')
        self.assertIs(caught.exception,failure);self.assertEqual(seen,[{'name':'neutral'}])
        self.assertEqual(self.budget.attempted,{'authored':1});self.assertEqual(self.budget.completed,{})
        self.assertEqual(self.budget.timings,{'authored':{'calls':1,'seconds':.5,'max_seconds':.5}})

    def test_cap_and_unregistered_reject_before_forwarded_leaf(self):
        seen=[];self.budget.caps['authored']=1
        self.budget.call('authored',lambda **kw:seen.append(kw),name='first')
        timing=self.budget.timings['authored'].copy()
        for family in ('authored','unregistered'):
            with self.subTest(family=family),self.assertRaises(b.ResourceStop):
                self.budget.call(family,lambda **kw:seen.append(kw),name='blocked')
        self.assertEqual(seen,[{'name':'first'}]);self.assertEqual(self.budget.attempted,{'authored':1})
        self.assertEqual(self.budget.completed,{'authored':1});self.assertEqual(self.budget.timings['authored'],timing)

    def test_preflight_dynamics_rejection_still_precedes_leaf(self):
        self.budget.caps={'cpg_step':1};seen=[]
        with self.assertRaisesRegex(b.ResourceStop,'forbidden preflight'):
            self.budget.call('cpg_step',lambda **kw:seen.append(kw),name='blocked')
        self.assertEqual(seen,[]);self.assertEqual(self.budget.attempted,{})
        self.assertEqual(self.budget.completed,{});self.assertEqual(self.budget.timings,{})

    def test_internal_calls_supply_category_and_callable_positionally(self):
        signature=inspect.signature(b.Budget.call)
        for name in ('self','name','fn'):self.assertEqual(signature.parameters[name].kind,inspect.Parameter.POSITIONAL_ONLY)
        sites=[]
        for path in (s.ROOT/'src/flyarena/experiments/contact_mechanics_v1').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='call':
                    sites.append((path.name,node.lineno));self.assertGreaterEqual(len(node.args),2)
                    self.assertFalse(any(isinstance(a,ast.Starred) for a in node.args[:2]))
                    self.assertFalse(any(kw.arg in ('name','fn','self') for kw in node.keywords))
        self.assertGreaterEqual(len(sites),10)

    def exercise_native_guard(self,fail):
        # Exercise the actual context manager against Python-only modules/classes.
        # No installed scientific package is imported or executed.
        modules={};records=[]
        def module(name):
            if name in modules:return modules[name]
            value=types.ModuleType(name);value.__path__=[];modules[name]=value
            if '.' in name:
                parent,child=name.rsplit('.',1);setattr(module(parent),child,value)
            return value
        def leaf(*args,**kwargs):records.append((args,kwargs));return kwargs
        mj=module('mujoco');mj.mj_name2id=leaf;mj.MjData=leaf
        for owner in ('MjSpec','MjsBody'):setattr(mj,owner,type(owner,(),{}))
        for full_name in b.SPEC_PER_BUILD:
            owner,attribute=full_name.split('.');setattr(getattr(mj,owner),attribute,leaf)
        classes=[('flygym.compose.base','BaseCompositionElement',('compile',)),
                 ('flygym.compose.fly.base_fly','BaseFly',('__init__','compile')),
                 ('flygym.compose.world.base_world','BaseWorld',('__init__',)),
                 ('flygym_demo.complex_terrain.cpg_controller','CPGNetwork',('__init__','reset','step')),
                 ('flygym_demo.complex_terrain.preprogrammed','PreprogrammedSteps',('__init__','get_joint_angles')),
                 ('flygym_demo.complex_terrain.hybrid_controller','HybridControllerObservation',())]
        owners=[mj.MjSpec,mj.MjsBody]
        for name,klass,attributes in classes:
            owner=type(klass,(),{a:leaf for a in attributes});setattr(module(name),klass,owner);owners.append(owner)
        obs=modules[classes[-1][0]].HybridControllerObservation;obs.from_sim=classmethod(leaf)
        fake_native=module('flyarena.experiments.contact_v1.native');fake_native.native_cache_manifest=leaf
        fake_law=module('flyarena.experiments.contact_v1.law');fake_law.regularized_velocity=leaf;fake_law.shared_twist=leaf
        # Keep the actual parent package; patch only its two import targets.
        modules={k:v for k,v in modules.items() if k.split('.')[0]!='flyarena' or k.endswith(('.native','.law'))}
        owners.extend([mj,fake_native,fake_law]);snapshots=[(owner,dict(vars(owner))) for owner in owners]
        self.budget.caps=dict(b.LEAF_CAPS);previous=object();marker=RuntimeError('authored guard exit')
        with patch.dict(sys.modules,modules),patch.object(contact_package,'native',fake_native,create=True),patch.object(contact_package,'law',fake_law,create=True),patch.object(io,'_ACTIVE_BUDGET',previous):
            def run():
                with self.budget.native_guard():
                    self.assertIs(io._ACTIVE_BUDGET,self.budget)
                    spec=mj.MjSpec();token=object()
                    got=spec.add_key(name='neutral',time=0,fn=token,self=token)
                    self.assertEqual(got,{'name':'neutral','time':0,'fn':token,'self':token})
                    mj.mj_name2id(token,name='thorax',fn=token,self=token)
                    self.assertEqual(self.budget.attempted,{'MjSpec.add_key':1,'mj_name2id':1})
                    self.assertEqual(self.budget.completed,self.budget.attempted)
                    if fail:raise marker
            if fail:
                with self.assertRaises(RuntimeError) as caught:run()
                self.assertIs(caught.exception,marker)
            else:run()
            self.assertIs(io._ACTIVE_BUDGET,previous)
            for owner,snapshot in snapshots:
                self.assertEqual(set(vars(owner)),set(snapshot))
                for name,value in snapshot.items():self.assertIs(vars(owner)[name],value,(owner,name))
        self.assertEqual(len(records),2)
        self.assertEqual(set(self.budget.timings),{'MjSpec.add_key','mj_name2id'})
        self.assertTrue(all(r['calls']==1 and r['seconds']>=0 for r in self.budget.timings.values()))

    def test_native_guard_forwards_collision_keywords_and_restores_on_success(self):self.exercise_native_guard(False)
    def test_native_guard_forwards_collision_keywords_and_restores_on_exception(self):self.exercise_native_guard(True)
