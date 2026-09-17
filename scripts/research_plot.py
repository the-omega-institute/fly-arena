#!/usr/bin/env python3
"""Render measured engineering trajectories and cue-offset diagnostics."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flyarena.experiments.probes import verify_evidence

def plot(root):
    reports={p.parent.name:json.loads(p.read_text()) for p in root.glob('*/report.json')}
    for name,r in reports.items():verify_evidence(root/name,r)
    fig,axes=plt.subplots(2,2,figsize=(12,9),constrained_layout=True)
    axes=axes.flatten()
    for name,color,style in [('wt-left','#137c8b','-'),('wt-right','#9568aa','-'),('mutation-left','#d87028','--')]:
        tr=reports[name]['trajectory'];axes[0].plot([p['x'] for p in tr],[p['y'] for p in tr],style,color=color,label=name)
        scene=json.loads((root/name/'scene.json').read_text());food=scene['food'][0]['position'];axes[0].scatter(*food[:2],marker='x',color=color)
    axes[0].set(title='Off-axis: measured trajectories',xlabel='X (mm)',ylabel='Y (mm)');axes[0].axis('equal');axes[0].legend(fontsize=8)
    for name,color in [('blank-v1','#c94e4e'),('blank-v2','#137c8b'),('output-ablation','#767676')]:
        tr=reports[name]['trajectory'];axes[1].plot([p['x'] for p in tr],[p['y'] for p in tr],color=color,label=name)
    axes[1].set(title='Blank and output ablation',xlabel='X (mm)',ylabel='Y (mm)');axes[1].axis('equal');axes[1].legend(fontsize=8)
    tr=reports['delayed-cue']['neural_trace'];times=[p['time'] for p in tr]
    axes[2].plot(times,[(p['raw_odor_left']+p['raw_odor_right'])/2 for p in tr],label='mean raw cue',color='#9568aa')
    axes[2].plot(times,[(p['drive_left']+p['drive_right'])/2 for p in tr],label='mean applied action',color='#137c8b')
    axes[2].axvline(1.,color='#777',linestyle=':',label='cue removed')
    axes[2].set(title='Cue disappearance (not memory proof)',xlabel='Time (s)',ylabel='Declared fixture / action units');axes[2].legend(fontsize=8)
    from matplotlib.patches import Rectangle
    tr=reports['bifurcation']['trajectory'];scene=json.loads((root/'bifurcation/scene.json').read_text())
    axes[3].plot([p['x'] for p in tr],[p['y'] for p in tr],color='#137c8b',label='measured body trajectory')
    for wall in scene['obstacles']:
        x,y,_=wall['position'];w,h,_=wall['size']
        axes[3].add_patch(Rectangle((x-w/2,y-h/2),w,h,facecolor='#999',alpha=.5))
    food=scene['food'][0]['position'];axes[3].scatter(*food[:2],marker='x',color='#d87028',label='food')
    axes[3].set(title='Traversable physical bifurcation',xlabel='X (mm)',ylabel='Y (mm)',xlim=(-2,20),ylim=(-18,18));axes[3].set_aspect('equal');axes[3].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Full retained MaleCNS LIF + solo MuJoCo · engineering approximation',fontsize=13)
    fig.savefig(root/'measured-trajectories.png',dpi=180);plt.close(fig)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);plot(p.parse_args().root)
