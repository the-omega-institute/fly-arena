"""A recorded engineering ablation, never a ranking match."""
import json
from pathlib import Path
import numpy as np
from flyarena.connectome import Connectome
from flyarena.compiler import Compiler
from flyarena.neural import Brain
from flyarena.store import Store
from flyarena.runner import simulate
from flyarena.contracts import MatchRequest
from flyarena.common import write_json

s=Store();flies=s.flies();base=next(f for f in flies if f['name']=='Wild Type / 原型');mutant=next(f for f in flies if f['name']=='Nectar / 花蜜')
g=Connectome();c=Compiler(g);states=[]
for f in [base,base,mutant]:
 w,_=c.load_weights(f['artifact_id']);b=Brain(g,w);b.stimulate(.7,.2);b.advance(3000)
 states.append(b.checkpoint())
assert all(np.array_equal(states[0][k],states[1][k]) for k in states[0])
changed=int(np.count_nonzero(states[0]['rates']!=states[2]['rates']))
assert changed>0
request=MatchRequest(fly_ids=[base['id']],mode='forage',map_id='orchard',seed=42,duration_seconds=2)
folder=Path('var/probes/output-ablation');simulate(request,[base],folder,silence_output=True)
frames=json.loads((folder/'frames.json').read_text())
assert all(np.max(np.abs(f['drives']))==0 for f in frames)
displacement=float(np.linalg.norm(np.array(frames[-1]['positions'][0][:2])-frames[0]['positions'][0][:2]))
report={'kind':'engineering-causality-probe','stimulus':[.7,.2],'neural_ticks':3000,'same_input_exact_repeat':True,'mutated_neurons_with_changed_rate':changed,'mutation':'olfactory x1.18, projection x1.1','output_ablation_displacement_mm':displacement,'output_ablation_score':json.loads((folder/'result.json').read_text())['scores'],'limitation':'Single controlled stimulus/seed; not evidence of statistical advantage or natural behavior.'}
write_json(Path('var/probes/causality.json'),report);print(report)
