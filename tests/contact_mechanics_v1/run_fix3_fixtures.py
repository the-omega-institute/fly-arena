"""Targeted FIX3 guarded fixtures; no native execution or broad suite rerun."""
import ast,importlib.util,io,json,pathlib,resource,sys,time,unittest
sys.dont_write_bytecode=True
root=pathlib.Path(__file__).resolve().parents[2];scratch=pathlib.Path('/tmp/fly-contact-mechanics-fix3');scratch.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'src'))
for p in (root/'src/flyarena/experiments/contact_mechanics_v1').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
counts={'native':0,'production_intent':0,'forbidden_reads':0}
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        s=str(args[0])
        if any(x in s for x in ('/var/delivery/','model.mjb','single_steps_','/canonical','/opaque','/transcript')):
            counts['forbidden_reads']+=1;raise RuntimeError('forbidden fixture input')
sys.addaudithook(audit)
def profile(frame,event,arg):
    if event!='call':return
    p=frame.f_code.co_filename;n=frame.f_code.co_name
    if p.endswith('/contact_v1/law.py') and n=='advance_intent':counts['production_intent']+=1;raise RuntimeError('production intent forbidden')
    if (p.endswith('/contact_mechanics_v1/geometry.py') or p.endswith('/contact_mechanics_v1/runtime.py')) and n not in ('<module>','Geometry'):
        counts['native']+=1;raise RuntimeError('native runtime forbidden')
    if p.endswith('/contact_v1/native.py') and n in ('_mj','bind_native','model_digest','capture_completed','_geometry','_jac','observe','excursion','checkpoint','restore','native_cache_manifest'):
        counts['native']+=1;raise RuntimeError('native path forbidden')
sys.setprofile(profile);start=time.time()
spec=importlib.util.spec_from_file_location('mechanics_source_tests',root/'tests/contact_mechanics_v1/test_source.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
spec2=importlib.util.spec_from_file_location('mechanics_fix1_tests',root/'tests/contact_mechanics_v1/test_fix1.py');module2=importlib.util.module_from_spec(spec2);sys.modules[spec2.name]=module2;spec2.loader.exec_module(module2)
module2.ROOT=scratch
spec3=importlib.util.spec_from_file_location('mechanics_fix3_tests',root/'tests/contact_mechanics_v1/test_fix3.py');module3=importlib.util.module_from_spec(spec3);sys.modules[spec3.name]=module3;spec3.loader.exec_module(module3)
targeted=unittest.defaultTestLoader.loadTestsFromModule(module3)
preserved_names=[
 'mechanics_source_tests.AdditionalContracts.test_attempt_completion_ledger_keeps_failed_calls',
 'mechanics_fix1_tests.ClosureAndSetupContracts.test_native_data_pending_allocation_stops_before_authored_constructor',
 'mechanics_fix1_tests.ClosureAndSetupContracts.test_control_observation_accounting_uses_all_three_families',
 'mechanics_fix1_tests.ClosureAndSetupContracts.test_ledger_caps_hashes_and_data_array_coefficients',
]
preserved=unittest.defaultTestLoader.loadTestsFromNames(preserved_names)
targeted_count=targeted.countTestCases();preserved_count=preserved.countTestCases()
suite=unittest.TestSuite([targeted,preserved])
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite);sys.setprofile(None)
rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
report={'scope':'FIX3 targeted and selected guarded regression fixtures','targeted_tests':targeted_count,'preserved_regression_tests':preserved_count,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'elapsed_s':time.time()-start,'rss_bytes':rss if sys.platform=='darwin' else rss*1024,'interpreter':sys.executable,'bytecode_disabled':sys.dont_write_bytecode,**counts,'native_modules':[x for x in ('mujoco','flygym','flygym_demo') if x in sys.modules],'numeric_threads':{k:__import__('os').environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')}}
(scratch/'fix3-fixtures.txt').write_text(stream.getvalue());(scratch/'fix3-fixture-report.json').write_text(json.dumps(report,indent=2)+'\n');print(stream.getvalue());print(json.dumps(report))
raise SystemExit(0 if result.wasSuccessful() and not any(counts.values()) and not report['native_modules'] and report['rss_bytes']<1024**3 else 1)
