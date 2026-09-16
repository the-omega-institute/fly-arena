"""Static scientific diagnostic plots from retained raw v10 evidence."""
from pathlib import Path
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flyarena.experiments.verify_v10 import read_stream, fields
from flyarena.experiments.cadence_v10 import PROFILE


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    reg=json.loads((args.root/'registration.json').read_text());sl=fields(reg['core_schema'])
    result=json.loads((args.root/'development-decision.json').read_text())
    fig,axes=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
    colors=['#258ca0','#d98428','#7251a3']
    for profile,style,label in [('historical','--','Historical'),(PROFILE,'-','V10')]:
        for color,case in zip(colors,['straight-008','straight-02','straight-04']):
            name=f'{profile}--42--{case}';r=result['trials'][name]
            t,x=read_stream(args.root/'development'/name/'core',40001,sum(n for _,n in reg['core_schema']),1)
            pos=x[:,sl['thorax_position']];rot=x[:,sl['thorax_rotation']].reshape(-1,3,3)
            axes[0,0].plot(pos[::100,0],pos[::100,1],style,color=color,label=f'{label} c={case[9:]}')
            axes[0,1].plot(t[::100]*reg['dt'],rot[::100,2,2],style,color=color)
            # 10ms finite differences show motion without 10kHz contact vibration dominating.
            speed=np.linalg.norm(np.diff(pos[::100],axis=0),axis=1)/.01
            axes[0,2].plot(t[100::100]*reg['dt'],speed,style,color=color)
        speed=[result['trials'][f'{profile}--42--{case}']['forward_mean_mm_s'] for case in ['straight-008','straight-02','straight-04']]
        axes[1,0].plot([.08,.2,.4],speed,style+'o',label=label)
        turncases=['turn-negative-08','turn-negative-04','turn-positive-04','turn-positive-08']
        turns=[result['trials'][f'{profile}--42--{case}']['net_active_yaw_rad'] for case in turncases]
        axes[1,1].plot([-.8,-.4,.4,.8],turns,style+'o',label=label)
    trials=[v for v in result['trials'].values() if v['conditions']['profile']==PROFILE]
    labels=[f"{v['conditions']['seed']} {v['conditions']['case'][0]}" for v in trials]
    gate_names=['upright','stop','swing','stance','straight_yaw','turn']
    grid=np.array([[1 if v['gates'].get(k) is True else 0 if v['gates'].get(k) is False else np.nan for k in gate_names] for v in trials])
    from matplotlib.colors import ListedColormap
    cmap=ListedColormap(['#ba5145','#33826d']);cmap.set_bad('#eeeeee')
    axes[1,2].imshow(grid,aspect='auto',cmap=cmap,vmin=0,vmax=1)
    axes[1,2].set_xticks(range(len(gate_names)),gate_names,rotation=35,ha='right');axes[1,2].set_yticks(range(len(labels)),labels,fontsize=7)
    axes[0,0].set(title='Actual thorax paths, seed 42',xlabel='world x (mm)',ylabel='world y (mm)');axes[0,0].axis('equal');axes[0,0].legend(fontsize=7)
    axes[0,1].set(title='Upright orientation',xlabel='time (s)',ylabel='thorax up · world up');axes[0,1].axhline(.8,color='red',lw=1)
    axes[0,2].set(title='Actual body speed (10 ms chords)',xlabel='time (s)',ylabel='mm/s');axes[0,2].axvspan(2.5,4,color='gray',alpha=.1)
    axes[1,0].set(title='Steady forward speed, seed 42',xlabel='common input',ylabel='mm/s');axes[1,0].legend()
    axes[1,1].set(title='Signed active yaw, seed 42',xlabel='asymmetry',ylabel='radians');axes[1,1].axhline(0,color='gray',lw=1);axes[1,1].legend()
    axes[1,2].set_title('V10 reconstructed gates: green pass, red fail, gray N/A',fontsize=9)
    for ax in axes.flat:
        if ax is not axes[1,2]:ax.grid(alpha=.2)
    fig.suptitle('Cadence-normalized hybrid v10 — registered development panel\nAll outcomes retained; no tuning; mechanical failure blocks neural interpretation',fontsize=14)
    fig.savefig(args.output,dpi=170)

if __name__=='__main__':main()
