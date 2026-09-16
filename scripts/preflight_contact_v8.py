"""Input integrity, exact existing-interval adapter check and scalar contracts.
No new full neural/body condition is executed here.
"""
from pathlib import Path
import sys,json,hashlib,shutil,importlib.metadata as metadata
import numpy as np
import mujoco as mj
from flyarena.common import file_sha
from flyarena.connectome import Connectome
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec
from flyarena.neural import Brain
from flyarena.backend import CPUBrainBackend
from flyarena.experiments.contact_v6 import LEGS,bind_annotations
from flyarena.experiments.contact_presence_v8 import ContactPresenceBridge,RMAX
from flyarena.experiments.binary_fixture_v8 import BinaryFixture,penetration
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'var/contact-v8'; INPUTS=OUT/'inputs'
ORIGINAL=Path('/Users/lexa/Desktop/lexa/omega/fly-arena'); OLD=Path('/tmp/fly-arena-embodied-v7/var/embodied-v7')

def write_new(path,value):
    with path.open('x') as f: json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

def main():
    oldreg=json.loads((INPUTS/'v7-contact-registration.json').read_text())
    replayreg=json.loads((INPUTS/'v7-replay-registration.json').read_text())
    source_bindings=[]
    for p,h in oldreg['source_hashes'].items():
        rel=Path(p).relative_to('/private/tmp/fly-arena-embodied-v7')
        source=OLD/'source'/rel if (OLD/'source'/rel).exists() else ROOT/rel
        assert file_sha(source)==h,('fixed v7 source',source)
        dest=INPUTS/'old-source'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        if rel.parts[0]=='src': assert file_sha(ROOT/rel)==h if (ROOT/rel).exists() else True
        source_bindings.append({'source':str(source),'copy':str(dest),'sha256':h})
    assert file_sha(INPUTS/'geometry.json')==replayreg['geometry_sha256']==oldreg['body_geometry_sha256']
    for p,h in replayreg['source_hashes'].items():
        if '/site-packages/' in p: assert file_sha(Path(p))==h
    f=BinaryFixture(INPUTS)
    oldfolder=OLD/'contact/WT-LF-42-neutral-intact'
    existing=INPUTS/'adapter-reference';existing.mkdir(exist_ok=True)
    for name in ['samples.npz','body-2000.npz']:
        shutil.copyfile(oldfolder/name,existing/name)
    a=np.load(existing/'samples.npz');f.restore(dict(np.load(existing/'body-2000.npz')))
    f.command_knees(a['command_rad'][20]);geo=oldreg['probe_geometry']['LF']
    for tick in range(2000,2100):
        f.data.mocap_pos[f.probe_id]=np.array(geo['center_mm'])-penetration(tick)*np.array(geo['normal']);f.step()
    error=float(np.max(np.abs(f.data.qpos-a['qpos'][21])))
    ratios,forces,loaded,raw=f.observe()
    sensor_error=float(np.max(np.abs(ratios-a['contact_ratios'][22])))
    assert error<1e-12 and sensor_error<1e-12,(error,sensor_error)
    graph=Connectome(ORIGINAL/'data',verify=True)
    assert file_sha(graph.path/'manifest.json')==oldreg['graph_manifest_sha256']
    assert file_sha(ORIGINAL/'data/raw/body-annotations.feather')==oldreg['raw_annotations_sha256']
    groups,annotations=bind_annotations(graph,ORIGINAL/'data/raw/body-annotations.feather')
    original_groups=np.load(OLD/'contact/groups.npz')
    for key,value in groups.items():assert np.array_equal(value,original_groups[key]),key
    selected=np.unique(np.concatenate(list(groups.values())))
    np.savez_compressed(INPUTS/'groups.npz',**groups,selected=selected)
    write_new(INPUTS/'annotations.json',annotations)
    compiler=Compiler(graph);subjects=json.loads((INPUTS/'subjects.json').read_text());bindings=[]
    for subject,oldsubject in zip(subjects,oldreg['bindings']):
        assert all(subject[k]==oldsubject[k] for k in subject)
        artifact=ORIGINAL/'var/artifacts'/subject['artifact_id']
        weights,manifest=compiler.load_weights(subject['artifact_id'],ORIGINAL/'var')
        assert file_sha(artifact/'manifest.json')==oldsubject['manifest_sha256']
        assert manifest['phenotype']['weights_sha256']==oldsubject['weights_sha256']
        report=compiler.compile(FlySpec.model_validate(subject['spec']),publish=False)
        assert report['artifact_id']==subject['artifact_id'] and report['weights_sha256']==oldsubject['weights_sha256']
        b=ContactPresenceBridge(CPUBrainBackend(Brain(graph,weights)),groups)
        rest=b.checkpoint();oldrest=np.load(OLD/'contact/neural-rest.npz')
        assert all(np.array_equal(rest[k],oldrest[k]) for k in rest)
        np.savez_compressed(INPUTS/('rest-'+subject['role']+'.npz'),**rest)
        # Input-contract only: no advance on full graph, no outcome fitting.
        b.backend.brain.external.fill(7)
        b.stimulate([0,1e-300,.2,1,2,0],(.55,.55))
        for l,v in zip(LEGS,[0,48,48,48,48,0]):assert np.all(b.backend.brain.external[groups['afferent_'+l]]==v)
        b.stimulate(np.ones(6),(.55,.55),True)
        for l in LEGS:assert np.all(b.backend.brain.external[groups['afferent_'+l]]==0)
        for side in ['left','right']:assert np.all(b.backend.brain.external[graph.groups['olfactory_'+side]]==48*(.55/.85))
        b.restore(rest)
        binding=subject|{'manifest_sha256':file_sha(artifact/'manifest.json'),'mutation_sha256':file_sha(artifact/'mutations.npz'),'weights_sha256':manifest['phenotype']['weights_sha256'],'reconstructed_spec_matches':True}
        bindings.append(binding)
    # Independent isolated scalar exponential-Euler recurrence: 48 is preselected.
    voltage=-52.;refractory=0;spikes=[]
    for tick in range(10000):
        if refractory: refractory-=1;continue
        voltage=-52+(voltage+52)*np.exp(-.1/20)+48*(1-np.exp(-.1/20))
        if voltage>=-45:spikes.append(tick+1);voltage=-52.;refractory=22
    assert spikes[0]==32 and set(np.diff(spikes))=={54}
    contracts={'first_scalar_crossing_ms':spikes[0]*.1,'scalar_sustained_hz':10000/54,'scalar_only_not_network_validation':True,
        'adapter_existing_interval_qpos_error':error,'adapter_existing_interval_sensor_error':sensor_error,
        'graph_neurons':graph.n,'graph_edges':graph.e,'selected_neurons':len(selected),'raw_graph_ids_exact':True,
        'old_source_bindings':source_bindings,'subjects':bindings,'rmax_hz':RMAX,
        'versions':{n:metadata.version(n) for n in ['numpy','numba','llvmlite','mujoco','flygym','pyarrow','pydantic','scipy','matplotlib']},
        'python':sys.version,'clock_assumption':'initial forward forces at tick0; after step at read tick t force/contact evaluation tick t-1, no additional forward at input boundary; external applies [t,t+100), body uses prior held motor, next command eligible t+100',
        'precision_note':'Approved literal denominator 444.41470981063657 used; v7 computed float 444.41470981063986 differs by 3.3e-12 Hz; no gain selection.'}
    write_new(OUT/'preflight.json',contracts)
    print(json.dumps({k:v for k,v in contracts.items() if k not in ['subjects','old_source_bindings']}),flush=True)

if __name__=='__main__':main()
