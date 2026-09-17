"""One attempt, charged calls, conservative allocation checks and prefix forecasts."""
import contextlib,functools,json,os,pathlib,resource,shutil,time
import numpy as np
from .io import write
from .schema import DT
class ResourceStop(RuntimeError):pass
AC=638100;AV=308000;N=1960100;R=1960149;L=6*AC+6;B=68;E=512*N;CONTROL_ENDPOINTS=16*40001;CONTROL_OBSERVATIONS=CONTROL_ENDPOINTS+AV
# Runtime and verifier share this one accounting budget. Leaves include both.
LEAF_CAPS={
 'mj_step':N,'mj_forward':53,'mj_resetDataKeyframe':53,'mj_saveModel':1,
 'mj_kinematics':4*AC+4*L+R+AV+16,'mj_comPos':4*AC+4*L+R+AV+16,
 'mj_fwdVelocity':R+4,'mj_jac':2*(36+1024)*AC+12*AV+2*E+72,
 'mj_jacBody':2*AC+1,'mj_jacBodyCom':2*B*AC+B,
 'mj_objectVelocity':2*E+36+B+1,'mj_contactForce':E+512*CONTROL_OBSERVATIONS,'control_observation':CONTROL_OBSERVATIONS,
 'mj_copyData':32,'mj_getState':512,'mj_stateSize':512,
 'mj_name2id':250000,'mj_id2name':250000,
 'MjData':4*AC+4*L+512,'model_build':53,'model_load':1,'bind_native':37,
 'checkpoint':2,'restore':2,'native_cache_manifest':512,'candidate_active':AC,
 'control_active':AV,'candidate_propose':AC,'independent_candidate':AC,
 'cpg_init_reset':424,'get_joint_angles':24*AC+4*L+24*AV+53*48+24,
 'MjSpec.compile':212,'MjSpec.copy':212,'MjSpec.construct':106,'cpg_step':AV,'reference_construct':123,'candidate_solve':6*AC,'candidate_shared_fit':AC,'static_prepare':2,'static_excursion':6,'static_neutral':4,
}
# Maximum source-proven composition counts for one fly/one ground scene.
# 69 mesh segments (original compact model manifest), 66 hinges + one free root.
SPEC_PER_BUILD={'MjSpec.add_mesh':69,'MjSpec.add_key':2,'MjSpec.add_texture':2,
 'MjSpec.add_material':1,'MjSpec.add_actuator':48,'MjSpec.add_pair':69,
 'MjSpec.add_sensor':6,'MjSpec.attach':1,'MjSpec.delete':1,
 'MjsBody.add_body':69,'MjsBody.add_geom':70,'MjsBody.add_joint':66,
 'MjsBody.add_freejoint':1,'MjsBody.add_site':2}
LEAF_CAPS.update({name:53*count for name,count in SPEC_PER_BUILD.items()})
# MuJoCo 3.9 MJDATA_POINTERS: all92 arrays, 8 bytes per element (including int/bool),
# 64 bytes alignment per array, 1MiB struct/wrapper reserve, plus the full arena.
# Fixed fly has no plugins; their arbitrary allocations are not admitted.
DATA_ELEMENT_MULTIPLIERS={'nq': 1, 'nv': 30, 'na': 2, 'nhistory': 1, 'npluginstate': 1, 'nu': 6, 'nbody': 90, 'neq': 1, 'nmocap': 7, 'nuserdata': 1, 'nsensordata': 1, 'ntree': 2, 'nplugin': 2, 'njnt': 6, 'ngeom': 12, 'nsite': 12, 'ncam': 12, 'nlight': 6, 'nflexvert': 5, 'nflexelem': 6, 'nJfe': 1, 'nflexedge': 2, 'nJfv': 2, 'nbvhdynamic': 6, 'ntendon': 4, 'nJten': 1, 'nwrap': 8, 'nJmom': 2, 'nM': 1, 'nC': 3, 'nbvh': 1, 'nD': 2}
def data_allocation_bytes(model):
    if int(model.nplugin)!=0:raise ResourceStop('unregistered native plugin allocation')
    sizes={name:int(getattr(model,name)) for name in DATA_ELEMENT_MULTIPLIERS}
    if any(n<0 for n in sizes.values()) or int(model.narena)<0:raise ValueError('negative native allocation dimensions')
    return 2*(8*sum(sizes[name]*n for name,n in DATA_ELEMENT_MULTIPLIERS.items())+92*64+1024**2+int(model.narena))

