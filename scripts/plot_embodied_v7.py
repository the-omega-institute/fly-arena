"""Actual measured active-minus-passive knees; no inferred body poses."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
base=Path(__file__).resolve().parents[1]/'var/embodied-v7'
legs=['LF','LM','LH','RF','RM','RH']
fig,axs=plt.subplots(2,3,figsize=(12,7),sharex=True)
for i,(leg,ax) in enumerate(zip(legs,axs.flat)):
    for context,color in [('off','#455a64'),('neutral','#008577')]:
        a=np.load(base/f'contact/WT-{leg}-42-{context}-intact/samples.npz')
        p=np.load(base/f'contact/WT-{leg}-42-{context}-motorzero/samples.npz')
        ax.plot(a['ticks']*.0001,a['knees'][:,i]-p['knees'][:,i],color=color,label=context)
    ax.axvspan(.2,.5,color='#df9c3b',alpha=.12)
    for threshold in (-.01,.01):ax.axhline(threshold,color='#999',ls=':',lw=.8)
    ax.set_title(leg);ax.set_xlabel('Time (s)');ax.set_ylabel('Active − passive knee (rad)');ax.grid(alpha=.2)
axs[0,0].legend()
fig.suptitle('Actual tethered WT knees: chemical context moves joints, tactile clamp removes none\n48 fixed scientific trials; causal contact gate FAIL; no free-walking or ABC claim',fontsize=13)
fig.tight_layout(rect=(0,0,1,.91))
fig.savefig(base/'joint-phenotype.svg')
fig.savefig(base/'joint-phenotype.png',dpi=140)
plt.close(fig)
