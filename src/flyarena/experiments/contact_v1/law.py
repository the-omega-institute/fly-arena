"""Selected law, pure numeric state transactions; no native or graph imports.

Tests inject authored intent/reference providers. advance_intent is prospective
native-equation code and is not executed by the source-only fixture flight.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import hashlib
import numpy as np
from .contracts import (Binding, Contact, Observation, ContractError, DT, SILENCE,
                        STATE_VERSION, CORRECTION_NORMS, MODES, array, drives,
                        encode, decode, observation_state, observation_from_state)

TAU=.003
BODY_TAU=.05
HEIGHT=.05
REGULARIZER=.02
DWELL=30
WAIT_LIMIT=500
LAG_LIMIT=np.pi/2
TWO_PI=2*np.pi


@dataclass(frozen=True)
class Action:
    angles: np.ndarray  # (6,7), anatomical order
    adhesion: np.ndarray  # (6,), bool


@dataclass(frozen=True)
class Proposal:
    owner_token: object  # process-local capability, never checkpointed
    revision: int
    predecessor: str  # exact scientific predecessor state, independently of revision
    generation: int
    state: dict
    action: Action


def advance_intent(theta, magnitude, binding, common, asymmetry):
    """Prospective native Euler equations. No actual CPG object is instantiated."""
    nu=np.full(6,12.*common/.6)
    w=binding.coupling*(common/.6)
    target=np.repeat([1-asymmetry,1+asymmetry],3)
    difference=theta[np.newaxis,:]-theta[:,np.newaxis]
    dtheta=(TWO_PI*nu+(magnitude*w*np.sin(difference-binding.biases)).sum(axis=1))*DT
    return theta+dtheta, magnitude+DT*20.*(target-magnitude)


def inside_eroded_hull(points, point, margin=.02):
    """Strict CCW convex-hull halfplanes; exact duplicate/collinear elimination."""
    points=np.asarray(points,dtype=np.float64); point=np.asarray(point,dtype=np.float64)
    if points.size==0: return False
    if points.ndim!=2 or points.shape[1]!=2 or point.shape!=(2,) or not np.isfinite(points).all() or not np.isfinite(point).all():
        raise ContractError('capture hull inputs')
    pts=sorted(set(map(tuple,points.tolist())))
    if len(pts)<3: return False
    def cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lo=[]; hi=[]
    for p in pts:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0: hi.pop()
        hi.append(p)
    hull=lo[:-1]+hi[:-1]
    if len(hull)<3: return False
    for a,b in zip(hull,hull[1:]+hull[:1]):
        if cross(a,b,point)<=margin*np.hypot(b[0]-a[0],b[1]-a[1]): return False
    return True


def release_order(theta,phi,pending):
    return sorted(pending,key=lambda i:(-float(theta[i]-phi[i]),i))


def regularized_velocity(A,b,z_native):
    A=np.asarray(A,dtype=np.float64).reshape(-1,7); b=np.asarray(b,dtype=np.float64)
    z_native=array(z_native,(7,),'native velocity')
    if b.shape!=(A.shape[0],) or not np.isfinite(A).all() or not np.isfinite(b).all():
        raise ContractError('task rows')
    if not len(A): return z_native.copy(),np.empty(0)
    h=A.T@A+REGULARIZER**2*np.eye(7)
    rhs=A.T@b+REGULARIZER**2*z_native
    try:
        chol=np.linalg.cholesky(h)
        z=np.linalg.solve(chol.T,np.linalg.solve(chol,rhs))
    except np.linalg.LinAlgError as exc:
        raise ContractError('task Cholesky failed') from exc
    if not np.isfinite(z).all(): raise ContractError('nonfinite velocity solve')
    return z,A@z-b


def capped_command(old_command,old_native,next_native,z,z_native,lower,upper,index):
    for name,x in (('old_command',old_command),('old_native',old_native),('next_native',next_native),('z',z),('z_native',z_native)):
        array(x,(7,),name)
    if np.any(next_native<lower) or np.any(next_native>upper): raise ContractError('native reference outside limits')
    C=CORRECTION_NORMS[index]
    old_x=old_command-old_native
    if np.linalg.norm(old_x)>80*C+1e-12: raise ContractError('old correction bound')
    e=DT*(z-z_native); norm=float(np.linalg.norm(e)); stepcap=800*DT*C
    limited=e*min(1.,stepcap/norm) if norm else e.copy()
    before=old_x+limited; length=float(np.linalg.norm(before)); radius=80*C
    radial=before*min(1.,radius/length) if length else before.copy()
    before_clip=next_native+radial
    command=np.clip(before_clip,lower,upper)
    x=command-next_native
    if (np.linalg.norm(x)>radius+1e-12 or
            np.linalg.norm(command-old_command)>np.linalg.norm(next_native-old_native)+stepcap+1e-12):
        raise ContractError('post-projection norm/rate bound')
    return command, {'requested_increment':e,'limited_increment':limited,
                     'before_ball':before,'after_ball':radial,'correction':x,
                     'range_flags':command!=before_clip,
                     'native_increment':next_native-old_native}


def shared_twist(binding,obs,modes,z_native,z0):
    contacts=[c for c in obs.contacts if c.leg>=0 and c.force[0]>0 and modes[c.leg]=='SUPPORT']
    ell=max(.05,np.sqrt(np.mean([np.dot((c.point-obs.thorax_pos)[:2],(c.point-obs.thorax_pos)[:2]) for c in contacts]))) if contacts else .05
    A=[]; b=[]
    for i in range(6):
        leg=[c for c in contacts if c.leg==i]
        scale=np.sqrt(len(leg)) if leg else 1.
        for con in leg:
            r=con.point-obs.thorax_pos
            A.extend(np.array([[1.,0.,-r[1]/ell],[0.,1.,r[0]/ell]])/scale)
            rhs=-(con.jacobian[:,binding.vadr[i]]@z_native[i]+con.passive_velocity)[:2]
            b.extend(rhs/scale)
    x=np.zeros(3)
    if A:
        A=np.asarray(A); b=np.asarray(b)
        u,s,vh=np.linalg.svd(A,full_matrices=False)
        cutoff=64*np.finfo(np.float64).eps*max(1.,float(s.max()))
        reciprocal=np.zeros_like(s); reciprocal[s>cutoff]=1/s[s>cutoff]
        x=vh.T@(reciprocal*(u.T@b))
    velocity=np.array([x[0],x[1],np.clip((z0-obs.thorax_pos[2])/BODY_TAU,-1.,1.)])
    omega=np.cross(obs.thorax_rotation[:,2],np.array([0.,0.,1.]))/BODY_TAU
    omega[2]=x[2]/ell
    if not np.isfinite(velocity).all() or not np.isfinite(omega).all(): raise ContractError('shared twist')
    return velocity,omega


def task_rows(binding,obs,state,i,dphi,body_velocity,body_omega):
    rows=[]; targets=[]; vadr=binding.vadr[i]; active_velocity=obs.qvel[vadr]
    mode=state['modes'][i]; centroid=obs.distal[i]; Jc=obs.distal_jacobians[i]
    measured_centroid_velocity=Jc@obs.qvel
    contacts=[c for c in obs.contacts if c.leg==i and c.force[0]>0]
    def scalar(J,measured,target,scale=1.):
        a=np.asarray(J)[vadr]
        rows.append(a/scale)
        targets.append((float(target)-float(measured)+float(a@active_velocity))/scale)
    if mode in ('LIFT','TRANSFER'):
        for m in range(5):
            J=obs.minimum_jacobians[i,m,2]
            target=np.clip((HEIGHT-obs.minima[i,m,2])/TAU,-HEIGHT/TAU,HEIGHT/TAU)
            scalar(J,J@obs.qvel,target,np.sqrt(5.))
        A=state['ap0'][i]; speed=0.
        if mode=='TRANSFER':
            beta=binding.beta[i]; origin=state['cycle'][i]*TWO_PI
            # Initial partial segments begin at the observed phase, not at an invented PEP.
            start=state['transfer_start'][i]
            finish=origin+2*beta/3
            duration=finish-start
            if duration<=0: s=1.; speed=0.
            else:
                s=float(np.clip((state['phi'][i]-start)/duration,0.,1.))
                speed=state['excursion'][i]*6*s*(1-s)*dphi[i]/(DT*duration)
            A+=state['excursion'][i]*(3*s*s-2*s*s*s)
        relative=centroid-obs.thorax_pos
        relative_v=measured_centroid_velocity-obs.thorax_velocity-np.cross(obs.thorax_omega,relative)
        for axis,target,desired_rate in ((0,A,speed),(1,state['lateral0'][i],0.)):
            direction=obs.thorax_rotation[:,axis]
            coordinate=float(direction@relative); rate=float(direction@relative_v)
            scalar(direction@Jc,rate,desired_rate+(target-coordinate)/TAU)
    elif mode in ('LAND','REACQUIRE'):
        xy=np.clip((state['landing_xy'][i]-centroid[:2])/TAU,-HEIGHT/TAU,HEIGHT/TAU)
        for axis in range(2): scalar(Jc[axis],measured_centroid_velocity[axis],xy[axis])
        J=obs.minimum_jacobians[i,4,2]
        target=0. if state['distal_force'][i]>0 else -min(HEIGHT/TAU,max(obs.minima[i,4,2],0.)/TAU)
        scalar(J,J@obs.qvel,target)
        scale=np.sqrt(max(1,len(contacts)))
        for con in contacts:
            for tangent in con.frame[1:]:
                scalar(tangent@con.jacobian,tangent@con.velocity,0.,scale)
    elif mode in ('SUPPORT','RELEASE_WAIT'):
        scale=np.sqrt(max(1,len(contacts)))
        for con in contacts:
            r=con.point-obs.thorax_pos; n=con.frame[0]; Pt=np.eye(3)-np.outer(n,n)
            target=-body_velocity-np.cross(body_omega,r)-con.passive_velocity-Pt@con.velocity
            rows.extend(con.jacobian[:,vadr]/scale); targets.extend(target/scale)
    else: raise ContractError('unknown mode')
    return np.asarray(rows,dtype=np.float64).reshape(-1,7),np.asarray(targets,dtype=np.float64)


class Controller:
    """State transactions; references must be immutable and side-effect-free.

    references.angles(phi[6], r[6]) -> (6,7)
    references.excursion(leg, observation, release_magnitude) -> mm
    The native adapter supplies references bound to an expendable geometry workspace.
    """
    def __init__(self,binding,theta,neutral_angles,adhesion,rng_state):
        self.binding=deepcopy(binding).validate()
        theta=array(theta,(6,),'initial theta')
        angles=array(neutral_angles,(6,7),'neutral angles')
        adhesion=np.asarray(adhesion)
        if adhesion.shape!=(6,) or adhesion.dtype.kind!='b': raise ContractError('adhesion')
        if np.any(angles<binding.lower) or np.any(angles>binding.upper): raise ContractError('initial ranges')
        self.state={
            'theta':theta.copy(),'magnitude':np.zeros(6),'phi':theta.copy(),
            'modes':['SUPPORT']*6,'resume_modes':['SUPPORT']*6,
            'cycle':np.floor(theta/TWO_PI).astype(np.int64),'partial':np.ones(6,dtype=bool),
            'clear_count':np.zeros(6,dtype=np.int64),'load_count':np.zeros(6,dtype=np.int64),
            'distal_count':np.zeros(6,dtype=np.int64),'wait_count':np.zeros(6,dtype=np.int64),
            'ap0':np.zeros(6),'lateral0':np.zeros(6),'release_height':np.zeros(6),
            'release_magnitude':np.zeros(6),'excursion':np.zeros(6),
            'landing_xy':np.zeros((6,2)),'transfer_start':np.zeros(6),
            'total_force':np.zeros(6),'distal_force':np.zeros(6),
            'angles':angles.copy(),'adhesion':adhesion.copy(),'native_reference':angles.copy(),
            'correction':np.zeros((6,7)),'z0':None,'initialized':False,'last_tick':-1,
            'generation':0,'rng_state':deepcopy(rng_state),'last_observation':None,
            'diagnostics':{},'base_frequency':np.full(6,12.),'base_coupling':binding.coupling.copy(),
            'phase_biases':binding.biases.copy(),'convergence':np.full(6,20.),
            'intrinsic_frequency':np.full(6,12.),'intrinsic_amplitude':np.ones(6),
            'coupling':binding.coupling.copy()}
        self._keys=set(self.state)
        self._owner_token=object()
        self._revision=0
        self.validate_state(self.state)

    def action(self):
        return Action(self.state['angles'].copy(),self.state['adhesion'].copy())

    def _latch(self,s,obs,i,references,partial=False):
        relative=obs.distal[i]-obs.thorax_pos
        s['ap0'][i]=obs.thorax_rotation[:,0]@relative
        s['lateral0'][i]=obs.thorax_rotation[:,1]@relative
        s['release_height'][i]=obs.distal[i,2]
        s['release_magnitude'][i]=s['magnitude'][i]
        s['landing_xy'][i]=obs.distal[i,:2]
        s['transfer_start'][i]=s['cycle'][i]*TWO_PI+self.binding.beta[i]/3
        if partial and s['modes'][i]=='TRANSFER': s['transfer_start'][i]=s['phi'][i]
        s['excursion'][i]=float(references.excursion(i,obs,s['release_magnitude'][i]))
        if not np.isfinite(s['excursion'][i]) or s['excursion'][i]<0: raise ContractError('native excursion')
        s['partial'][i]=partial

    def propose(self,u,obs,references,*,intent=advance_intent):
        common,asymmetry=drives(u)
        if common<=SILENCE: return None  # exact no sensor/provider/state/RNG access
        if not isinstance(obs,Observation): raise ContractError('versioned observation required')
        obs.validate(self.binding,self.state['last_tick'])
        self.validate_prestate(obs.tick,obs.prior_qpos,obs.prior_qvel)
        predecessor=self.checkpoint_json()
        s=deepcopy(self.state); b=self.binding
        # A gap from silence intentionally breaks dwell continuity.
        if obs.tick!=s['last_tick']+1:
            for key in ('clear_count','load_count','distal_count'): s[key][:]=0
        total=np.zeros(6); distal=np.zeros(6)
        nonfoot=False
        for con in obs.contacts:
            if con.force[0]>0:
                if con.leg<0: nonfoot=True
                else:
                    total[con.leg]+=con.force[0]
                    if con.geom==b.foot_geoms[con.leg,4]: distal[con.leg]+=con.force[0]
        clear=(total==0)&(obs.minima[:,:,2].min(axis=1)>.02)
        for key,predicate in (('clear_count',clear),('load_count',total>0),('distal_count',distal>0)):
            s[key]=np.where(predicate,np.minimum(s[key]+1,DWELL),0).astype(np.int64)
        s['total_force']=total; s['distal_force']=distal
        if not s['initialized']:
            s['z0']=float(obs.thorax_pos[2]); s['initialized']=True
            for i in range(6):
                phase=s['phi'][i]-s['cycle'][i]*TWO_PI; beta=b.beta[i]
                s['modes'][i]='LIFT' if phase<beta/3 else 'TRANSFER' if phase<2*beta/3 else 'LAND' if phase<beta else 'SUPPORT'
                if s['modes'][i] in ('LIFT','TRANSFER','LAND'): self._latch(s,obs,i,references,partial=True)
                else:
                    s['landing_xy'][i]=obs.distal[i,:2]
                    s['transfer_start'][i]=s['cycle'][i]*TWO_PI+beta/3
        theta_old=s['theta'].copy(); phi_old=s['phi'].copy()
        theta_next,r_next=intent(theta_old.copy(),s['magnitude'].copy(),b,common,asymmetry)
        theta_next=array(theta_next,(6,),'proposed intent theta'); r_next=array(r_next,(6,),'proposed magnitude')
        dtheta=theta_next-theta_old
        if np.any(dtheta<=0) or np.any(r_next<0) or np.any(r_next>1.8+1e-12): raise ContractError('intent increment/magnitude')
        s['intrinsic_frequency']=np.full(6,12.*common/.6)
        s['intrinsic_amplitude']=np.repeat([1-asymmetry,1+asymmetry],3)
        s['coupling']=b.coupling*(common/.6)
        # Release latches use the current proposed intent magnitude.
        s['magnitude']=r_next.copy()
        moved=np.zeros(6); blocked=np.zeros(6,dtype=bool); transitioned=np.zeros(6,dtype=bool)
        for i in range(6):
            mode=s['modes'][i]; origin=s['cycle'][i]*TWO_PI; beta=b.beta[i]
            if mode in ('SUPPORT','RELEASE_WAIT') and total[i]==0:
                s['resume_modes'][i]=mode; s['modes'][i]='REACQUIRE'
                s['landing_xy'][i]=obs.distal[i,:2]; mode='REACQUIRE'
            if mode=='REACQUIRE':
                if s['distal_count'][i]>=DWELL:
                    s['modes'][i]=s['resume_modes'][i]; transitioned[i]=True
                else: blocked[i]=True
                continue
            if mode=='RELEASE_WAIT': blocked[i]=True; continue
            boundary=origin+({'LIFT':beta/3,'TRANSFER':2*beta/3,'LAND':beta,'SUPPORT':TWO_PI}[mode])
            if s['phi'][i]>=boundary:
                if mode=='LIFT':
                    if s['clear_count'][i]>=DWELL:
                        s['modes'][i]='TRANSFER'; s['transfer_start'][i]=boundary; transitioned[i]=True
                    else: blocked[i]=True
                elif mode=='TRANSFER':
                    s['modes'][i]='LAND'; s['landing_xy'][i]=obs.distal[i,:2]; transitioned[i]=True
                elif mode=='LAND':
                    if s['distal_count'][i]>=DWELL: s['modes'][i]='SUPPORT'; transitioned[i]=True
                    else: blocked[i]=True
                else: s['modes'][i]='RELEASE_WAIT'; transitioned[i]=True; blocked[i]=True
                continue
            advance=min(2*dtheta[i],theta_next[i]-s['phi'][i],boundary-s['phi'][i])
            if advance<0: raise ContractError('negative phase debt')
            s['phi'][i]+=advance; moved[i]=advance
        pending=[i for i in range(6) if s['modes'][i]=='RELEASE_WAIT']
        supports={i for i in range(6) if s['modes'][i] in ('SUPPORT','RELEASE_WAIT') and s['load_count'][i]>=DWELL and s['adhesion'][i]}
        xi=obs.com[:2]+obs.com_velocity[:2]*np.sqrt(max(obs.com[2],0.)/obs.gravity)
        veto=nonfoot or obs.thorax_rotation[2,2]<=.8 or any(m in ('LAND','REACQUIRE') for m in s['modes'])
        admitted=[]
        for i in release_order(theta_next,s['phi'],pending):
            remaining=supports-{i}
            points=[con.point[:2] for con in obs.contacts if con.leg in remaining and con.force[0]>0]
            if not veto and inside_eroded_hull(points,xi):
                supports.discard(i); admitted.append(i); blocked[i]=False
                s['cycle'][i]+=1; s['modes'][i]='LIFT'
                self._latch(s,obs,i,references)
                s['clear_count'][i]=0; s['distal_count'][i]=0
                # No crossing into a second phase segment in this tick.
        s['wait_count']=np.where(blocked,s['wait_count']+1,0).astype(np.int64)
        if np.any(s['wait_count']>WAIT_LIMIT): raise ContractError('stall: active gate wait exceeded500')
        lag=theta_next-s['phi']
        if np.any(lag < -1e-12) or np.any(lag>LAG_LIMIT): raise ContractError('phase_lag: pi/2 exceeded')
        s['theta']=theta_next; s['magnitude']=r_next
        next_native=np.asarray(references.angles(s['phi'].copy(),r_next.copy()),dtype=np.float64)
        array(next_native,(6,7),'native reference')
        if np.any(next_native<b.lower) or np.any(next_native>b.upper): raise ContractError('native template outside compiled ranges')
        old_native=s['native_reference'].copy()
        z_native=(next_native-old_native)/DT
        velocity,omega=shared_twist(b,obs,s['modes'],z_native,s['z0'])
        per_leg=[]; commands=np.empty((6,7))
        for i in range(6):
            A,target=task_rows(b,obs,s,i,moved,velocity,omega)
            z,residual=regularized_velocity(A,target,z_native[i])
            command,projection=capped_command(s['angles'][i],old_native[i],next_native[i],z,z_native[i],b.lower[i],b.upper[i],i)
            commands[i]=command
            per_leg.append({'A':A,'b':target,'z':z,'residual':residual,
                            'measured_active_task_velocity':A@obs.qvel[b.vadr[i]], **projection})
        s['angles']=commands; s['native_reference']=next_native.copy(); s['correction']=commands-next_native
        s['adhesion']=np.array([mode not in ('LIFT','TRANSFER') for mode in s['modes']],dtype=bool)
        s['diagnostics']={'legs':per_leg,'lag':lag,'phase_increment':s['phi']-phi_old,
                          'admitted':admitted,'capture_point':xi,'release_veto':bool(veto),
                          'positive_nonfoot':nonfoot,'body_velocity':velocity,'body_omega':omega,
                          'minimum_heights':obs.minima[:,:,2].copy(),'actuator_force':obs.actuator_force.copy(),
                          'forcecap_observed':np.abs(obs.actuator_force[:42])>=65.}
        s['last_observation']=observation_state(obs); s['last_tick']=obs.tick; s['generation']+=1
        self.validate_state(s)
        return Proposal(self._owner_token,self._revision,hashlib.sha256(predecessor.encode()).hexdigest(),
                        self.state['generation'],s,Action(commands.copy(),s['adhesion'].copy()))

    def validate_prestate(self,tick,qpos,qvel):
        """Consecutive active packets must continue the exact accepted endpoint.

        A deliberate physical silence gap breaks dwell history, so its immediate
        physical prestate is checked by the port recorder rather than old sensors.
        """
        if self.state['initialized'] and tick==self.state['last_tick']+1:
            previous=self.state['last_observation']
            if previous is None or not np.array_equal(qpos,previous['qpos']) or not np.array_equal(qvel,previous['qvel']):
                raise ContractError('consecutive interval prestate mismatch')

    def validate_proposal(self,proposal):
        """Shared complete ownership check, before any controller/port write."""
        predecessor=hashlib.sha256(self.checkpoint_json().encode()).hexdigest()
        if (not isinstance(proposal,Proposal) or proposal.owner_token is not self._owner_token
                or proposal.revision!=self._revision or proposal.predecessor!=predecessor
                or proposal.generation!=self.state['generation']):
            raise ContractError('stale/foreign proposal predecessor')
        self.validate_state(proposal.state)
        if (proposal.state['generation']!=self.state['generation']+1
                or proposal.state['last_tick']<=self.state['last_tick']
                or not np.array_equal(proposal.action.angles,proposal.state['angles'])
                or not np.array_equal(proposal.action.adhesion,proposal.state['adhesion'])):
            raise ContractError('action/state successor mismatch')
        obs=proposal.state['last_observation']
        self.validate_prestate(obs['tick'],obs['prior_qpos'],obs['prior_qvel'])

    def commit(self,proposal):
        self.validate_proposal(proposal)
        staged=deepcopy(proposal.state)
        self.state=staged
        self._revision+=1
        return self.action()

    def step(self,u,obs,references,*,intent=advance_intent):
        proposal=self.propose(u,obs,references,intent=intent)
        return self.action() if proposal is None else self.commit(proposal)

    def validate_state(self,s):
        if not isinstance(s,dict) or set(s)!=self._keys: raise ContractError('incomplete controller state')
        for name in ('theta','magnitude','phi','ap0','lateral0','release_height','release_magnitude','excursion','transfer_start','total_force','distal_force','base_frequency','convergence','intrinsic_frequency','intrinsic_amplitude'):
            array(s[name],(6,),name)
        for name in ('cycle','clear_count','load_count','distal_count','wait_count'):
            a=array(s[name],(6,),name,kind='i')
            if np.any(a<0): raise ContractError('negative counter')
        for name in ('modes','resume_modes'):
            if not isinstance(s[name],list) or len(s[name])!=6 or any(m not in MODES for m in s[name]): raise ContractError('mode schema')
        for name in ('angles','native_reference','correction'): array(s[name],(6,7),name)
        array(s['landing_xy'],(6,2),'landing_xy')
        for name in ('base_coupling','phase_biases','coupling'): array(s[name],(6,6),name)
        for name in ('adhesion','partial'):
            if not isinstance(s[name],np.ndarray) or s[name].shape!=(6,) or s[name].dtype.kind!='b': raise ContractError('bool state')
        if type(s['initialized']) is not bool or type(s['generation']) is not int or s['generation']<0 or type(s['last_tick']) is not int or s['last_tick']< -1:
            raise ContractError('state scalar')
        if s['initialized'] and (type(s['z0']) is not float or not np.isfinite(s['z0'])) or not s['initialized'] and s['z0'] is not None:
            raise ContractError('height reference')
        b=self.binding
        if (np.any(s['angles']<b.lower) or np.any(s['angles']>b.upper) or np.any(s['native_reference']<b.lower) or np.any(s['native_reference']>b.upper)
                or not np.array_equal(s['correction'],s['angles']-s['native_reference']) or np.any(np.linalg.norm(s['correction'],axis=1)>80*CORRECTION_NORMS+1e-12)):
            raise ContractError('command/correction state')
        if np.any(s['theta']-s['phi']>LAG_LIMIT) or np.any(s['theta']-s['phi']< -1e-12) or np.any(s['wait_count']>WAIT_LIMIT) or any(np.any(s[k]>DWELL) for k in ('clear_count','load_count','distal_count')):
            raise ContractError('phase/counter bound')
        if not np.array_equal(s['base_frequency'],np.full(6,12.)) or not np.array_equal(s['convergence'],np.full(6,20.)) or not np.array_equal(s['base_coupling'],b.coupling) or not np.array_equal(s['phase_biases'],b.biases):
            raise ContractError('immutable native state changed')
        self.validate_continuation(s)

        # Every nested numeric state array is finite; only binding limits allow infinity.
        def finite_tree(value):
            if isinstance(value,np.ndarray) and value.dtype.kind == 'f' and not np.isfinite(value).all():
                raise ContractError('nonfinite nested controller state')
            if isinstance(value,dict):
                for item in value.values(): finite_tree(item)
            elif isinstance(value,(list,tuple)):
                for item in value: finite_tree(item)
        finite_tree(s)
        if s['initialized']:
            for i,mode in enumerate(s['modes']):
                p=s['phi'][i]-s['cycle'][i]*TWO_PI; beta=b.beta[i]
                interval={'LIFT':(0.,beta/3),'TRANSFER':(beta/3,2*beta/3),'LAND':(2*beta/3,beta),'SUPPORT':(beta,TWO_PI),'RELEASE_WAIT':(TWO_PI,TWO_PI)}
                if s['resume_modes'][i] not in ('SUPPORT','RELEASE_WAIT'): raise ContractError('reacquire resume mode')
                check=s['resume_modes'][i] if mode=='REACQUIRE' else mode
                lo,hi=interval[check]
                if p<lo-1e-12 or p>hi+1e-12: raise ContractError('mode/phase/cycle inconsistent')
        encode(s)
        return s

    def validate_continuation(self,s):
        """Semantic schemas for every saved continuation payload; no RNG draw."""
        rng=s['rng_state']
        if (not isinstance(rng,tuple) or len(rng)!=5 or rng[0]!='MT19937'
                or not isinstance(rng[1],np.ndarray) or rng[1].dtype!=np.uint32
                or rng[1].shape!=(624,) or not np.any(rng[1])
                or type(rng[2]) is not int or not 0<=rng[2]<=624
                or type(rng[3]) is not int or rng[3] not in (0,1)
                or type(rng[4]) is not float or not np.isfinite(rng[4])):
            raise ContractError('native RandomState MT19937 schema')
        for key in ('magnitude','release_magnitude'):
            if np.any(s[key]<0) or np.any(s[key]>1.8+1e-12): raise ContractError('magnitude domain')
        for key in ('excursion','total_force','distal_force'):
            if np.any(s[key]<0): raise ContractError('nonnegative trajectory/load domain')
        if np.any(s['distal_force']>s['total_force']): raise ContractError('distal/total load')
        if not s['initialized']:
            zeros=('magnitude','clear_count','load_count','distal_count','wait_count','ap0','lateral0',
                   'release_height','release_magnitude','excursion','landing_xy','transfer_start',
                   'total_force','distal_force','correction')
            if (s['last_tick']!=-1 or s['generation']!=0 or s['last_observation'] is not None
                    or s['diagnostics']!={} or any(np.any(s[k]!=0) for k in zeros)
                    or not np.array_equal(s['theta'],s['phi'])
                    or not np.array_equal(s['cycle'],np.floor(s['phi']/TWO_PI).astype(np.int64))
                    or s['modes']!=['SUPPORT']*6 or s['resume_modes']!=['SUPPORT']*6
                    or not np.all(s['partial']) or not np.array_equal(s['intrinsic_frequency'],np.full(6,12.))
                    or not np.array_equal(s['intrinsic_amplitude'],np.ones(6))
                    or not np.array_equal(s['coupling'],self.binding.coupling)):
                raise ContractError('uninitialized continuation schema')
            return
        if s['last_tick']<1 or not 1<=s['generation']<=s['last_tick'] or s['last_observation'] is None:
            raise ContractError('initialized observation/generation clock')
        obs=observation_from_state(s['last_observation']).validate(self.binding,s['last_tick']-1)
        if obs.tick!=s['last_tick']: raise ContractError('saved observation clock equality')
        expected_adhesion=np.array([m not in ('LIFT','TRANSFER') for m in s['modes']],dtype=bool)
        if not np.array_equal(s['adhesion'],expected_adhesion): raise ContractError('mode/action adhesion')
        total=obs.loads(); distal=np.zeros(6)
        for con in obs.contacts:
            if con.leg>=0 and con.force[0]>0 and con.geom==self.binding.foot_geoms[con.leg,4]:
                distal[con.leg]+=con.force[0]
        if not np.array_equal(total,s['total_force']) or not np.array_equal(distal,s['distal_force']):
            raise ContractError('saved observation/load mismatch')
        if (np.any((s['clear_count']>0)&((total!=0)|(obs.minima[:,:,2].min(axis=1)<=.02)))
                or np.any((s['load_count']>0)&(total<=0)) or np.any((s['distal_count']>0)&(distal<=0))):
            raise ContractError('saved dwell/load mismatch')
        for i,mode in enumerate(s['modes']):
            origin=s['cycle'][i]*TWO_PI; beta=self.binding.beta[i]
            if mode=='TRANSFER' and not origin+beta/3-1e-12<=s['transfer_start'][i]<=s['phi'][i]+1e-12:
                raise ContractError('transfer trajectory origin')
            if s['wait_count'][i]>0 and mode not in ('LIFT','LAND','RELEASE_WAIT','REACQUIRE'):
                raise ContractError('wait/mode mismatch')
        frequency=s['intrinsic_frequency']; amplitude=s['intrinsic_amplitude']
        if (not np.all(frequency==frequency[0]) or not 12.*SILENCE/.6<frequency[0]<=8.+1e-12
                or not np.all(amplitude[:3]==amplitude[0]) or not np.all(amplitude[3:]==amplitude[3])
                or np.any(amplitude<.2-1e-12) or np.any(amplitude>1.8+1e-12)
                or abs(amplitude[0]+amplitude[3]-2.)>1e-12
                or not np.allclose(s['coupling'],self.binding.coupling*(frequency[0]/12.),rtol=0,atol=1e-14)):
            raise ContractError('native drive/configuration domain')
        d=s['diagnostics']
        keys={'legs','lag','phase_increment','admitted','capture_point','release_veto','positive_nonfoot',
              'body_velocity','body_omega','minimum_heights','actuator_force','forcecap_observed'}
        if not isinstance(d,dict) or set(d)!=keys: raise ContractError('diagnostic schema')
        for key,shape in (('lag',(6,)),('phase_increment',(6,)),('capture_point',(2,)),
                          ('body_velocity',(3,)),('body_omega',(3,)),('minimum_heights',(6,5)),('actuator_force',(48,))):
            array(d[key],shape,'diagnostic '+key)
        if (not np.array_equal(d['lag'],s['theta']-s['phi']) or np.any(d['phase_increment']<0)
                or not np.array_equal(d['minimum_heights'],obs.minima[:,:,2])
                or not np.array_equal(d['actuator_force'],obs.actuator_force)):
            raise ContractError('diagnostic continuation mismatch')
        if (type(d['release_veto']) is not bool or type(d['positive_nonfoot']) is not bool
                or not isinstance(d['admitted'],list) or any(type(i) is not int or not 0<=i<6 for i in d['admitted'])
                or len(set(d['admitted']))!=len(d['admitted'])
                or any(s['modes'][i]!='LIFT' for i in d['admitted'])
                or not isinstance(d['forcecap_observed'],np.ndarray) or d['forcecap_observed'].dtype!=np.bool_
                or not np.array_equal(d['forcecap_observed'],np.abs(obs.actuator_force[:42])>=65.)):
            raise ContractError('diagnostic flags/admission')
        legkeys={'A','b','z','residual','measured_active_task_velocity','requested_increment','limited_increment',
                 'before_ball','after_ball','correction','range_flags','native_increment'}
        if not isinstance(d['legs'],list) or len(d['legs'])!=6: raise ContractError('diagnostic legs')
        for i,leg in enumerate(d['legs']):
            if not isinstance(leg,dict) or set(leg)!=legkeys: raise ContractError('diagnostic leg schema')
            A=leg['A']
            if not isinstance(A,np.ndarray) or A.ndim!=2 or A.shape[1]!=7 or A.shape[0]>3*512+7:
                raise ContractError('diagnostic row capacity')
            array(A,A.shape,'diagnostic A')
            for key in ('b','residual','measured_active_task_velocity'): array(leg[key],(len(A),),key)
            for key in ('z','requested_increment','limited_increment','before_ball','after_ball','correction','native_increment'):
                array(leg[key],(7,),key)
            if (not isinstance(leg['range_flags'],np.ndarray) or leg['range_flags'].dtype!=np.bool_
                    or leg['range_flags'].shape!=(7,) or not np.array_equal(leg['correction'],s['correction'][i])):
                raise ContractError('diagnostic projection schema')

    def checkpoint(self):
        return {'version':STATE_VERSION,'binding':self.binding.token(),'state':encode(deepcopy(self.state))}

    def restored_state(self,checkpoint):
        if not isinstance(checkpoint,dict) or set(checkpoint)!={'version','binding','state'} or checkpoint['version']!=STATE_VERSION or checkpoint['binding']!=self.binding.token():
            raise ContractError('checkpoint binding/schema')
        try:
            shadow=decode(deepcopy(checkpoint['state'])); self.validate_state(shadow)
        except (TypeError,KeyError,ValueError,OverflowError) as exc:
            raise ContractError('invalid controller checkpoint: '+str(exc)) from exc
        return shadow

    def restore(self,checkpoint):
        staged=self.restored_state(checkpoint)
        self.state=staged
        self._revision+=1  # also invalidates same-state and ABA outstanding proposals

    def checkpoint_json(self):
        return json.dumps(self.checkpoint(),sort_keys=True,separators=(',',':'),allow_nan=False)
