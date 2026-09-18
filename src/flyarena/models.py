"""Supported brain dynamics; platform identity and optimizers stay outside this registry."""
from .neural import PROFILE as LIF_PROFILE, Brain
from .rate import PROFILE as RATE_PROFILE, RateBrain

PROFILES={p['id']:p for p in (LIF_PROFILE,RATE_PROFILE)}

def profile(ident):
    if ident not in PROFILES:raise ValueError('Unsupported neural model')
    return PROFILES[ident]

def make_brain(ident,graph,weights,params):
    profile(ident)
    cls=Brain if ident==LIF_PROFILE['id'] else RateBrain
    return cls(graph,weights,params['tau_scale'],params['threshold_shift_mv'])

def require_model_bridge(ident,bridge):
    profile(ident)
    if ident!=LIF_PROFILE['id'] and bridge!='legacy-v1':
        raise ValueError('Continuous-rate brain supports the legacy arena bridge only; research v2 remains LIF-only')

def catalog():
    return [{'id':p['id'],'profile':p,'available':True,'spiking':p['id']==LIF_PROFILE['id'],
             'bridge_profiles':['legacy-v1','sensorimotor-research-v2'] if p['id']==LIF_PROFILE['id'] else ['legacy-v1']}
            for p in PROFILES.values()]
