"""Independent arithmetic of the selected law. Never calls production law helpers."""
from copy import deepcopy
import numpy as np
from .schema import DT,TOL
C=np.array([.06,np.sqrt(.001651),.03]*2)
TWOPI=2*np.pi

def agree(actual,want,name,*,exact=False):
    a=np.asarray(actual);b=np.asarray(want)
    if a.shape!=b.shape or (not np.array_equal(a,b) if exact else not np.allclose(a,b,rtol=0,atol=TOL)):
        delta=float(np.max(np.abs(a.astype(float)-b.astype(float)),initial=0)) if a.shape==b.shape and a.dtype.kind in 'fiub' and b.dtype.kind in 'fiub' else None
        raise ValueError('independent mismatch '+name+' max_error='+str(delta))

def intent(theta,r,c,a,coupling,bias):
    frequency=np.repeat(12*c/.6,6)
    differences=np.subtract.outer(theta,theta).T
    increment=DT*(2*np.pi*frequency+np.sum(r[None,:]*(coupling*c/.6)*np.sin(differences-bias),axis=1))
    return theta+increment,r+DT*20*(np.repeat([1-a,1+a],3)-r)

def supported(points,xi):
    points=sorted(set(tuple(p) for p in points))
    if len(points)<3:return False
    def det(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    chains=[]
    for order in (points,points[::-1]):
        chain=[]
        for p in order:
            while len(chain)>1 and det(chain[-2],chain[-1],p)<=0:chain.pop()
            chain.append(p)
        chains.extend(chain[:-1])
    if len(chains)<3:return False
    return all(det(a,b,xi)>.02*np.linalg.norm(np.subtract(b,a)) for a,b in zip(chains,chains[1:]+chains[:1]))

def twist(b,obs,s,z):
    contacts=[x for x in obs.contacts if x.leg>=0 and x.force[0]>0 and s['modes'][x.leg]=='SUPPORT']
    length=max(.05,float(np.sqrt(np.mean([sum((x.point[:2]-obs.thorax_pos[:2])**2) for x in contacts])))) if contacts else .05
    matrices=[];rhs=[]
    for i in range(6):
        group=[x for x in contacts if x.leg==i]
        for x in group:
            p=x.point-obs.thorax_pos;weight=np.sqrt(len(group));matrices.append(np.array([[1,0,-p[1]/length],[0,1,p[0]/length]])/weight)
            rhs.append(-(x.jacobian[:,b.vadr[i]]@z[i]+x.passive_velocity)[:2]/weight)
    fit=np.zeros(3)
    if matrices:
        A=np.vstack(matrices);y=np.concatenate(rhs);u,sigma,v=np.linalg.svd(A,full_matrices=False);keep=sigma>64*np.finfo(float).eps*max(1,float(sigma.max()));inv=np.zeros_like(sigma);inv[keep]=1/sigma[keep];fit=v.T@(inv*(u.T@y))
    velocity=np.r_[fit[:2],np.clip((s['z0']-obs.thorax_pos[2])/.05,-1,1)]
    angular=np.cross(obs.thorax_rotation[:,2],[0.,0.,1.])/.05;angular[2]=fit[2]/length
    return velocity,angular

def tasks(b,obs,s,i,delta,velocity,omega):
    dofs=b.vadr[i];rows=[];rhs=[];mode=s['modes'][i];p=obs.distal[i];J=obs.distal_jacobians[i];vp=J@obs.qvel
    contacts=[x for x in obs.contacts if x.leg==i and x.force[0]>0]
    def add(j,measured,wanted,weight=1.):
        active=j[dofs];rows.append(active/weight);rhs.append((wanted-measured+active@obs.qvel[dofs])/weight)
    if mode in ('LIFT','TRANSFER'):
        for foot in range(5):
            j=obs.minimum_jacobians[i,foot,2];desired=np.clip((.05-obs.minima[i,foot,2])/.003,-.05/.003,.05/.003);add(j,j@obs.qvel,desired,np.sqrt(5))
        target=s['ap0'][i];rate=0.
        if mode=='TRANSFER':
            duration=s['cycle'][i]*TWOPI+2*b.beta[i]/3-s['transfer_start'][i]
            progress=np.clip((s['phi'][i]-s['transfer_start'][i])/duration,0,1) if duration>0 else 1.
            if duration>0:rate=s['excursion'][i]*6*progress*(1-progress)*delta[i]/(DT*duration)
            target+=s['excursion'][i]*(3*progress**2-2*progress**3)
        relative=p-obs.thorax_pos;relative_velocity=vp-obs.thorax_velocity-np.cross(obs.thorax_omega,relative)
        for axis,value,speed in ((0,target,rate),(1,s['lateral0'][i],0.)):
            direction=obs.thorax_rotation[:,axis];add(direction@J,direction@relative_velocity,speed+(value-direction@relative)/.003)
    elif mode in ('LAND','REACQUIRE'):
        desired=np.clip((s['landing_xy'][i]-p[:2])/.003,-.05/.003,.05/.003)
        for axis in range(2):add(J[axis],vp[axis],desired[axis])
        j=obs.minimum_jacobians[i,4,2];target=0. if s['distal_force'][i]>0 else -min(.05/.003,max(obs.minima[i,4,2],0)/.003);add(j,j@obs.qvel,target)
        for contact in contacts:
            for tangent in contact.frame[1:]:add(tangent@contact.jacobian,tangent@contact.velocity,0.,np.sqrt(max(1,len(contacts))))
    else:
        for contact in contacts:
            n=contact.frame[0];rhs.extend((-velocity-np.cross(omega,contact.point-obs.thorax_pos)-contact.passive_velocity-(np.eye(3)-np.outer(n,n))@contact.velocity)/np.sqrt(len(contacts)))
            rows.extend(contact.jacobian[:,dofs]/np.sqrt(len(contacts)))
    return np.asarray(rows,dtype=float).reshape(-1,7),np.asarray(rhs,dtype=float)

def candidate_transition(pre,obs,u,b,reference):
    """One independent state/action prediction from compact prestate and real observation."""
    s=deepcopy(pre);common=float(np.mean(u));asym=float((u[1]-u[0])/(2*common));total=np.zeros(6);distal=np.zeros(6);nonfoot=False
    for x in obs.contacts:
        if x.force[0]>0:
            if x.leg<0:nonfoot=True
            else:
                total[x.leg]+=x.force[0]
                if x.geom==b.foot_geoms[x.leg,4]:distal[x.leg]+=x.force[0]
    if obs.tick!=pre['last_tick']+1:
        for k in ('clear_count','load_count','distal_count'):s[k]=np.zeros(6,dtype=np.int64)
    predicates=((total==0)&(obs.minima[:,:,2].min(axis=1)>.02),total>0,distal>0)
    for k,p in zip(('clear_count','load_count','distal_count'),predicates):s[k]=np.where(p,np.minimum(s[k]+1,30),0)
    s['total_force']=total;s['distal_force']=distal
    def latch(i,partial):
        rel=obs.distal[i]-obs.thorax_pos;s['ap0'][i]=obs.thorax_rotation[:,0]@rel;s['lateral0'][i]=obs.thorax_rotation[:,1]@rel;s['release_height'][i]=obs.distal[i,2];s['release_magnitude'][i]=s['magnitude'][i];s['landing_xy'][i]=obs.distal[i,:2]
        s['transfer_start'][i]=s['phi'][i] if partial and s['modes'][i]=='TRANSFER' else s['cycle'][i]*TWOPI+b.beta[i]/3
        s['excursion'][i]=reference.excursion(i,obs,s['release_magnitude'][i]);s['partial'][i]=partial
    if not s['initialized']:
        s['initialized']=True;s['z0']=float(obs.thorax_pos[2])
        for i in range(6):
            p=s['phi'][i]-s['cycle'][i]*TWOPI;beta=b.beta[i]
            s['modes'][i]='LIFT' if p<beta/3 else 'TRANSFER' if p<2*beta/3 else 'LAND' if p<beta else 'SUPPORT'
            if s['modes'][i] in ('LIFT','TRANSFER','LAND'):latch(i,True)
            else:s['landing_xy'][i]=obs.distal[i,:2];s['transfer_start'][i]=s['cycle'][i]*TWOPI+beta/3
    theta,r=intent(s['theta'],s['magnitude'],common,asym,b.coupling,b.biases);dt=theta-s['theta'];s['magnitude']=r;delta=np.zeros(6);blocked=np.zeros(6,dtype=bool)
    for i in range(6):
        mode=s['modes'][i];beta=b.beta[i];origin=s['cycle'][i]*TWOPI
        if mode in ('SUPPORT','RELEASE_WAIT') and total[i]==0:
            s['resume_modes'][i]=mode;s['modes'][i]=mode='REACQUIRE';s['landing_xy'][i]=obs.distal[i,:2]
        if mode=='REACQUIRE':
            if s['distal_count'][i]>=30:s['modes'][i]=s['resume_modes'][i]
            else:blocked[i]=True
            continue
        if mode=='RELEASE_WAIT':blocked[i]=True;continue
        edge=origin+{'LIFT':beta/3,'TRANSFER':2*beta/3,'LAND':beta,'SUPPORT':TWOPI}[mode]
        if s['phi'][i]>=edge:
            if mode=='LIFT':
                if s['clear_count'][i]>=30:s['modes'][i]='TRANSFER';s['transfer_start'][i]=edge
                else:blocked[i]=True
            elif mode=='TRANSFER':s['modes'][i]='LAND';s['landing_xy'][i]=obs.distal[i,:2]
            elif mode=='LAND':
                if s['distal_count'][i]>=30:s['modes'][i]='SUPPORT'
                else:blocked[i]=True
            else:s['modes'][i]='RELEASE_WAIT';blocked[i]=True
        else:delta[i]=min(2*dt[i],theta[i]-s['phi'][i],edge-s['phi'][i]);s['phi'][i]+=delta[i]
    supports={i for i in range(6) if s['modes'][i] in ('SUPPORT','RELEASE_WAIT') and s['load_count'][i]>=30 and pre['adhesion'][i]}
    xi=obs.com[:2]+obs.com_velocity[:2]*np.sqrt(max(obs.com[2],0)/obs.gravity)
    veto=nonfoot or obs.thorax_rotation[2,2]<=.8 or any(m in ('LAND','REACQUIRE') for m in s['modes']);admitted=np.zeros(6)
    pending=sorted([i for i in range(6) if s['modes'][i]=='RELEASE_WAIT'],key=lambda i:(-(theta[i]-s['phi'][i]),i))
    for i in pending:
        if not veto and supported([x.point[:2] for x in obs.contacts if x.leg in supports-{i} and x.force[0]>0],xi):
            supports.discard(i);admitted[i]=1.;blocked[i]=False;s['cycle'][i]+=1;s['modes'][i]='LIFT';latch(i,False);s['clear_count'][i]=0;s['distal_count'][i]=0
    s['wait_count']=np.where(blocked,s['wait_count']+1,0);s['theta']=theta;s['lag']=theta-s['phi'];s['phase_increment']=s['phi']-pre['phi']
    if np.any(dt<=0) or np.any(s['lag']>np.pi/2) or np.any(s['wait_count']>500):raise ValueError('retained successful action violates finite phase domain')
    native=reference.angles(s['phi'],r);zN=(native-pre['native_reference'])/DT;v,w=twist(b,obs,s,zN)
    s.update(body_velocity=v,body_omega=w,capture_point=xi,admitted=admitted,release_veto=np.array([veto]),positive_nonfoot=np.array([nonfoot]))
    outputs={k:[] for k in ('z','residual_norm','residual_max','requested_increment','limited_increment','before_ball','after_ball','range_flags','correction','angles')}
    task_payload=[]
    for i in range(6):
        A,y=tasks(b,obs,s,i,delta,v,w);H=A.T@A+.02**2*np.eye(7);rhs=A.T@y+.02**2*zN[i];chol=np.linalg.cholesky(H);z=np.linalg.solve(chol.T,np.linalg.solve(chol,rhs)) if len(A) else zN[i].copy()
        e=DT*(z-zN[i]);en=np.linalg.norm(e);limited=e*min(1.,800*DT*C[i]/en) if en else e.copy();before=pre['angles'][i]-pre['native_reference'][i]+limited;bn=np.linalg.norm(before);after=before*min(1.,80*C[i]/bn) if bn else before.copy();raw=native[i]+after;angles=np.clip(raw,b.lower[i],b.upper[i]);res=A@z-y
        task_payload.append({'A':A,'b':y,'z_native':zN[i],'z':z,'residual':res})
        values=(z,np.linalg.norm(res),np.max(np.abs(res),initial=0),e,limited,before,after,angles!=raw,angles-native[i],angles)
        for key,value in zip(outputs,values):outputs[key].append(value)
    s.update({k:np.array(v) for k,v in outputs.items()});s['native_reference']=native;s['adhesion']=np.array([m not in ('LIFT','TRANSFER') for m in s['modes']]);s['last_tick']=obs.tick;s['generation']+=1
    s['_tasks']=task_payload
    return s

def verify_candidate(pre,post,obs,u,b,reference):
    predicted=candidate_transition(pre,obs,u,b,reference)
    try:
        for key in ('theta','magnitude','phi','cycle','partial','clear_count','load_count','distal_count','wait_count','ap0','lateral0','release_height','release_magnitude','excursion','transfer_start','total_force','distal_force','landing_xy','native_reference','correction','z0','initialized','last_tick','generation','body_velocity','body_omega','capture_point','admitted','release_veto','positive_nonfoot','phase_increment','lag','z','residual_norm','residual_max','requested_increment','limited_increment','before_ball','after_ball','range_flags','angles','adhesion'):
            agree(post[key],predicted[key],key)
        for key in ('modes','resume_modes'):
            if post[key]!=predicted[key]:raise ValueError('independent mode '+key)
        return predicted
    except BaseException as error:
        error.independent_prediction=predicted
        error.independent_observation=obs
        raise
