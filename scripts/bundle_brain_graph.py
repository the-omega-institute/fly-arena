"""Attach bounded, connected neuron neighborhoods to a published replay design.

Edges and model weights come from the actual compiled contestant. These are
structural display samples, not additional recorded neural activity. No private
account fields, simulation state or whole-brain tensors are published.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
from flyarena.connectome import Connectome,CIRCUITS
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec
from flyarena.common import DATA,VAR


from flyarena.brain_graph import build


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--match-id',required=True);p.add_argument('--data',type=Path,default=DATA);p.add_argument('--var',type=Path,default=VAR);args=p.parse_args()
    if len(args.match_id)!=32 or any(c not in '0123456789abcdef' for c in args.match_id):p.error('Invalid match id')
    folder=args.var/'research/replay-gallery-v1';path=folder/(args.match_id+'-match.json');match=json.loads(path.read_text());frames=json.loads((folder/(args.match_id+'-frames.json')).read_text())
    if match['status']!='verified':raise ValueError('Only verified public replays')
    graph=Connectome(args.data);compiler=Compiler(graph)
    stats=[]
    for slot,participant in enumerate(match['participants']):
        ids=sorted({str(n['id']) for frame in frames for n in (frame.get('brain',[{}]*len(match['participants']))[slot].get('sampled_nodes') or [])})
        if not ids:continue
        if len(ids)>512:raise ValueError('Expected a bounded fixed replay sample')
        participant['brain_graph']=build(graph,compiler,participant,ids,args.var)
        stats.append({'fly':participant['id'],'sampled_neurons':len(ids),'circuits':{k:{'neurons':len(v['neurons']),'edges':len(v['edges'])} for k,v in participant['brain_graph']['circuits'].items()}})
    path.write_text(json.dumps(match,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'match_id':match['id'],'bytes':path.stat().st_size,'participants':stats}),flush=True)

if __name__=='__main__':main()
