"""Matched full-connectome WT input pulses; open-loop neural controls, not behavior claims."""
import argparse,json,time
from pathlib import Path
import numpy as np
from flyarena.connectome import Connectome
from flyarena.neural import Brain
from flyarena.backend import CPUBrainBackend
from flyarena.experiments.embodied_sensor import EmbodiedSensor
from flyarena.observation import display_indices,population_summary
from flyarena.common import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data'));p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    graph=Connectome(a.data);brain=Brain(graph);backend=CPUBrainBackend(brain);sensor=EmbodiedSensor(graph,'engineered-kernel-contact-v1')
    indices=display_indices(graph,[]);results=[]
    conditions=[('blank',{}),('odor-left',{'odor_left':.5}),('taste',{'taste':1.}),('touch-left',{'touch_left':1.}),('visual-left',{'visual_left':1.})]
    for name,inputs in conditions:
        brain.reset();samples=[];started=time.time()
        for block in range(200):
            t=block*.01; pulse=.5<=t<1.5
            kwargs=dict(odor_left=0.,odor_right=0.);kwargs.update(inputs if pulse else {})
            sensor.apply(brain,backend=backend,**kwargs);brain.advance(100)
            samples.append({'time':round((block+1)*.01,2),'input_on':pulse,'population':population_summary(brain.rates),'circuits':brain.trace(),'sampled_nodes':[{'id':str(int(graph.ids[i])),'activity':float(brain.rates[i])} for i in indices]})
        results.append({'id':name,'inputs':inputs,'elapsed_seconds':time.time()-started,'samples':samples})
        write_json(a.output/'status.json',{'completed':[r['id'] for r in results],'total':len(conditions)});print(name,round(time.time()-started,2),flush=True)
    write_json(a.output/'controls.json',{'schema':'wt-stimulus-controls/v1','connectome_sha256':graph.manifest['sha256'],'neuron_count':graph.n,'recorded_count':len(indices),'model':'malecns-lif-cpu-v1','sensory_profile':sensor.profile['id'],'stimulus_seconds':[.5,1.5],'duration_seconds':2,'scope':'Independent reset WT brains with identical weights; open-loop engineered input pulses, no body or fitness.','conditions':results})

    summary=json.loads((a.output/'controls.json').read_text())
    for condition in summary['conditions']:
        for sample in condition['samples']:sample.pop('sampled_nodes')
    write_json(a.output/'summary.json',summary)

if __name__=='__main__':main()
