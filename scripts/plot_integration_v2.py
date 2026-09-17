#!/usr/bin/env python3
"""Plot verified integration evidence; geometry and trajectories are never synthesized."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from flyarena.common import file_sha, write_json
from flyarena.experiments.probes import verify_evidence


def scene(ax, value, reports):
    points=[]
    for obstacle in value['obstacles']:
        x,y,_=obstacle['position'];w,h,_=obstacle['size']
        ax.add_patch(Rectangle((x-w/2,y-h/2),w,h,color='#8895a1',alpha=.4))
        points.extend([(x-w/2,y-h/2),(x+w/2,y+h/2)])
    for food in value['food']:
        x,y,_=food['position'];points.append((x,y))
        ax.scatter([x],[y],marker='*',s=155,c='#e6a126',edgecolor='#6d4707',zorder=6)
        ax.annotate('Food source',(x,y),xytext=(7,7),textcoords='offset points',fontsize=8)
    for report in reports:points.extend((p['x'],p['y']) for p in report['trajectory'])
    points=np.array(points);lo=points.min(axis=0)-2;hi=points.max(axis=0)+2
    ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),xlabel='x (mm)',ylabel='y (mm)')
    ax.set_aspect('equal',adjustable='box');ax.grid(alpha=.2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args();root=args.root
    names=['heldout-left','heldout-right','bifurcation-left','bifurcation-right']
    source_receipts={}
    fig,axes=plt.subplots(2,2,figsize=(12,10),layout='constrained')
    for ax,name in zip(axes.flat,names):
        r=json.loads((root/name/'report.json').read_text());verify_evidence(root/name,r)
        source_receipts[name]=r['receipt_sha256']
        t=r['trajectory'];scene(ax,r['scene'],[r]);ax.plot([p['x'] for p in t],[p['y'] for p in t],color='#2267a7',lw=1.8)
        ax.scatter(t[0]['x'],t[0]['y'],marker='o',s=35,c='#198364',label='Start',zorder=5)
        ax.scatter(t[-1]['x'],t[-1]['y'],marker='x',s=55,c='#c63e3e',label='End',zorder=5)
        latency=r['metrics']['food_latency_seconds'];latency='censored' if latency is None else f'{latency:g} s'
        ax.set_title(f"{name} | seed {r['seed']} | {r['duration_seconds']} s\nFood {r['metrics']['food_intake']:.2f}; first intake {latency}",fontsize=11)
        ax.legend(fontsize=8,loc='best')
    fig.suptitle('Full-graph neural-only motor transfer: held-out body evidence',fontsize=15)
    fig.savefig(root/'heldout-trajectories.png',dpi=160,bbox_inches='tight');plt.close(fig)
    experiment=json.loads((root/'experiment.json').read_text());assert experiment['status']=='complete'
    reports=experiment['reports'];assert len({r['condition_key'] for r in reports})==1
    fig,ax=plt.subplots(figsize=(11,9),layout='constrained');scene(ax,reports[0]['scene'],reports)
    for subject,r,color,style in zip(experiment['subjects'],reports,['#202b36','#b66b00','#2267a7'],['-','--','-.']):
        folder=root/'state/research/runs'/experiment['id']/'1'/str(r['seed'])/subject['role']
        verify_evidence(folder,r);source_receipts['experiment/'+subject['role']]=r['receipt_sha256'];t=r['trajectory']
        ax.plot([p['x'] for p in t],[p['y'] for p in t],color=color,ls=style,lw=2,label=f"{subject['role']}: {subject['fly_id']}")
        ax.scatter(t[-1]['x'],t[-1]['y'],color=color,s=35,marker='x')
    ax.legend(loc='upper left',bbox_to_anchor=(0,-.12),fontsize=8,title='Frozen subject identities')
    ax.set_title(f"Independent WT / official / submitted design\nSeed {reports[0]['seed']}, common {reports[0]['duration_seconds']} s horizon; crosses mark endpoints",fontsize=13)
    fig.savefig(root/'experiment-trajectories.png',dpi=160,bbox_inches='tight');plt.close(fig)
    write_json(root/'plots.json',{'script_sha256':file_sha(Path(__file__)),'figures':{n:file_sha(root/n) for n in ['heldout-trajectories.png','experiment-trajectories.png']},'condition_key':reports[0]['condition_key'],'source_receipts':source_receipts,'interpretation':'Measured trajectories and receipted initial sources. Divergence is not advantage; no biological validation.'})

if __name__=='__main__':main()
