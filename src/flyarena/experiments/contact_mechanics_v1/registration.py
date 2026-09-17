"""Pre-native source closure and exclusive experiment identity."""
import ast,importlib.metadata,importlib.util,json,os,pathlib,shutil,sys,time
from .io import sha,write,read,digest
from .schema import *
from .budget import LEAF_CAPS
SOURCE=pathlib.Path(__file__).resolve().parents[4]
DOC=SOURCE/'docs/contact-mechanics-v1'
def source_check():
    original=read(DOC/'accepted-source-manifest.json')
    for name,rec in original.items():
        if sha(SOURCE/name)!=rec['sha256']:raise ValueError('accepted source changed: '+name)
    for p in (SOURCE/'src/flyarena/experiments/contact_mechanics_v1').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
    return {'preserved':len(original),'ready':False}
def inventory():
    paths=[SOURCE/name for name in read(DOC/'accepted-source-manifest.json')]
    for folder in ('src','docs','tests','scripts'):
        paths.extend(p for p in (SOURCE/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc',))
    paths.extend(SOURCE/name for name in ('pyproject.toml','uv.lock') if (SOURCE/name).exists())
    return {str(p.relative_to(SOURCE)):sha(p) for p in sorted(set(paths))}
def native_closure():
    # Metadata lookup does not import scientific packages or read model payloads.
    records={}
    for name in ('numpy','scipy','mujoco','flygym','flygym-demo'):
        try:dist=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            if name!='flygym-demo':raise
            continue
        files={}
        for entry in dist.files or ():
            p=pathlib.Path(dist.locate_file(entry))
            if p.is_file() and p.suffix not in ('.pyc',) and '__pycache__' not in p.parts:
                files[str(p)]=sha(p)
        for module in ({'flygym':('flygym','flygym_demo')}.get(name,(name.replace('-','_'),))):
            spec=importlib.util.find_spec(module)
            if spec and spec.submodule_search_locations:
                for directory in spec.submodule_search_locations:
                    for p in pathlib.Path(directory).rglob('*'):
                        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':files[str(p.resolve())]=sha(p)
        records[name]={'version':dist.version,'files':files}
    return records

def protocol():
    """Exact fixed prospective contract shared by producer and saved verifier."""
    return {'profiles':[CONTROL,PROFILE],'cases':[list(x) for x in CASES],
      'trials':[t.record() for stage in ('development','heldout','repeat') for t in panel(stage)],
      'schemas':{name:[list(x) for x in schema] for name,schema in (('core',CORE),('contacts',CONTACT),('candidate',CANDIDATE),('control',LEGACY))},
      'dt':DT,'leaf_caps':LEAF_CAPS,'active_ticks':[3000,25000],'analysis_inclusive':[6000,25000],'stop_ticks':[30000,40000],
      'limits':{'wall_seconds':14400,'preflight_seconds':600,'rss':2*1024**3,'bytes':8*1024**3,'free_floor':20*1024**3,'reserve_bytes':128*1024**2,'reserve_seconds':60,'physics_steps':1960100,'hard_physics_steps':2600000,'neural_seconds':0}}

def preregister(root):
    started=time.time();root=pathlib.Path(root);source_check();root.mkdir(parents=True,exist_ok=False)
    locator=read(DOC/'model-locator.json')
    if locator['registered_model_mjb_sha256']!=MODEL_SHA:raise ValueError('model locator identity')
    closure=inventory();native=native_closure()
    value={'schema':'contact-mechanics-preregistration/v1','source_root':str(SOURCE),'source':closure,'dependencies':native,'interpreter':sys.executable,'interpreter_sha256':sha(sys.executable),'python_version':sys.version,'plan_sha256':sha(DOC/'approved-plan.md'),'model_locator':locator,'leaf_caps':LEAF_CAPS,
      'profiles':[CONTROL,PROFILE],'cases':[list(x) for x in CASES],'trials':[t.record() for stage in ('development','heldout','repeat') for t in panel(stage)],'schemas':{'core':CORE,'contacts':CONTACT,'candidate':CANDIDATE,'control':LEGACY},'dt':DT,'created_unix':started,'source_bytes':sum((SOURCE/p).stat().st_size for p in closure),
      'active_ticks':[3000,25000],'analysis_inclusive':[6000,25000],'stop_ticks':[30000,40000],
      'limits':{'wall_seconds':14400,'preflight_seconds':600,'rss':2*1024**3,'bytes':8*1024**3,'free_floor':20*1024**3,'reserve_bytes':128*1024**2,'reserve_seconds':60,'physics_steps':1960100,'hard_physics_steps':2600000,'neural_seconds':0},'ready':False,'science_started':False}
    value.update(protocol())
    write(root/'preregistration.json',value);write(root/'source-closure.json',closure)
    shutil.copyfile(DOC/'approved-plan.md',root/'approved-plan.md');shutil.copyfile(DOC/'leaf-call-table.json',root/'leaf-call-table.json')
    return {'preregistration_sha256':sha(root/'preregistration.json'),'native_calls':0,'root':str(root)}
def validate(root,*,final=False):
    root=pathlib.Path(root);pre=read(root/'preregistration.json')
    if pre['interpreter']!=sys.executable or pre['interpreter_sha256']!=sha(sys.executable) or pre['python_version']!=sys.version or pre['plan_sha256']!=sha(DOC/'approved-plan.md'):raise ValueError('runtime/plan identity')
    for path,h in pre['source'].items():
        if sha(SOURCE/path)!=h:raise ValueError('source closure changed: '+path)
    for package,rec in pre['dependencies'].items():
        if importlib.metadata.version(package)!=rec['version']:raise ValueError('native dependency version')
        for path,h in rec['files'].items():
            if sha(path)!=h:raise ValueError('native asset/library closure changed: '+path)
    if final:
        reg=read(root/'registration.json')
        if reg['preregistration_sha256']!=sha(root/'preregistration.json') or sha(root/'model.mjb')!=MODEL_SHA:raise ValueError('final identity')
        return reg
    return pre
