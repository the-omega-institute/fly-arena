"""Detached native primitives; never imported/called by source fixtures."""
from types import SimpleNamespace
import numpy as np
from .schema import TOL,DT,CONTACT,unpack

def prepare(model,data,q,v):
    import mujoco as mj
    data.qpos[:]=q;data.qvel[:]=v
    mj.mj_kinematics(model,data);mj.mj_comPos(model,data);mj.mj_fwdVelocity(model,data)
def point_jac(model,data,point,body):
    import mujoco as mj
    J=np.zeros((3,model.nv));mj.mj_jac(model,data,J,None,np.asarray(point),int(body));return J

def point_velocity(model,data,point,body):
    import mujoco as mj
    value=np.zeros(6);mj.mj_objectVelocity(model,data,mj.mjtObj.mjOBJ_BODY,int(body),value,0)
    return value[3:]+np.cross(value[:3],point-data.xipos[int(body)])

class Geometry:
    def __init__(self,model,binding,thorax,bodies):
        self.model=model;self.binding=binding;self.thorax=int(thorax);self.bodies=tuple(int(x) for x in bodies)
        self.vertices={}
        for g in binding.foot_geoms.flat:
            mesh=int(model.geom_dataid[g]);start=int(model.mesh_vertadr[mesh]);count=int(model.mesh_vertnum[mesh])
            self.vertices[int(g)]=np.asarray(model.mesh_vert[start:start+count],dtype=np.float64).copy()
    def endpoint(self,data,*,jacobians=False):
        import mujoco as mj
        b=self.binding;model=self.model
        minima=np.empty((6,5,3));ids=np.empty((6,5),dtype=np.int64);distal=np.empty((6,3));J=np.zeros((6,5,3,b.nv));dJ=np.zeros((6,3,b.nv));max_error=0.
        for leg in range(6):
            for j,g in enumerate(b.foot_geoms[leg]):
                verts=self.vertices[int(g)];R=data.geom_xmat[g].reshape(3,3);p=data.geom_xpos[g]
                world=verts@R.T+p;index=int(np.argmin(world[:,2]));point=world[index]
                # Independent indexed dot-product reduction; ties use vertex order.
                z=verts[:,0]*R[2,0]+verts[:,1]*R[2,1]+verts[:,2]*R[2,2]+p[2]
                other=int(np.argmin(z));independent=p+R@verts[other]
                if other!=index and abs(z[other]-world[index,2])>TOL:raise ValueError('independent minimum identity')
                max_error=max(max_error,float(np.max(np.abs(independent-point))))
                minima[leg,j]=point;ids[leg,j]=index
                if jacobians:J[leg,j]=point_jac(model,data,point,model.geom_bodyid[g])
                if j==4:
                    distal[leg]=world.mean(axis=0)
                    check=p+R@verts.mean(axis=0);max_error=max(max_error,float(np.max(np.abs(check-distal[leg]))))
                    if jacobians:dJ[leg]=point_jac(model,data,distal[leg],model.geom_bodyid[g])
        if max_error>TOL:raise ValueError('independent endpoint geometry disagreement')
        R=data.xmat[self.thorax].reshape(3,3).copy();position=data.xpos[self.thorax].copy()
        result=SimpleNamespace(minima=minima,minimum_vertices=ids,minimum_jacobians=J,distal=distal,distal_jacobians=dJ,thorax_pos=position,thorax_rotation=R,
           height=minima[:,:,2].min(axis=1),ap=(distal-position)@R[:,0],geometry_error=max_error)
        if jacobians:
            tJ=np.zeros((3,b.nv));rJ=np.zeros((3,b.nv));mj.mj_jacBody(model,data,tJ,rJ,self.thorax)
            result.thorax_velocity=tJ@data.qvel;result.thorax_omega=rJ@data.qvel
            masses=np.asarray(model.body_mass[list(self.bodies)],dtype=np.float64);weights=masses/masses.sum();Jcom=np.zeros((3,b.nv))
            result.com=np.sum(weights[:,None]*data.xipos[list(self.bodies)],axis=0)
            for body,w in zip(self.bodies,weights):
                jac=np.zeros((3,b.nv));mj.mj_jacBodyCom(model,data,jac,None,body);Jcom+=w*jac
            result.com_velocity=Jcom@data.qvel;result.gravity=float(np.linalg.norm(model.opt.gravity))
        return result
    def interval_metrics(self,prior,rows,qvel):
        normal=np.zeros(6);weighted=np.zeros(6);peak=np.zeros(6);error=0.
        for raw in rows:
            row=unpack(CONTACT,raw);leg=int(row['leg'][0]);geom=int(row['geom'][0]);ground=int(row['ground'][0]);point=row['point'];frame=row['frame'].reshape(3,3)
            if ground!=self.binding.ground_geom or geom not in self.binding.fly_geoms:raise ValueError('owned contact map')
            footbody=int(self.model.geom_bodyid[geom]);groundbody=int(self.model.geom_bodyid[ground])
            velocity=point_velocity(self.model,prior,point,footbody)-point_velocity(self.model,prior,point,groundbody)
            independent=(point_jac(self.model,prior,point,footbody)-point_jac(self.model,prior,point,groundbody))@qvel
            error=max(error,float(np.max(np.abs(velocity-independent))))
            if error>TOL:raise ValueError('independent point velocity mismatch')
            if leg<0:continue
            if geom not in self.binding.foot_geoms[leg]:raise ValueError('contact leg map')
            n=frame[0];speed=float(np.linalg.norm(velocity-n*np.dot(n,velocity)));fn=float(row['force'][0]);peak[leg]=max(peak[leg],speed)
            if fn>0:normal[leg]+=fn;weighted[leg]+=fn*speed
        return normal,weighted,peak,error
    def observation(self,current,prior,endpoint,rows,tick,force):
        b=self.binding;contacts=[]
        for raw in rows:
            r=unpack(CONTACT,raw);geom=int(r['geom'][0]);body=int(self.model.geom_bodyid[geom]);p=r['point'];local=prior.xmat[body].reshape(3,3).T@(p-prior.xpos[body]);now=current.xpos[body]+current.xmat[body].reshape(3,3)@local
            J=point_jac(self.model,current,now,body);Jold=point_jac(self.model,prior,p,body)
            contacts.append(SimpleNamespace(index=int(r['index'][0]),geom=geom,ground=int(r['ground'][0]),leg=int(r['leg'][0]),interval_tick=tick-1,force=r['force'],frame=r['frame'].reshape(3,3),distance=float(r['distance'][0]),point_prior=p,point_local=local,point=now,jacobian=J,velocity=J@current.qvel,passive_velocity=J[:,b.passive_dofs]@current.qvel[b.passive_dofs],prior_velocity=Jold@prior.qvel))
        return SimpleNamespace(**endpoint.__dict__,tick=tick,qpos=current.qpos.copy(),qvel=current.qvel.copy(),prior_qpos=prior.qpos.copy(),prior_qvel=prior.qvel.copy(),contacts=tuple(contacts),actuator_force=force)
    def excursion(self,steps,leg,obs,magnitude):
        import mujoco as mj
        b=self.binding;g=int(b.foot_geoms[leg,4]);data=mj.MjData(self.model);values=[]
        for phase in (0.,float(steps.swing_period[steps.legs[leg]][1])):
            data.qpos[:]=obs.qpos;angles=steps.get_joint_angles(steps.legs[leg],phase,1.);data.qpos[b.qadr[leg]]=np.clip(angles,b.lower[leg],b.upper[leg])
            mj.mj_kinematics(self.model,data);mj.mj_comPos(self.model,data)
            point=data.geom_xpos[g]+data.geom_xmat[g].reshape(3,3)@self.vertices[g].mean(axis=0)
            values.append(float(obs.thorax_rotation[:,0]@(point-obs.thorax_pos)))
        return magnitude*abs(values[1]-values[0])

