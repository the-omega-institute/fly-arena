"""Attach bounded, connected neuron neighborhoods to a published replay design.

Edges and model weights come from the actual compiled contestant. These are
structural display samples, not additional recorded neural activity. No private
account fields, simulation state or whole-brain tensors are published.
"""
from __future__ import annotations
import json
import numpy as np
from .connectome import Connectome,CIRCUITS
from .contracts import FlySpec


def build(graph,compiler,participant,sampled_ids,var):
    # Bind the design snapshot to its compiled artifact before adding display data.
    spec=FlySpec.model_validate(participant['spec'])
    report=compiler.compile(spec)
    if report['artifact_id']!=participant['artifact_id']:
        raise ValueError('Replay design differs from compiled artifact')
    weights,manifest=compiler.load_weights(participant['artifact_id'],var)
    metadata=json.loads((graph.path/'neurons.json').read_text())
    by_id={str(ident):i for i,ident in enumerate(graph.ids)}
    anchors=np.array([by_id[ident] for ident in sampled_ids if ident in by_id],dtype=np.int32)
    incoming=np.flatnonzero(np.isin(graph.post,anchors))
    # Materialize the bounded incoming lists once, rather than scanning all
    # 25 million edges for each displayed anchor.
    incoming_by_anchor={int(i):incoming[graph.post[incoming]==i] for i in anchors}
    artifact=np.load(var/'artifacts'/participant['artifact_id']/'mutations.npz',allow_pickle=False)
    resolved='resolved_edge_idx' in artifact
    idx=artifact['resolved_edge_idx' if resolved else 'edge_idx']
    deltas=artifact['resolved_log_delta' if resolved else 'edge_delta']
    node_delta=None if resolved else artifact['node_delta']
    def log_delta(edge):
        p=int(np.searchsorted(idx,edge));extra=float(deltas[p]) if p<len(idx) and int(idx[p])==edge else 0.
        return extra if resolved else float(node_delta[graph.pre[edge]])+extra
    def strongest(indices):
        return indices[np.lexsort((indices,-graph.counts[indices].astype(np.int64)))[:3]]
    circuits={};display_groups=[]
    anatomical_side=getattr(graph,'side',np.zeros(graph.n))
    groups={key:set(int(i) for i in graph.groups[key]) for key,*_ in CIRCUITS}
    # Additional recorded sensory anchors are display groups, not mutations to
    # the canonical connectome or additions to the genome's circuit selectors.
    for key,kind,side,label,color in [("taste","gustatory",None,"Food taste","#c6a052"),
            ("touch_left","mechanosensory_tactile",1,"Left environmental touch","#66b695"),
            ("touch_right","mechanosensory_tactile",-1,"Right environmental touch","#76a8df")]:
        group={i for i,row in enumerate(metadata) if row.get('class')==kind and
               (side is None or anatomical_side[i]==side)}
        if not group.intersection(anchors):
            continue
        groups[key]=group
        display_groups.append({'id':key,'label':label,'name':label,'color':color,
                               'neuron_count':len(group),
                               'edge_count':sum(int(graph.indptr[i+1]-graph.indptr[i]) for i in group)})
    for key,group in groups.items():
        seeds=[int(i) for i in anchors if int(i) in group]
        edge_ids=set()
        for index in seeds:
            edge_ids.update(int(e) for e in strongest(np.arange(graph.indptr[index],graph.indptr[index+1])))
            edge_ids.update(int(e) for e in strongest(incoming_by_anchor[index]))
        chosen=set(seeds);edges=[]
        for edge in sorted(edge_ids):
            pre,post=int(graph.pre[edge]),int(graph.post[edge]);chosen.update([pre,post])
            baseline=float(np.float32(graph.counts[edge])*graph.signs[pre]*np.float32(.275));scale=float(np.exp(log_delta(edge)));weight=float(weights[edge])
            if not np.isclose(baseline*scale,weight,rtol=2e-6,atol=1e-6):raise ValueError('Model weight does not match resolved design')
            edges.append({'pre':str(graph.ids[pre]),'post':str(graph.ids[post]),'edge':edge,'count':int(graph.counts[edge]),'baseline_weight':baseline,'weight':weight,'multiplier':scale})
        circuits[key]={'neurons':[metadata[i] for i in sorted(chosen)],'edges':edges,'anchors':[str(graph.ids[i]) for i in seeds]}
    return {'schema':'brain-neighborhood/v1','artifact_id':participant['artifact_id'],'connectome_sha256':spec.connectome_sha256,'weights_sha256':manifest['phenotype']['weights_sha256'],'weight_units':'model synaptic strength','selection':'For each recorded sample neuron: three strongest incoming and three strongest outgoing edges by anatomical synapse count, ties by canonical edge index. Neighbor activity remains absent unless recorded.','circuits':circuits,'display_groups':display_groups}
