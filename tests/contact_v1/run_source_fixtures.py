"""Source-only fixture harness, including frozen-source negative fix1 regressions."""
import argparse
import ast
import importlib.util
import io
import json
import os
import pathlib
import resource
import sys
import time
import unittest

parser=argparse.ArgumentParser()
parser.add_argument('--source-root',default='/tmp/fly-arena-contact-realization-design-v1')
parser.add_argument('--regressions-only',action='store_true')
parser.add_argument('--report-name',default='corrected')
args=parser.parse_args()
root=pathlib.Path(args.source_root); tests=pathlib.Path(__file__).parent
scratch=pathlib.Path('/tmp/fly-contact-v1-fix1'); scratch.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'src'))
source=root/'src/flyarena/experiments/contact_v1'
for path in [*source.glob('*.py'),tests/'test_contract.py',tests/'test_fix1.py']:
    ast.parse(path.read_text(),filename=str(path))
counts={'native_calls':0,'native_intent_equation_calls':0,'forbidden_data_reads':0}
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        name=str(args[0])
        if any(p in name for p in ('/var/delivery/','/var/behavior-','/single_steps_','/canonical','/opaque','/review-receipt','/quality-review-summary')):
            counts['forbidden_data_reads']+=1
            raise RuntimeError('forbidden data read in fixture run')
sys.addaudithook(audit)
def profile(frame,event,arg):
    if event=='call':
        filename=frame.f_code.co_filename; name=frame.f_code.co_name
        if filename.endswith('/contact_v1/law.py') and name=='advance_intent':
            counts['native_intent_equation_calls']+=1
            raise RuntimeError('native-equation execution forbidden in fixture run')
        if filename.endswith('/contact_v1/native.py') and name in {'_mj','bind_native','model_digest','capture_completed','_geometry','_jac','observe','excursion','checkpoint','restore','native_cache_manifest','__init__'}:
            if name=='__init__' and frame.f_locals.get('self').__class__.__name__=='NativePort': return
            counts['native_calls']+=1
            raise RuntimeError('native adapter execution forbidden in fixture run')
sys.setprofile(profile)
started=time.time()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module)
    return module
base=load('contact_v1_fixture_tests',tests/'test_contract.py')
fix=load('contact_v1_fix1_tests',tests/'test_fix1.py')
loader=unittest.defaultTestLoader
if args.regressions_only:
    suite=unittest.TestSuite(fix.Fix1Contracts(name) for name in loader.getTestCaseNames(fix.Fix1Contracts) if name.startswith('test_regression_'))
else:
    suite=unittest.TestSuite([loader.loadTestsFromModule(base),loader.loadTestsFromModule(fix)])
stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
sys.setprofile(None)
output=stream.getvalue(); (scratch/(args.report_name+'-tests.txt')).write_text(output)
rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
report={'schema':'contact-source-fixtures/fix1','source_root':str(root),'tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'success':result.wasSuccessful(),
        'failed_cases':[test.id() for test,_ in result.failures],'error_cases':[test.id() for test,_ in result.errors],
        'elapsed_s':time.time()-started,'observed_peak_rss_bytes':rss if sys.platform=='darwin' else rss*1024,
        'interpreter':sys.executable,'bytecode_disabled':sys.dont_write_bytecode,
        'numeric_threads':{k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS')},
        'scientific_imports_present':[p for p in ('mujoco','flygym','flygym_demo') if p in sys.modules],**counts,
        'limitations':'Authored state/provider/recorder payload fixtures only. No native CPG, model, geometry, physics, graph, cache manifest or physical checkpoint restore executed.'}
(scratch/(args.report_name+'-report.json')).write_text(json.dumps(report,indent=2)+'\n')
print(output,end=''); print(json.dumps(report))
raise SystemExit(0 if result.wasSuccessful() and not any(counts.values()) else 1)