class Budget:
    def __init__(self,root,*,start=None,caps=None):
        self.root=pathlib.Path(root);self.start=time.time() if start is None else start;self.caps=dict(LEAF_CAPS if caps is None else caps)
        self.attempted={};self.completed={};self.stage='preflight';self.current='';self.steps=0;self.timings={};self.reserved=128*1024**2;self.known_bytes=0;self.last_inventory=0.;self.pending_buffers=0;self.source_bytes=0;self.remaining_steps=N;self.future_runtime=0;self.future_reconstruction=0;self.future_trials=0;self.max_byte_rate=0.;self.byte_mark=0;self.stream_bytes=0;self.finalizing=False;self.remaining={};self.rates={};self.finalization_max_seconds=0.
    def check(self,pending=0,*,pending_memory=0,pending_disk=0):
        # Legacy pending means a new memory allocation, never current resident buffers.
        pending_memory+=pending
        if pending_memory<0 or pending_disk<0:raise ValueError('negative pending allocation')
        wall=time.time()-self.start;usage=resource.getrusage(resource.RUSAGE_SELF)
        rss=usage.ru_maxrss if os.uname().sysname=='Darwin' else usage.ru_maxrss*1024
        if time.monotonic()-self.last_inventory>=30:
            self.known_bytes=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()) if self.root.exists() else 0;self.last_inventory=time.monotonic()
        size=self.known_bytes+self.source_bytes;disk_reserve=self.pending_buffers+pending_disk
        free=shutil.disk_usage(self.root if self.root.exists() else self.root.parent).free
        limit=(600 if self.finalizing else 540) if self.stage=='preflight' else (14400 if self.finalizing else 14400-self.finalization_reserve())
        if ((self.stage=='preflight' and self.known_bytes+disk_reserve>128*1024**2) or wall>limit
            or rss+pending_memory>2*1024**3 or size+disk_reserve+(0 if self.finalizing else self.reserved)>8*1024**3
            or free-disk_reserve<20*1024**3):raise ResourceStop('wall/RSS/preallocation/evidence/free-floor reserve')
        return {'wall_seconds':wall,'peak_rss_bytes':rss,'pending_memory_bytes':pending_memory,'pending_disk_bytes':disk_reserve,
          'evidence_bytes':size,'free_bytes':free,'mechanical_seconds':self.attempted.get('mj_step',0)*DT,
          'attempted':self.attempted.copy(),'completed':self.completed.copy(),'timings':self.timings.copy(),'projection':self.projection()}
    def finalization_reserve(self):return max(60.,2*self.finalization_max_seconds)
    def note_finalization(self,seconds):self.finalization_max_seconds=max(self.finalization_max_seconds,float(seconds))
    def set_remaining(self,workloads):
        if any(type(n) is not int or n<0 for n in workloads.values()):raise ValueError('remaining workload domain')
        self.remaining=dict(workloads);self.check_projection()
    def projection(self):
        costs={name:2*self.rates[name]*count for name,count in self.remaining.items() if name in self.rates}
        return {'remaining':self.remaining.copy(),'maximum_measured_seconds_per_item':self.rates.copy(),'known_costs_seconds':costs,
          'known_total_seconds':sum(costs.values()),'unknown_categories':[k for k,n in self.remaining.items() if n and k not in self.rates],
          'finalization_reserve_seconds':self.finalization_reserve()}
    def check_projection(self):
        if time.time()-self.start+self.projection()['known_total_seconds']+self.finalization_reserve()>14400:raise ResourceStop('combined known remaining work cannot fit single deadline')
    def charge(self,name):
        if name not in self.caps:raise ResourceStop('unregistered native call: '+name)
        value=self.attempted.get(name,0)+1
        if value>self.caps[name]:raise ResourceStop('call capacity: '+name)
        if self.stage=='preflight' and name in ('mj_step','candidate_active','candidate_propose','control_active','independent_candidate','cpg_step','candidate_solve','candidate_shared_fit'):raise ResourceStop('forbidden preflight dynamics/intent')
        self.attempted[name]=value
    def complete(self,name):
        if self.completed.get(name,0)>=self.attempted.get(name,0):raise ValueError('completion without charged attempt: '+name)
        self.completed[name]=self.completed.get(name,0)+1
    def call(self,name,fn,/,*args,**kwargs):
        if name=='MjData':self.check(pending_memory=data_allocation_bytes(args[0] if args else kwargs['model']))
        if name in ('model_build','model_load','checkpoint','restore','mj_copyData','MjData','MjSpec.compile'):self.check()
        self.charge(name);started=time.monotonic()
        try:result=fn(*args,**kwargs)
        except BaseException:raise
        else:self.complete(name);return result
        finally:
            elapsed=time.monotonic()-started;rec=self.timings.setdefault(name,{'calls':0,'seconds':0.,'max_seconds':0.})
            rec['calls']+=1;rec['seconds']+=elapsed;rec['max_seconds']=max(rec['max_seconds'],elapsed)
    def forecast(self,category,elapsed,count,remaining):
        if count<=0:return
        if elapsed<0 or remaining<0:raise ValueError('forecast domain')
        self.rates[category]=max(self.rates.get(category,0.),elapsed/count);self.remaining[category]=remaining
        self.check_projection()
    def forecast_bytes(self,count,remaining):
        if count<=0:return
        produced=max(0,self.stream_bytes-self.byte_mark);self.byte_mark=self.stream_bytes
        self.max_byte_rate=max(self.max_byte_rate,produced/count)
        if self.known_bytes+self.source_bytes+2*self.max_byte_rate*remaining+self.reserved>8*1024**3:raise ResourceStop('known remaining byte forecast cannot fit reserve')
    @contextlib.contextmanager
    def native_guard(self):
        import mujoco as mj
        from . import io
        previous_budget=io._ACTIVE_BUDGET;io._ACTIVE_BUDGET=self
        original={}
        for name in dir(mj):
            if name.startswith(('mj_','mju_')) and callable(getattr(mj,name)):
                fn=getattr(mj,name);original[name]=fn
                def wrapped(*args,_name=name,_fn=fn,**kwargs):return self.call(_name,_fn,*args,**kwargs)
                setattr(mj,name,wrapped)
        # Fixed constructor/reference call graph. Wrappers charge BEFORE calls.
        from flygym.compose.base import BaseCompositionElement
        from flygym.compose.fly.base_fly import BaseFly
        from flygym_demo.complex_terrain.cpg_controller import CPGNetwork
        from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
        from ..contact_v1 import native,law
        from flygym.compose.world.base_world import BaseWorld
        from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
        patched=[]
        def wrap(owner,attribute,family):
            fn=getattr(owner,attribute);patched.append((owner,attribute,fn))
            def charged(*a,**kw):return self.call(family,fn,*a,**kw)
            setattr(owner,attribute,charged)
        for full_name in SPEC_PER_BUILD:
            owner,attribute=full_name.split('.')
            wrap(getattr(mj,owner),attribute,full_name)
        wrap(mj,'MjData','MjData')
        def reserve(owner,attribute,names):
            fn=getattr(owner,attribute);patched.append((owner,attribute,fn))
            def charged(*a,**kw):
                for name in names:self.charge(name)
                result=fn(*a,**kw)
                for name in names:self.completed[name]=self.completed.get(name,0)+1
                return result
            setattr(owner,attribute,charged)
        reserve(BaseWorld,'__init__',('MjSpec.construct',));reserve(BaseFly,'__init__',('MjSpec.construct',))
        reserve(BaseCompositionElement,'compile',('MjSpec.copy',));reserve(BaseFly,'compile',('MjSpec.copy',))
        wrap(BaseCompositionElement,'compile','MjSpec.compile');wrap(BaseFly,'compile','MjSpec.compile')
        # Preserve the classmethod descriptor while charging every observation read.
        descriptor=HybridControllerObservation.__dict__['from_sim'];patched.append((HybridControllerObservation,'from_sim',descriptor))
        def observation(cls,sim,*args,**kwargs):
            contacts=sim.mj_data.contact;n=int(sim.mj_data.ncon);grounds=sim._internal_ground_geom_ids
            owned=np.isin(contacts.geom1[:n],grounds)|np.isin(contacts.geom2[:n],grounds)
            if np.count_nonzero(owned)>512:raise ResourceStop('control observation owned contact capacity')
            return self.call('control_observation',descriptor.__func__,cls,sim,*args,**kwargs)
        HybridControllerObservation.from_sim=classmethod(observation)
        wrap(CPGNetwork,'step','cpg_step')
        wrap(PreprogrammedSteps,'__init__','reference_construct')
        wrap(law,'regularized_velocity','candidate_solve');wrap(law,'shared_twist','candidate_shared_fit')
        wrap(CPGNetwork,'__init__','cpg_init_reset');wrap(CPGNetwork,'reset','cpg_init_reset')
        wrap(PreprogrammedSteps,'get_joint_angles','get_joint_angles')
        wrap(native,'native_cache_manifest','native_cache_manifest')
        try:yield
        finally:
            io._ACTIVE_BUDGET=previous_budget
            for owner,attribute,fn in reversed(patched):setattr(owner,attribute,fn)
            for name,fn in original.items():setattr(mj,name,fn)
    def persist(self,name='resource-terminal.json'):
        try:report=self.check()
        except ResourceStop:report={'wall_seconds':time.time()-self.start,'attempted':self.attempted,'completed':self.completed,'timings':self.timings,'cap_reached':True,'projection':self.projection(),'pending_buffers_bytes':self.pending_buffers}
        write(self.root/name,report)
