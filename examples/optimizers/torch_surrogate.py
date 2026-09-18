"""Optional PyTorch surrogate-guided search; pip install torch on your device.

A small MLP predicts fitness from log circuit scales, then ranks a sampled pool.
Uses random warmup until four completed observations have distinct scores.
This trains an optimizer's surrogate, not a replacement fly brain or PPO agent.
Configuration: {"seed":42,"sigma":0.08,"steps":100,"pool":128}.
"""
from copy import deepcopy
import math


def propose(founder, history, generation, slot, config):
    import torch
    circuits=['olfactory','projection','descending']
    done=[m for m in history if m['generation']<generation and m['fitness'] is not None]
    parent=max(done,key=lambda m:(m['fitness'],-m['generation'],-m['slot']))['fly'] if done else founder
    spec=deepcopy(parent['spec'])
    spec.update(name=f'Surrogate G{generation+1}.{slot+1}',parent_id=parent['id'])
    if generation and slot==0:return spec
    def vector(fly):
        values={c:0. for c in circuits}
        for w in fly['spec']['weight_mutations']:
            if w['selector'] in values:values[w['selector']]+=math.log(w['scale'])
        return [values[c] for c in circuits]
    # Keep examples finite on ordinary laptops; all arbitrary code remains local.
    seed=int(config.get('seed',42))+100*generation+slot
    sigma=min(.3,max(.01,float(config.get('sigma',.08))))
    steps=min(1000,max(1,int(config.get('steps',100))))
    pool=min(1024,max(2,int(config.get('pool',128))))
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        candidates=(torch.tensor(vector(parent))+sigma*torch.randn(pool,3)).clamp(math.log(.5),math.log(2))
        chosen=candidates[0]
        if len(done)>=4 and max(m['fitness'] for m in done)>min(m['fitness'] for m in done):
            x=torch.tensor([vector(m['fly']) for m in done]);y=torch.tensor([m['fitness'] for m in done]).float()
            y=(y-y.mean())/y.std().clamp_min(1e-6)
            model=torch.nn.Sequential(torch.nn.Linear(3,16),torch.nn.Tanh(),torch.nn.Linear(16,1))
            optimizer=torch.optim.Adam(model.parameters(),lr=.02)
            for _ in range(steps):
                optimizer.zero_grad();loss=(model(x).squeeze(-1)-y).square().mean();loss.backward();optimizer.step()
            with torch.no_grad():chosen=candidates[model(candidates).squeeze(-1).argmax()]
    other=[w for w in spec['weight_mutations'] if w['selector'] not in circuits]
    spec['weight_mutations']=other+[{'selector':c,'scale':math.exp(float(chosen[i]))} for i,c in enumerate(circuits)]
    return spec
