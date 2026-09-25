"""Run budgeted circuit mutations under matched sensory input; no embodied fitness claim.

Example: arena's Python scripts/run_neural_sweep.py --data data --output var/sweep-01
On a shared node, run under: flock "${ARENA_VAR:?Set ARENA_VAR}/gpu.lock" <command>
"""
from __future__ import annotations
import argparse
import gc
import json
import signal
from pathlib import Path
import time
import numpy as np
from flyarena.compiler import Compiler
from flyarena.connectome import CIRCUITS, Connectome
from flyarena.contracts import FlySpec
from flyarena.neural import Brain, PROFILE
from flyarena.common import write_json


def run(data: Path, output: Path, circuit: str, scales: list[float], duration: int):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose a new output directory')
    output.mkdir(parents=True, exist_ok=True)
    status = {'state': 'running', 'started': time.time(), 'completed_subjects': 0,
              'scope': 'Matched neural input experiment; no body, food score, winner or evolution selection',
              'circuit': circuit, 'scales': scales, 'duration_seconds': duration,
              'sample_interval_seconds': .01, 'sensor': 'legacy bilateral odor current: 8 + 40 * concentration',
              'schedule': [[0.,0.],[1.,0.],[0.,1.],[1.,1.]], 'model': PROFILE, 'subjects': []}
    write_json(output/'status.json', status)
    try:
        graph = Connectome(data)
        compiler = Compiler(graph)
        status.update(connectome=graph.manifest['id'], connectome_sha256=graph.manifest['sha256'],
                      neurons=graph.n, edges=graph.e)
        # Compile every requested design before spending time on simulation.
        specs = [FlySpec(name=f'{circuit} x{scale:g}',connectome_sha256=graph.manifest['sha256'],
                         weight_mutations=[] if scale == 1 else [{'selector':circuit,'scale':scale}]) for scale in scales]
        reports = [compiler.compile(spec,publish=True,root=output) for spec in specs]
        for index,(spec,report) in enumerate(zip(specs,reports)):
            folder=output/f'subject-{index:02d}';folder.mkdir()
            write_json(folder/'design.json', {'spec':spec.model_dump(),'report':report})
            weights,_=compiler.load_weights(report['artifact_id'],output)
            brain=Brain(graph,weights)
            brain.advance(1);brain.reset() # Warm Numba compilation outside timed simulation.
            spike_counts=np.zeros(graph.n,dtype=np.int64)
            samples=[];started=time.perf_counter()
            for sample in range(duration*100):
                stimulus=status['schedule'][sample*4//(duration*100)]
                brain.stimulate(*stimulus)
                counts=brain.advance(100)
                spike_counts+=counts
                samples.append({'time_seconds':brain.tick*.0001,'input_left':stimulus[0],
                                'input_right':stimulus[1],'spikes_in_interval':int(counts.sum()),
                                'circuit_hz':brain.trace()})
            elapsed=time.perf_counter()-started
            write_json(folder/'traces.json', samples)
            np.savez_compressed(folder/'neuron-spikes.npz',neuron_ids=graph.ids,counts=spike_counts)
            np.savez_compressed(folder/'final-state.npz',**brain.checkpoint())
            status['subjects'].append({'name':spec.name,'scale':scales[index], 'artifact_id':report['artifact_id'],
                                      'budget_used':report['budget_used'],'total_spikes':brain.total_spikes,
                                      'wall_seconds':elapsed,'samples':len(samples),'directory':folder.name})
            status['completed_subjects']+=1
            write_json(output/'status.json',status)
            del brain,weights,spike_counts;gc.collect()
        status['state']='complete'
    except BaseException as exc:
        status.update(state='failed',error=str(exc))
        raise
    finally:
        status['finished']=time.time()
        write_json(output/'status.json',status)
    return status


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--circuit',choices=[c[0] for c in CIRCUITS],default='olfactory')
    parser.add_argument('--scales',type=float,nargs='+',default=[1.,.9,1.1])
    parser.add_argument('--duration',type=int,choices=range(1,31),default=1,metavar='1..30')
    args=parser.parse_args()
    def interrupted(signum, frame):
        raise RuntimeError('Experiment interrupted or timed out')
    signal.signal(signal.SIGTERM, interrupted)
    if len(args.scales)>8:parser.error('At most 8 subjects per serial job')
    print(json.dumps(run(args.data,args.output,args.circuit,args.scales,args.duration)))
