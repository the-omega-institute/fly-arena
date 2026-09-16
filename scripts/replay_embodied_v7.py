"""One fixed coordinate panel and sixteen actual-body archived-neural replays."""
from pathlib import Path
import json, time, importlib.metadata, inspect
import numpy as np
import mujoco as mj
from flyarena.common import file_sha, write_json
from flyarena.experiments.fixture_v7 import Fixture
from flyarena.experiments.embodied_v7 import RMAX
from flyarena.experiments.contact_v6 import LEGS
ROOT=Path(__file__).resolve().parents[1]
OLD=Path('/tmp/fly-arena-contact-v6/var/contact-v6/assay-001')
OUT=ROOT/'var/embodied-v7/replay'

def run(f, folder, commands):
    folder.mkdir(); f.restore(f.initial)
    np.savez_compressed(folder/'checkpoint-0000.npz',**f.checkpoint())
    q=[f.data.qpos.copy()]; velocity=[f.data.qvel[f.vadr].copy()]; force=[f.data.actuator_force[f.aids].copy()]
    requested=[np.zeros(6)]; work=[np.zeros(6)]; cumulative=np.zeros(6)
    for tick in range(6000):
        if tick%100==0: f.command_knees(commands[tick//100])
        f.step(); cumulative += f.data.actuator_force[f.aids]*f.data.qvel[f.vadr]*.0001
        q.append(f.data.qpos.copy()); velocity.append(f.data.qvel[f.vadr].copy()); force.append(f.data.actuator_force[f.aids].copy())
        requested.append(f.command.copy()); work.append(cumulative.copy())
        if f.tick in (2000,4000,6000): np.savez_compressed(folder/f'checkpoint-{f.tick:04}.npz',**f.checkpoint())
    np.savez_compressed(folder/'body.npz',ticks=np.arange(6001),qpos=q,knees=np.array(q)[:,f.qadr],velocity=velocity,force=force,requested=requested,work_native=work)

def longest(mask):
    return max((len(a) for a in ''.join('1' if x else '0' for x in mask).split('0')),default=0)

def main():
    OUT.mkdir(exist_ok=False)
    f=Fixture(); geometry=f.geometry(); write_json(OUT/'geometry.json',geometry)
    (OUT/'compiled.xml').write_text(f.sim.world.mjcf_root.to_xml()); mj.mj_saveModel(f.model,str(OUT/'compiled.mjb'),None)
    sources=[ROOT/'src/flyarena/experiments'/n for n in ('fixture_v7.py','embodied_v7.py','contact_v6.py','sensor.py')]+[Path(__file__),ROOT/'scripts/env-v7.sh']
    import flygym.simulation, flygym.compose.world.tethered_world, flygym.compose.fly.base_fly, flygym_demo.complex_terrain.common
    sources += [Path(inspect.getfile(x)) for x in (flygym.simulation,flygym.compose.world.tethered_world,flygym.compose.fly.base_fly,flygym_demo.complex_terrain.common)]
    source_hashes={str(p):file_sha(p) for p in sources}
    archive_hashes={str(p):file_sha(p) for p in OLD.rglob('*.npz')}
    for p,digest in json.loads((OLD/'inventory.json').read_text()).items():
        if p.endswith('.npz'): assert file_sha(OLD/p)==digest
    protocol={'profile':'contact-embodiment-v7','claim':'recorded neural replay into tethered actual physics; NOT closed loop or walking',
              'body_dt':.0001,'command_hold_ticks':100,'rmax_hz':RMAX,'readout':'.1*(mean flexor-mean extensor)/Rmax',
              'replay_time':'rates at neural tick t held for physical [t,t+100); rates from endpoint tick 6000 not applied',
              'coordinate_pulses':'each leg independently -0.05,+0.05 radians; hold [.2,.4); end .6; identical neutral initial state',
              'gate':{'own_difference_rad_exclusive':.01,'duration_seconds':.05,'required':['LF','RM or RH'],'repeat_max_rad':1e-9,'zero_settled_rms_rad':.001,'settled_window':[.2,.6]},
              'versions':{k:importlib.metadata.version(k) for k in ('flygym','mujoco','numpy')},'source_hashes':source_hashes,
              'archive_hashes':archive_hashes,'approved_plan_sha256':file_sha(ROOT/'var/embodied-v7/approved-plan.json'),
              'compiled_hashes':{n:file_sha(OUT/n) for n in ('compiled.xml','compiled.mjb')},'geometry_sha256':file_sha(OUT/'geometry.json')}
    assert protocol['versions']['flygym']=='2.1.0' and protocol['versions']['mujoco']=='3.9.0'
    write_json(OUT/'registration.json',protocol)
    coordinate=[]
    for i,l in enumerate(LEGS):
        for value in (-.05,.05):
            command=np.zeros((60,6)); command[20:40,i]=value
            folder=OUT/f'coordinate-{l}-{value:+.2f}'; run(f,folder,command)
            b=np.load(folder/'body.npz'); response=(b['knees'][3500:4001,i].mean()-f.neutral[i])*f.signs[i]
            coordinate.append({'leg':l,'requested_rad':value,'actual_signed_rad':float(response),'pass':bool(response*value>0)})
    write_json(OUT/'coordinate.json',coordinate)
    if not all(x['pass'] for x in coordinate):
        write_json(OUT/'gate.json',{'coordinate_pass':False,'transduction_pass':False,'stop':'coordinate mapping'}); return
    for name in ('blank',*LEGS,'LF-repeat'):
        old=np.load(OLD/name/'samples.npz'); rates=old['rates_hz']; pools=old['motor_pools_hz']
        assert np.isfinite(rates).all() and rates.min()>=0 and rates.max()<=RMAX+1e-9
        cmd=.1*(pools[:, :,0]-pools[:, :,1])/RMAX
        for clamp in (False,True):
            run(f,OUT/(f'{name}-'+('zero' if clamp else 'intact')),np.zeros((60,6)) if clamp else cmd[:-1])
        print(json.dumps({'replayed':name}),flush=True)
    metrics={}
    for i,l in enumerate(LEGS):
        a=np.load(OUT/f'{l}-intact/body.npz'); p=np.load(OUT/f'{l}-zero/body.npz')
        diff=a['knees'][:,i]-p['knees'][:,i]; length=longest(np.abs(diff)>.01)
        metrics[l]={'peak_own_difference_rad':float(np.max(np.abs(diff))),'duration_above_001_s':length*.0001,'pass':length>=500,
                    'max_actuator_force_native':float(np.max(np.abs(a['force']))),'final_work_native':a['work_native'][-1].tolist()}
    a=np.load(OUT/'LF-intact/body.npz'); b=np.load(OUT/'LF-repeat-intact/body.npz')
    repeat=float(np.max(np.abs(a['knees']-b['knees'])))
    zero=np.load(OUT/'blank-zero/body.npz'); rms=float(np.sqrt(np.mean((zero['knees'][2000:]-f.neutral)**2)))
    passed=metrics['LF']['pass'] and (metrics['RM']['pass'] or metrics['RH']['pass']) and repeat<=1e-9 and rms<=.001
    assert all(file_sha(Path(p))==h for p,h in source_hashes.items())
    write_json(OUT/'gate.json',{'coordinate_pass':True,'transduction_pass':passed,'legs':metrics,'repeat_max_rad':repeat,'zero_settled_rms_rad':rms,
                             'completed_coordinate_trials':12,'completed_replay_trials':16,'next_stage':'physical-contact' if passed else 'STOP'})
    print((OUT/'gate.json').read_text(),flush=True)

if __name__=='__main__': main()