def static_preflight(body,adapter,budget):
    """Actual reset primitives, no Observation packet or controller action exists."""
    import mujoco as mj
    geom=Geometry(body.model,adapter.binding,adapter.thorax,adapter.bodies)
    a=mj.MjData(body.model);b=mj.MjData(body.model)
    for data in (a,b):budget.call('static_prepare',prepare,body.model,data,body.data.qpos,body.data.qvel)
    endpoint=geom.endpoint(a,jacobians=True);other=geom.endpoint(b,jacobians=False)
    if not np.allclose(endpoint.minima,other.minima,rtol=0,atol=TOL):raise ValueError('static geometry mismatch')
    error=0.
    for i in range(6):
        for j,g in enumerate(adapter.binding.foot_geoms[i]):
            p=endpoint.minima[i,j];v=point_velocity(body.model,a,p,body.model.geom_bodyid[g]);error=max(error,float(np.max(np.abs(v-endpoint.minimum_jacobians[i,j]@a.qvel))))
        g=adapter.binding.foot_geoms[i,4];v=point_velocity(body.model,a,endpoint.distal[i],body.model.geom_bodyid[g]);error=max(error,float(np.max(np.abs(v-endpoint.distal_jacobians[i]@a.qvel))))
    thorax_speed=np.zeros(6);mj.mj_objectVelocity(body.model,a,mj.mjtObj.mjOBJ_BODY,adapter.thorax,thorax_speed,0)
    thorax_linear=thorax_speed[3:]+np.cross(thorax_speed[:3],endpoint.thorax_pos-a.xipos[adapter.thorax])
    error=max(error,float(np.max(np.abs(thorax_linear-endpoint.thorax_velocity))),float(np.max(np.abs(thorax_speed[:3]-endpoint.thorax_omega))))
    masses=body.model.body_mass[list(adapter.bodies)];weighted=np.zeros(3)
    for body_id,mass in zip(adapter.bodies,masses):
        value=np.zeros(6);mj.mj_objectVelocity(body.model,a,mj.mjtObj.mjOBJ_BODY,body_id,value,0);weighted+=mass*value[3:]
    error=max(error,float(np.max(np.abs(weighted/masses.sum()-endpoint.com_velocity))))
    if error>TOL:raise ValueError('static velocity mismatch')
    endpoint.qpos=body.data.qpos.copy()
    excursions=[budget.call('static_excursion',adapter.excursion,i,endpoint,1.) for i in range(6)]
    return {'geometry_error':endpoint.geometry_error,'velocity_error':error,'unit_excursions':excursions,'synthetic_interval_created':False,'physics_steps':0,'intent_calls':0}
