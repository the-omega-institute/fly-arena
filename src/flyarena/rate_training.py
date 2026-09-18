"""Backpropagation through the full sparse rate network; low-dimensional Adam.

Fits circuit multipliers to a declared odor→motor-response teaching task. Arena
fitness is measured separately by embodied evaluations, never inferred from loss.
"""
from __future__ import annotations
import numpy as np
from .rate import PROFILE, connection_matrix, response


def loss_and_gradient(matrix,membership,theta,stimulus,neurons,decoder,target,*,steps=100,tau_scale=1.,threshold_shift=0.):
    if not 1<=steps<=300:raise ValueError('Use 1–300 rate steps per teaching stimulus')
    gain=np.exp(membership@theta)
    decay=np.exp(-PROFILE['dt_ms']/(PROFILE['tau_ms']*tau_scale))
    r=np.zeros(matrix.shape[0]);history=[]
    transposed=matrix.transpose().tocsr()
    for _ in range(steps):
        drive=stimulus+.005*(transposed@(gain*r))
        z=np.maximum(drive-7.-threshold_shift,0)/20.
        slope=12.5*(1-np.tanh(z)**2)*(drive>7.+threshold_shift)
        history.append((r,slope))
        r=decay*r+(1-decay)*response(drive,7.+threshold_shift)
    error=r[neurons]/100.@decoder-target
    loss=float(np.mean(error**2))
    adjoint=np.zeros_like(r);np.add.at(adjoint,neurons,decoder@(2*error/len(error))/100.)
    gradient=np.zeros_like(theta)
    for previous,slope in reversed(history):
        q=.005*(matrix@((1-decay)*slope*adjoint))
        gradient+=membership.T@(q*gain*previous)
        adjoint=decay*adjoint+q*gain
    return loss,gradient


def fit(graph,weights,neurons,decoder,circuits,*,updates=3,steps=100,learning_rate=.02,tau_scale=1.,threshold_shift=0.,stimuli=((.8,.2),(.2,.8))):
    if not 1<=updates<=20 or not 1<=steps<=300 or not 0<learning_rate<=.05:raise ValueError('Bounded Adam settings required')
    if not circuits or len(set(circuits))!=len(circuits) or any(c not in graph.groups for c in circuits):raise ValueError('Choose distinct known circuits')
    from .calibrate import target
    matrix=connection_matrix(graph,weights)
    membership=np.zeros((graph.n,len(circuits)))
    for i,c in enumerate(circuits):membership[graph.groups[c],i]=1
    examples=[]
    for left,right in stimuli:
        if not (0<=left<=1 and 0<=right<=1):raise ValueError('Teaching odors must be in [0,1]')
        external=np.zeros(graph.n)
        for side,value in [('left',left),('right',right)]:external[graph.groups['olfactory_'+side]]=8+40*value
        examples.append((external,target(left,right)))
    if not 1<=len(examples)<=8:raise ValueError('Use 1–8 teaching stimuli')
    theta=np.zeros(len(circuits));m=theta.copy();v=theta.copy();history=[]
    for step in range(updates+1):
        values=[loss_and_gradient(matrix,membership,theta,x,neurons,decoder,y,steps=steps,tau_scale=tau_scale,threshold_shift=threshold_shift) for x,y in examples]
        loss=float(np.mean([x[0] for x in values]));grad=np.mean([x[1] for x in values],axis=0)
        if not np.isfinite(loss) or not np.isfinite(grad).all():raise FloatingPointError('Nonfinite training objective')
        history.append({'step':step,'response_mse':loss,'log_scale_delta':theta.tolist(),'gradient':grad.tolist()})
        if step==updates:break
        m=.9*m+.1*grad;v=.999*v+.001*grad**2
        theta=np.clip(theta-learning_rate*(m/(1-.9**(step+1)))/(np.sqrt(v/(1-.999**(step+1)))+1e-8),-.15,.15)
    return theta,{'algorithm':'adam-rate-response-v1','objective':'Final bilateral motor response MSE on declared odor teaching stimuli; not arena fitness',
        'stimuli':[list(s) for s in stimuli],'rate_steps':steps,'updates':updates,'learning_rate':learning_rate,'circuits':circuits,
        'neuron_count':graph.n,'edge_count':graph.e,'history':history,'within_match_plasticity':False}
