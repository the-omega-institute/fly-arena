"""Experimental continuous-rate dynamics on every retained anatomical edge.

The same signed weights drive a bounded firing-rate approximation, not spikes.
The shared legacy decoder was fitted to LIF; transfer is explicitly experimental.
"""
from __future__ import annotations
import numpy as np
from scipy.sparse import csr_matrix

PROFILE = {
    'id':'malecns-rate-cpu-v1', 'dt_ms':1.0, 'tau_ms':20.0,
    'synaptic_gain_seconds':.005, 'threshold_mv':7.0, 'response_width_mv':20.0,
    'max_rate_hz':250.0, 'integration':'exponential-Euler; bounded tanh rectifier',
    'scope':'Full retained MaleCNS graph; continuous rates, no discrete spikes, no refractory or synaptic delay',
    'readout':'Transfer of frozen LIF legacy decoder; experimental, not recalibrated',
}


def connection_matrix(graph, weights):
    # W is source × target, preserving every edge including zero-effective edges.
    return csr_matrix((np.asarray(weights,dtype=np.float64),graph.post,graph.indptr),shape=(graph.n,graph.n))


def response(drive, threshold=7.):
    return PROFILE['max_rate_hz']*np.tanh(np.maximum(drive-threshold,0)/PROFILE['response_width_mv'])


class RateBrain:
    total_spikes = None  # Absence of spike events must not be presented as zero spikes.

    def __init__(self,graph,weights=None,tau_scale=1.,threshold_shift=0.):
        self.graph=graph
        self.weights=graph.baseline_weights() if weights is None else weights
        self.matrix=connection_matrix(graph,self.weights).transpose().tocsr()
        self.decay=np.exp(-PROFILE['dt_ms']/(PROFILE['tau_ms']*tau_scale))
        self.threshold=PROFILE['threshold_mv']+threshold_shift
        self.reset()

    def reset(self):
        self.rates=np.zeros(self.graph.n,dtype=np.float64)
        self.external=np.zeros(self.graph.n,dtype=np.float64)
        self.tick=0

    def stimulate(self,left,right,visual_left=0.,visual_right=0.,touch=0.):
        return self.stimulate_multimodal(left, right, visual_left, visual_right, touch)

    def stimulate_multimodal(self, odor_left, odor_right, visual_left=0., visual_right=0., touch=0.):
        from .experiments.embodied_sensor import apply
        return apply(self.external, self.graph, odor_left=odor_left, odor_right=odor_right,
                     visual_left=visual_left, visual_right=visual_right, touch=touch)

    def advance(self,steps=100):
        if not isinstance(steps,(int,np.integer)) or steps<0:raise ValueError('steps must be a nonnegative integer')
        end=self.tick+int(steps)
        for _ in range(end//10-self.tick//10):
            drive=self.external+PROFILE['synaptic_gain_seconds']*(self.matrix@self.rates)
            self.rates=self.decay*self.rates+(1-self.decay)*response(drive,self.threshold)
        self.tick=end
        if not np.isfinite(self.rates).all():raise FloatingPointError('Non-finite rate state')
        return self.rates.copy()

    def trace(self):
        return {key:float(self.rates[self.graph.groups[key]].mean()) if len(self.graph.groups[key]) else 0.
                for key in ['olfactory','projection','local','memory','readout','descending','visual','motor']}

    def checkpoint(self):
        return {'rates':self.rates.copy(),'external':self.external.copy(),'tick':np.array(self.tick)}

    def restore(self,state):
        if set(state)!={'rates','external','tick'}:raise ValueError('Incomplete rate checkpoint')
        tick=np.asarray(state['tick'])
        if tick.shape!=() or tick.dtype.kind not in 'iu' or tick<0:raise ValueError('Invalid rate clock')
        for key in ('rates','external'):
            value=np.asarray(state[key])
            if value.shape!=(self.graph.n,) or not np.isfinite(value).all():raise ValueError('Invalid rate checkpoint')
        if np.any(state['rates']<0) or np.any(state['rates']>PROFILE['max_rate_hz']):raise ValueError('Invalid firing rates')
        self.rates[:]=state['rates'];self.external[:]=state['external'];self.tick=int(tick)
