"""Full-connectome rate-network BPTT + Adam, using installed Arena dependencies.

Config: {"data":"/path/to/data","output":"var/rate-training","updates":3,"steps":100}.
Needs the public prepared graph and frozen readout locally. This fits a neural
response teaching task; the Arena subsequently measures actual embodied fitness.
"""
from copy import deepcopy
from pathlib import Path
import numpy as np
from flyarena.common import digest,write_json
from flyarena.connectome import Connectome
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec
from flyarena.rate_training import fit


def propose(founder,history,generation,slot,config):
    done=[m for m in history if m['generation']<generation and m['fitness'] is not None]
    parent=max(done,key=lambda m:(m['fitness'],-m['generation'],-m['slot']))['fly'] if done else founder
    spec=deepcopy(parent['spec']);spec.update(name=f'Rate Adam G{generation+1}.{slot+1}',parent_id=parent['id'])
    if spec['model_profile']!='malecns-rate-cpu-v1':raise ValueError('Start from a continuous-rate fly')
    if generation and slot==0:return spec
    graph=Connectome(Path(config['data']),verify=True);compiler=Compiler(graph)
    output=Path(config.get('output','var/rate-training'));output.mkdir(parents=True,exist_ok=True)
    report=compiler.compile(FlySpec.model_validate(spec),publish=True,root=output)
    weights,_=compiler.load_weights(report['artifact_id'],output)
    with np.load(graph.path/'readout.npz',allow_pickle=False) as a:neurons,decoder=a['neurons'],a['weights']
    circuits=['olfactory','projection','descending']
    delta,record=fit(graph,weights,neurons,decoder,circuits,updates=int(config.get('updates',3)),steps=int(config.get('steps',100)),
                     learning_rate=float(config.get('learning_rate',.02)),tau_scale=spec['neuron_parameters']['tau_scale'],threshold_shift=spec['neuron_parameters']['threshold_shift_mv'])
    baseline=deepcopy(spec)
    # Project toward the parent until all combined-edge and mutation budgets pass.
    for factor in (1.,.5,.25,.125,0.):
        spec=deepcopy(baseline)
        spec['weight_mutations'] += [{'selector':c,'scale':float(np.exp(delta[i]*factor))} for i,c in enumerate(circuits)]
        try:compiler.compile(FlySpec.model_validate(spec));break
        except ValueError:
            if factor==0.:raise
    record.update(parent_id=parent['id'],generation=generation,slot=slot,budget_projection_factor=factor,
                  note='Loss trajectory describes pre-projection neural training; evaluate the exported proposal in the arena.')
    spec['description']=(f"Full-graph Adam response training: {record['updates']} updates, {record['rate_steps']} ms per odor. "
                         f"Teaching MSE {record['history'][0]['response_mse']:.6g} → {record['history'][-1]['response_mse']:.6g}; "
                         f"budget projection {factor:g}. This is neural response loss, not arena fitness or online learning.")
    write_json(output/(digest(record)+'.json'),record)
    return spec
