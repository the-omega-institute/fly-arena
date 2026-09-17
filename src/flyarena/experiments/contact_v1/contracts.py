"""Pure, versioned observations; all array storage is privately owned float64."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import numpy as np

DT = .0001
SILENCE = .0001
MAX_CONTACTS = 512
MAX_COORDINATES = 1024
MAX_VERTICES = 100000
OBS_VERSION = 'contact-realization-observation/v1'
STATE_VERSION = 'contact-realization-state/v1'
LEGS = ('lf', 'lm', 'lh', 'rf', 'rm', 'rh')
MODES = ('SUPPORT', 'RELEASE_WAIT', 'LIFT', 'TRANSFER', 'LAND', 'REACQUIRE')
CORRECTION_NORMS = np.array([.06, np.sqrt(.015**2+.001**2+.025**2+.02**2+.02**2), .03]*2)


class ContractError(ValueError):
    """No action or controller state has been committed on this exception."""


def array(value, shape, name, *, finite=True, kind='f'):
    a = np.asarray(value)
    if a.shape != shape or a.dtype.kind != kind or (kind == 'f' and a.dtype != np.float64) or (kind == 'i' and a.dtype != np.int64):
        raise ContractError(f'{name}: wrong shape/dtype')
    if finite and not np.isfinite(a).all():
        raise ContractError(f'{name}: nonfinite')
    return a.astype(np.float64 if kind == 'f' else np.int64, copy=True)


def rotation(value, name):
    r = array(value, (3, 3), name)
    if not np.allclose(r.T @ r, np.eye(3), rtol=0, atol=1e-9) or abs(np.linalg.det(r)-1)>1e-9:
        raise ContractError(f'{name}: not a right-handed orthonormal frame')
    return r


def identity(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ContractError(f'{name}: expected sha256')
    return value


def drives(value):
    u = np.asarray(value, dtype=np.float64)
    if u.shape != (2,) or not np.isfinite(u).all() or np.any(u<0):
        raise ContractError('two finite nonnegative drives required')
    c = float(u.mean()); a = float((u[1]-u[0])/(2*c)) if c else 0.
    if c>.4+1e-12 or abs(a)>.8+1e-12:
        raise ContractError('outside motor-v4 domain')
    return c, a


@dataclass(frozen=True)
class Binding:
    model_hash: str
    asset_hash: str
    input_hash: str
    nq: int
    nv: int
    qadr: np.ndarray
    vadr: np.ndarray
    root_dofs: np.ndarray
    foot_geoms: np.ndarray
    ground_geom: int
    fly_geoms: tuple
    lower: np.ndarray
    upper: np.ndarray
    beta: np.ndarray
    coupling: np.ndarray
    biases: np.ndarray
    total_vertices: int

    def validate(self):
        for name in ('model_hash', 'asset_hash', 'input_hash'):
            identity(getattr(self, name), name)
        if type(self.nq) is not int or type(self.nv) is not int or not 1<=self.nq<=MAX_COORDINATES or not 1<=self.nv<=MAX_COORDINATES:
            raise ContractError('coordinate capacity')
        if type(self.total_vertices) is not int or not 30<=self.total_vertices<=MAX_VERTICES:
            raise ContractError('vertex capacity')
        for name, limit in (('qadr', self.nq), ('vadr', self.nv)):
            a = array(getattr(self, name), (6,7), name, kind='i')
            if len(set(a.flat)) != 42 or np.any(a<0) or np.any(a>=limit):
                raise ContractError('active map')
        root = np.asarray(self.root_dofs)
        if root.ndim != 1 or root.dtype.kind != 'i' or root.size != 6 or len(set(root))!=6 or np.any(root<0) or np.any(root>=self.nv) or set(root)&set(self.vadr.flat):
            raise ContractError('root map')
        geoms = array(self.foot_geoms, (6,5), 'foot_geoms', kind='i')
        if len(set(geoms.flat))!=30 or np.any(geoms<0) or self.ground_geom in geoms:
            raise ContractError('foot map')
        if type(self.ground_geom) is not int or self.ground_geom<0 or not isinstance(self.fly_geoms, tuple) or any(type(g) is not int or g<0 for g in self.fly_geoms) or len(set(self.fly_geoms))!=len(self.fly_geoms) or not set(geoms.flat)<=set(self.fly_geoms) or self.ground_geom in self.fly_geoms:
            raise ContractError('fly-ground ownership')
        lo=array(self.lower,(6,7),'lower',finite=False); hi=array(self.upper,(6,7),'upper',finite=False)
        if np.isnan(lo).any() or np.isnan(hi).any() or np.isposinf(lo).any() or np.isneginf(hi).any() or np.any(lo>hi):
            raise ContractError('compiled limits')
        beta=array(self.beta,(6,),'beta')
        if np.any(beta<=np.pi/4) or np.any(beta>=2*np.pi): raise ContractError('native swing interval')
        w=array(self.coupling,(6,6),'coupling'); p=array(self.biases,(6,6),'biases')
        expected=np.array([[0,1,0,1,0,1],[1,0,1,0,1,0]]*3,dtype=float)
        if not np.array_equal(w,expected*10.) or not np.array_equal(p,expected*np.pi):
            raise ContractError('native tripod configuration')
        return self

    @property
    def passive_dofs(self):
        return np.array(sorted(set(range(self.nv))-set(self.root_dofs)-set(self.vadr.flat)),dtype=np.int64)

    def token(self):
        return hashlib.sha256(json.dumps(encode(self.__dict__),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Contact:
    index: int
    geom: int
    ground: int
    leg: int  # -1: nonfoot fly-ground; never a supporting foot
    interval_tick: int
    force: np.ndarray
    distance: float
    frame: np.ndarray
    point_prior: np.ndarray
    local_point: np.ndarray
    point: np.ndarray  # prior material point transported into current state
    jacobian: np.ndarray
    velocity: np.ndarray
    passive_velocity: np.ndarray
    interval_velocity: np.ndarray  # J(q[k-1]) v[k-1]

    def validate(self, binding, tick):
        for name in ('index','geom','ground','leg','interval_tick'):
            if type(getattr(self,name)) is not int: raise ContractError('contact integer identity')
        if self.index<0 or self.interval_tick!=tick-1 or self.ground!=binding.ground_geom:
            raise ContractError('contact clock/ground')
        owner={int(g):i for i,row in enumerate(binding.foot_geoms) for g in row}
        expected=owner.get(self.geom,-1)
        if self.geom not in binding.fly_geoms or self.leg!=expected:
            raise ContractError('contact ownership')
        array(self.force,(6,),'force'); rotation(self.frame,'contact frame')
        for name in ('point_prior','local_point','point','velocity','passive_velocity','interval_velocity'):
            array(getattr(self,name),(3,),name)
        array(self.jacobian,(3,binding.nv),'contact Jacobian')
        if not np.isfinite(self.distance): raise ContractError('contact distance')


@dataclass(frozen=True)
class Observation:
    tick: int
    model_hash: str
    qpos: np.ndarray
    qvel: np.ndarray
    prior_qpos: np.ndarray
    prior_qvel: np.ndarray
    thorax_pos: np.ndarray
    thorax_rotation: np.ndarray
    thorax_velocity: np.ndarray
    thorax_omega: np.ndarray
    com: np.ndarray
    com_velocity: np.ndarray
    gravity: float
    minima: np.ndarray
    minimum_vertices: np.ndarray
    minimum_jacobians: np.ndarray
    distal: np.ndarray
    distal_jacobians: np.ndarray
    contacts: tuple
    actuator_force: np.ndarray
    version: str = OBS_VERSION

    def validate(self,binding,last_tick):
        if self.version!=OBS_VERSION or self.model_hash!=binding.model_hash or type(self.tick) is not int or self.tick<1 or self.tick<=last_tick:
            raise ContractError('observation identity/tick')
        if not isinstance(self.contacts,tuple) or len(self.contacts)>MAX_CONTACTS:
            raise ContractError('contact capacity')
        for name,n in (('qpos',binding.nq),('qvel',binding.nv),('prior_qpos',binding.nq),('prior_qvel',binding.nv)):
            array(getattr(self,name),(n,),name)
        for name in ('thorax_pos','thorax_velocity','thorax_omega','com','com_velocity'):
            array(getattr(self,name),(3,),name)
        rotation(self.thorax_rotation,'thorax_rotation')
        if type(self.gravity) not in (float,int) or not np.isfinite(self.gravity) or self.gravity<=0: raise ContractError('gravity')
        array(self.minima,(6,5,3),'all-mesh minima')
        vertices=array(self.minimum_vertices,(6,5),'minimum vertex identities',kind='i')
        if np.any(vertices<0): raise ContractError('negative minimum vertex')
        array(self.minimum_jacobians,(6,5,3,binding.nv),'all-mesh Jacobians')
        array(self.distal,(6,3),'distal centroid'); array(self.distal_jacobians,(6,3,binding.nv),'distal Jacobians')
        array(self.actuator_force,(48,),'actuator_force')
        indices=set()
        for con in self.contacts:
            if not isinstance(con,Contact): raise ContractError('contact type')
            con.validate(binding,self.tick)
            if con.index in indices: raise ContractError('duplicate contact interval identity')
            indices.add(con.index)
            if not np.allclose(con.velocity,con.jacobian@self.qvel,atol=1e-10,rtol=0) or not np.allclose(con.passive_velocity,con.jacobian[:,binding.passive_dofs]@self.qvel[binding.passive_dofs],atol=1e-10,rtol=0):
                raise ContractError('incoherent endpoint contact velocity')
        return self

    def loads(self):
        total=np.zeros(6); distal=np.zeros(6)
        for con in self.contacts:
            if con.leg>=0 and con.force[0]>0:
                total[con.leg]+=con.force[0]
        return total


def encode(value):
    """JSON-safe arrays retain exact dtype, shape and float64 bits, including limits."""
    if isinstance(value,np.ndarray):
        if value.dtype.kind not in 'fiub': raise ContractError('unsupported checkpoint dtype')
        return {'__array__':value.dtype.str,'shape':list(value.shape),'hex':np.ascontiguousarray(value).tobytes().hex()}
    if isinstance(value,np.generic): return value.item()
    if isinstance(value,dict): return {str(k):encode(v) for k,v in value.items()}
    if isinstance(value,tuple): return {'__tuple__':[encode(v) for v in value]}
    if isinstance(value,list): return [encode(v) for v in value]
    if value is None or isinstance(value,(str,bool,int)): return value
    if isinstance(value,float) and math.isfinite(value): return value
    raise ContractError('unsupported/nonfinite checkpoint scalar')


def decode(value):
    if isinstance(value,dict):
        if '__array__' in value:
            if set(value)!={'__array__','shape','hex'}: raise ContractError('array schema')
            dtype=np.dtype(value['__array__']); shape=value['shape']
            if dtype.kind not in 'fiub' or not isinstance(shape,list) or any(type(n) is not int or n<0 for n in shape) or math.prod(shape)>2000000:
                raise ContractError('array capacity/schema')
            raw=bytes.fromhex(value['hex'])
            if len(raw)!=math.prod(shape)*dtype.itemsize: raise ContractError('array bytes')
            return np.frombuffer(raw,dtype=dtype).reshape(shape).copy()
        if '__tuple__' in value:
            if set(value)!={'__tuple__'}: raise ContractError('tuple schema')
            return tuple(decode(v) for v in value['__tuple__'])
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list): return [decode(v) for v in value]
    if value is None or isinstance(value,(str,bool,int)) or isinstance(value,float) and math.isfinite(value): return value
    raise ContractError('checkpoint scalar')


def observation_state(obs):
    return {**deepcopy(obs.__dict__),'contacts':tuple(deepcopy(c.__dict__) for c in obs.contacts)}


def observation_from_state(state):
    state=deepcopy(state)
    state['contacts']=tuple(Contact(**v) for v in state['contacts'])
    return Observation(**state)
