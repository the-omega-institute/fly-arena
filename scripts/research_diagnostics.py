#!/usr/bin/env python3
"""Persist transparent sensor/readout diagnostics without changing frozen artifacts."""
import argparse
import json
from pathlib import Path
import numpy as np
from flyarena.common import DATA, file_sha, write_json
from flyarena.experiments.sensor import encode_odor

def diagnostics(data, output):
    old=json.loads((data/'connectome/readout.json').read_text())
    new=json.loads((data/'connectome/research-v2/readout.json').read_text())
    rows=[]
    for raw in [(0.,0.),(2.,1.2),(1.2,2.),(.42,.38),(.38,.42)]:
        clipped=np.clip(raw,0,1);contrast=(clipped[0]-clipped[1])/(sum(clipped)+.05)
        encoded=np.clip([np.mean(clipped)+2*contrast,np.mean(clipped)-2*contrast],0,1)
        rows.append({'raw':raw,'v1_encoded':encoded.tolist(),'v2_encoded':encode_odor(*raw).tolist()})
    def directions(meta):
        rows=[r for r in meta['validation'] if abs(r['odor'][0]-r['odor'][1])>.01]
        return {'correct':sum((r['observed'][1]-r['observed'][0])*(r['odor'][0]-r['odor'][1])>0 for r in rows),
                'count':len(rows),'mean_command_mae':float(np.mean([r['mae'] for r in meta['validation']]))}
    report={'sensor_saturation_examples':rows,'v1_declared_zero_cue_target':[.85,.85],
            'v1_heldouts':directions(old),'v2_heldouts':directions(new),
            'v1_readout_sha256':file_sha(data/'connectome/readout.npz'),
            'v2_readout_sha256':file_sha(data/'connectome/research-v2/readout.npz'),
            'v2_quality_gates':new['quality_gates'],
            'interpretation':'Heldout sets differ across versions; do not interpret aggregate MAE as a paired statistical effect. Physical transfer and blank behavior are measured separately in engineering validation.'}
    # numpy bool sums need explicit Python int for canonical JSON.
    for version in ('v1_heldouts','v2_heldouts'):report[version]['correct']=int(report[version]['correct'])
    write_json(output,report)
    print(json.dumps(report,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=DATA);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();diagnostics(a.data,a.output)
