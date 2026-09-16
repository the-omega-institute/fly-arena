"""Outcome-free exclusive source and raw-input registration."""
import hashlib,json,os,time,resource,sys
from pathlib import Path
import numpy as np
import mujoco as mj
ROOT=Path('/tmp/fly-arena-behavior-v11')
RAW=Path('/tmp/fly-arena-behavior-v10/var/behavior-v10/mechanical-01')
CONTROL=Path('/Users/lexa/Desktop/lexa/omega/fly-arena/var/sshx/behavior-v11')
OUT=ROOT/'var/behavior-v11/audit-01'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def write(p,x):
 with p.open('x') as f:json.dump(x,f,sort_keys=True,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
def main():
 OUT.mkdir(exist_ok=False)
 error=None
 try:
  reg=json.loads((RAW/'registration.json').read_text());sources=json.loads((RAW/'sources.json').read_text())
  files={};inventory=[]
  def bind(p,expected=None):
   p=Path(p);h=sha(p)
   if expected and h!=expected:raise ValueError('hash mismatch: '+str(p))
   files[str(p)]={'sha256':h,'bytes':p.stat().st_size}
  for p in ['goal.json','context.json','approved-plan.json']:bind(CONTROL/p)
  for p in [ROOT/'docs/BEHAVIOR_V11_REGISTRATION.md',Path(__file__),RAW/'registration.json',RAW/'development-decision.json',RAW/'execution-terminal.json']:bind(p)
  bind(RAW/'model.mjb',reg['model_sha256']);bind(RAW/'sources.json',reg['sources_sha256']);bind(RAW/'model-names.json',reg['native_names_sha256']);bind(RAW/'subjects.json',reg['subjects_sha256'])
  for original,v in sources.items():
   bind(RAW/v['archive'],v['sha256'])
   if '/.venv/' in original:bind(original,v['sha256'])
  for p in (CONTROL/'frozen-v10-source').rglob('*'):
   if p.is_file():
    if p.name.endswith(('.log.md','.carrier.log')):raise ValueError('forbidden source')
    bind(p)
    matches=[v for k,v in sources.items() if k.endswith(str(p.relative_to(CONTROL/'frozen-v10-source'))) ]
    if matches and any(v['sha256']!=sha(p) for v in matches):raise ValueError('frozen source mismatch')
  for kind in ['artifacts','graph']:
   pairs=reg[kind].values() if kind=='artifacts' else [reg[kind]]
   for mapping in pairs:
    for p,h in mapping.items():bind(p,h)
  for name,v in reg['compiled_arrays'].items():bind(RAW/f'model-{name}.npy',v['sha256'])
  for profile in reg['profiles']:
   for seed in [42,43]:
    for case in reg['cases']:
     if not case[1]:continue
     name=f'{profile}--{seed}--{case[0]}';trial=RAW/'development'/name
     item={'id':name,'profile':profile,'seed':seed,'case':case,'raw':str(trial),'ticks':[6000,25000],'records':['actual','command','unit_r1']}
     for stream in ['core','geometry']:
      path=trial/stream;term=json.loads((path/'terminal.json').read_text());meta=json.loads((path/'start.json').read_text())
      if not term['complete'] or term['primary_failure'] or term['retention_failures']:raise ValueError('incomplete stream')
      if (meta['profile'],meta['seed'],meta['case'])!=(profile,seed,case):raise ValueError('condition mismatch')
      bind(path/'terminal.json');bind(path/'start.json')
      for n,h in term['files'].items():bind(path/n,h)
     inventory.append(item)
  m=mj.MjModel.from_binary_path(str(RAW/'model.mjb'))
  for k in reg['compiled_arrays']:
   if not np.array_equal(getattr(m,k),np.load(RAW/f'model-{k}.npy',allow_pickle=False)):raise ValueError('compiled mismatch '+k)
  native={'axes':m.jnt_axis.tolist(),'qposadr':m.jnt_qposadr.tolist(),'dofadr':m.jnt_dofadr.tolist(),'transmissions':m.actuator_trnid.tolist(),'gear':m.actuator_gear.tolist(),'gain':m.actuator_gainprm.tolist(),'bias':m.actuator_biasprm.tolist(),'material_points':[]}
  for gid in reg['measurement']['foot_geom_ids']:
   mesh=m.geom_dataid[gid];v=m.mesh_vert[m.mesh_vertadr[mesh]:m.mesh_vertadr[mesh]+m.mesh_vertnum[mesh]].astype(float)
   native['material_points'].append({'geom':int(gid),'vertices_sha256':hashlib.sha256(v.tobytes()).hexdigest(),'centroid':v.mean(axis=0).tolist(),'vertices':len(v)})
  write(OUT/'native.json',native);write(OUT/'inputs.json',files)
  write(OUT/'registration.json',{'schema':'distal-registration/v11','registered_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'specification':str(ROOT/'docs/BEHAVIOR_V11_REGISTRATION.md'),'specification_sha256':sha(ROOT/'docs/BEHAVIOR_V11_REGISTRATION.md'),'inputs_sha256':sha(OUT/'inputs.json'),'native_sha256':sha(OUT/'native.json'),'inventory':inventory,'raw':str(RAW),'budget':{'workers':1,'deadline_unix':1789577628,'rss_bytes':8*1024**3,'new_bytes':2*1024**3,'physical_seconds':0,'neural_seconds':0,'sweeps':0},'old_failure_verbatim':json.loads((CONTROL/'context.json').read_text())['implementation_conclusion']['actual_measured_outcomes']['failed'],'downstream':json.loads((CONTROL/'approved-plan.json').read_text())['downstream_goal']})
  print(json.dumps({'registered':len(inventory),'inputs':len(files),'registration_sha256':sha(OUT/'registration.json')}))
 except BaseException as exc:
  error={'type':type(exc).__name__,'message':str(exc)};raise
 finally:
  write(OUT/'registration-terminal.json',{'error':error,'complete':error is None})
if __name__=='__main__':main()
