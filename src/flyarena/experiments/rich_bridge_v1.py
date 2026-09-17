"""Unqualified four-input/three-intent research candidate; no recurrence here.

All transitions are pure proposals until the complete synchronous boundary is
validated. This module imports neither a neural backend nor a physical engine.
"""
from copy import deepcopy, copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np
from .sensor import encode_odor
from .motor import MotorTransfer

PROFILE = 'rich-odor-obstacle-touch-excursion/v1'
CHANNELS = ('odor_left', 'odor_right', 'tactile_left', 'tactile_right')
DT = .0001
PERIOD = 100
BETA = float(np.exp(-.01/.05))
KERNEL_SHA = '3d5f08551e34a4429d8a2c542b6d1becb6e58e0de5b0922e1d9d5c78c9e46e7d'


def need(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def hexhash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def array(value, shape, low=None, high=None):
    a = np.asarray(value)
    need(a.dtype == np.float64 and a.shape == shape and np.isfinite(a).all(), 'float64 shape/finite contract')
    need(low is None or np.all(a >= low), 'value below bound')
    need(high is None or np.all(a <= high), 'value above bound')
    return a.copy()


def intent_parameters(intent, base_frequency, base_coupling):
    """Algebra only: no oscillator, controller, neural or physical advance."""
    c, a, e = array(intent, (3,))
    need(0 <= c <= .4+1e-12 and abs(a) <= .8+1e-12 and .75 <= e <= 1, 'intent domain')
    frequency = array(base_frequency, (6,), 0)
    coupling = array(base_coupling, (6, 6))
    return frequency*(c/.6), coupling*(c/.6), e*np.repeat([1-a, 1+a], 3)


@dataclass(frozen=True)
class NeuralMap:
    count: int
    populations: tuple
    identity: str

    def __post_init__(self):
        need(type(self.count) is int and self.count > 0 and hexhash(self.identity), 'neural map identity')
        need(isinstance(self.populations, tuple) and len(self.populations) == 6, 'six immutable populations')
        for group in self.populations:
            need(isinstance(group, tuple) and group and all(type(i) is int and 0 <= i < self.count for i in group), 'map index range')
            need(len(set(group)) == len(group), 'duplicate neuron index')
        need(len(set(sum(self.populations[:4], ()))) == sum(map(len, self.populations[:4])), 'sensory overlap')
        need(not set(self.populations[4]) & set(self.populations[5]), 'DN and Q overlap')


def load_maps():
    """Artifact generated once from hash-verified canonical metadata, no graph."""
    from .rich_bridge_v1_seals import MAP_SHA256
    raw = Path(__file__).with_name('rich_bridge_v1_maps.json').read_bytes()
    need(hashlib.sha256(raw).hexdigest() == MAP_SHA256, 'selector artifact changed')
    value = json.loads(raw)
    need(value['kernel_sha256'] == KERNEL_SHA and value['counts'] == [884,1344,1264,1294,1314,49], 'selector contract')
    return NeuralMap(value['neuron_count'], tuple(tuple(x['indices']) for x in value['populations']), digest(value))


def validate_layout(ids, sides, artifact):
    """Read-only ID/side validation; positions are never inferred from anatomy."""
    ids=np.asarray(ids);sides=np.asarray(sides)
    need(ids.dtype==np.int64 and sides.dtype==np.int8 and ids.shape==sides.shape==(artifact['neuron_count'],),'layout shape/dtype')
    need(np.all(ids[1:]>ids[:-1]),'neuron IDs must be unique and sorted')
    for population in artifact['populations']:
        indices=np.asarray(population['indices'],dtype=np.int64)
        need(np.all(indices>=0) and np.all(indices<len(ids)),'layout index')
        need([str(int(x)) for x in ids[indices]]==population['body_ids'],'neuron ID/order mismatch')
        side=population['selector'].get('side')
        if side is not None:need(np.all(sides[indices]=={'L':1,'R':-1}[side]),'neuron side mismatch')


def bind_canonical_neurons(metadata_root):
    """Verify frozen small canonical files without opening any graph edges."""
    mapping=load_maps()
    value=json.loads(Path(__file__).with_name('rich_bridge_v1_maps.json').read_text())
    root=Path(metadata_root)
    for name in ('ids.npy','side.npy'):
        need(hashlib.sha256((root/name).read_bytes()).hexdigest()==value['metadata_sha256'][name],'canonical layout hash mismatch')
    manifest=json.loads((root/'manifest.json').read_text())
    need(hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()==value['manifest_sha256'] and manifest['sha256']==value['graph_sha256'],'graph manifest mismatch')
    validate_layout(np.load(root/'ids.npy',mmap_mode='r',allow_pickle=False),np.load(root/'side.npy',mmap_mode='r',allow_pickle=False),value)
    return mapping


def profile_manifest():
    from .rich_bridge_v1_seals import BASE_SOURCES
    root = Path(__file__).resolve().parents[3]
    for name, expected in BASE_SOURCES.items():
        need(hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, 'preserved source changed: '+name)
    names = ('rich_bridge_v1.py','rich_bridge_v1_body.py','rich_bridge_v1_controller.py','rich_bridge_v1_seals.py','rich_bridge_v1_maps.json')
    sources = {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in names}
    return {'id': PROFILE, 'ready': False, 'research_only': True, 'qualified_base': False,
            'capabilities': ['sensory-frame4/v1','motor-intent3/v1','owned-state-checkpoint/v1'],
            'unavailable': ['physical-admission','full-restore','cuda','vision','proprioception','aggression'],
            'sources': sources, 'base_sources': dict(BASE_SOURCES), 'neural_map': load_maps().identity,
            'dt': DT, 'period_ticks': PERIOD, 'rate_unit': 'Hz', 'rate_reference': 100.,
            'filter_seconds': .05, 'excursion_range': [.75,1.], 'inputs': list(CHANNELS)}


def admit(request):
    """No caller can turn a candidate source profile into execution admission."""
    need(request.get('profile') == PROFILE, 'unknown profile')
    raise ValueError('unqualified research source; no production, physical or CUDA admission')


@dataclass(frozen=True)
class GeometryBinding:
    model_sha256: str
    subject: str
    geom_names: tuple
    leg_sides: tuple
    obstacles: tuple
    actuator_sha256: str
    dt: float = DT

    def __post_init__(self):
        need(hexhash(self.model_sha256) and isinstance(self.subject,str) and self.subject, 'body identity')
        need(hexhash(self.actuator_sha256),'actuator binding identity')
        need(type(self.dt) is float and self.dt == DT, 'body timestep')
        need(isinstance(self.geom_names,tuple) and len(set(self.geom_names)) == len(self.geom_names), 'geometry names')
        need(isinstance(self.leg_sides,tuple) and len(self.leg_sides) == len(self.geom_names), 'complete geometry ownership')
        need(all(x in ('L','R','excluded') for x in self.leg_sides), 'geometry side')
        need('L' in self.leg_sides and 'R' in self.leg_sides, 'bilateral leg geometry')
        need(isinstance(self.obstacles,tuple) and len(set(self.obstacles)) == len(self.obstacles), 'obstacle IDs')
        need(all(type(i) is int and 0 <= i < len(self.geom_names) and self.leg_sides[i] == 'excluded'
                 and self.geom_names[i].startswith('obstacle-') for i in self.obstacles), 'explicit external obstacles only')
        for name, side in zip(self.geom_names,self.leg_sides):
            need(isinstance(name,str) and bool(name), 'named geometry required')
            if side != 'excluded':
                need(name.startswith(self.subject+'/'), 'leg belongs to another fly')

    @property
    def identity(self):
        return digest(self.__dict__)


class ContactLatch:
    def __init__(self, geometry):
        self.geometry = geometry
        self.start_tick = 0
        self.next_tick = 0
        self.touches = [False, False]
        self.events = []

    def observe(self, source_tick, model_sha256, contacts):
        """Consume copied contact (geom1,geom2,dist) rows from a completed solve.

        source_tick is the solve prestate tick, not the endpoint geometry tick.
        Caller supplies even empty rows for every tick; gaps cannot look blank.
        """
        need(type(source_tick) is int and source_tick == self.next_tick and source_tick < self.start_tick+PERIOD, 'contact tick gap/order')
        need(model_sha256 == self.geometry.model_sha256, 'contact model mismatch')
        touches = self.touches.copy(); events = self.events.copy()
        for index, row in enumerate(contacts):
            need(len(row) == 3, 'contact row')
            g1,g2,dist = row
            need(all(type(g) is int and 0 <= g < len(self.geometry.geom_names) for g in (g1,g2)), 'contact geometry')
            need(type(dist) in (float,int) and np.isfinite(dist), 'contact distance')
            if dist > 0:
                continue
            for own,other in ((g1,g2),(g2,g1)):
                side = self.geometry.leg_sides[own]
                if side in ('L','R') and other in self.geometry.obstacles:
                    touches[side == 'R'] = True
                    events.append((source_tick,index,own,other,float(dist)))
        need(len(events) <= 100000, 'contact interval event cap')
        self.touches,self.events,self.next_tick = touches,events,source_tick+1

    def frame(self, tick, raw_odor, binding):
        need(type(tick) is int and tick % PERIOD == 0 and tick == self.next_tick, 'boundary contact completeness')
        need((tick == 0 and self.start_tick == 0) or tick == self.start_tick+PERIOD, 'contact interval')
        odor = array(raw_odor,(2,),0)
        values = tuple(encode_odor(*odor)) + tuple(float(v) for v in self.touches)
        return {'schema':'sensory-frame4/v1','binding':binding,'model':self.geometry.model_sha256,
                'geometry':self.geometry.identity,'tick':tick,'channels':CHANNELS,'values':values,
                'contact_start':self.start_tick,'contact_end':tick,'events':tuple(self.events)}


@dataclass(frozen=True, init=False)
class FrozenDecoder:
    """Exact frozen v2 kernel algebra, with no Brain/graph imports or training."""
    def __init__(self, neurons, centers, weights, bandwidth, asset_sha256):
        need(hexhash(asset_sha256), 'decoder asset digest')
        need(all(isinstance(i,(int,np.integer)) and not isinstance(i,(bool,np.bool_)) for i in neurons),'decoder neuron index dtype')
        object.__setattr__(self,'neurons',tuple(int(i) for i in neurons))
        need(self.neurons and len(set(self.neurons)) == len(self.neurons), 'decoder neuron order')
        centers = array(centers,(len(centers),len(self.neurons)))
        weights = array(weights,(len(centers),2))
        for name,value in (('centers',centers),('weights',weights),('norm',np.sum(centers**2,axis=1))):
            object.__setattr__(self,name,np.frombuffer(value.tobytes(),dtype=np.float64).reshape(value.shape))
        need(len(self.centers)>0 and np.isfinite(bandwidth) and bandwidth>0, 'decoder bandwidth')
        object.__setattr__(self,'bandwidth',float(bandwidth))
        object.__setattr__(self,'asset_sha256',asset_sha256)
        object.__setattr__(self,'identity',digest({'asset':asset_sha256,'neurons':self.neurons,'bandwidth':self.bandwidth,
            'centers':hashlib.sha256(self.centers.tobytes()).hexdigest(),'weights':hashlib.sha256(self.weights.tobytes()).hexdigest()}))

    @classmethod
    def from_asset(cls,path,expected_sha256):
        raw=Path(path).read_bytes()
        need(hashlib.sha256(raw).hexdigest()==expected_sha256,'decoder asset changed')
        import io
        with np.load(io.BytesIO(raw),allow_pickle=False) as a:
            need(set(a.files)=={'neurons','centers','weights','bandwidth'},'decoder fields')
            return cls(a['neurons'],a['centers'],a['weights'],float(a['bandwidth']),expected_sha256)

    def command(self,rates):
        x=array(rates,(len(self.neurons),),0)/100
        d2=np.maximum(0,self.norm+x@x-2*self.centers@x)
        kernel=np.exp(-d2/(2*self.bandwidth**2))
        activity=min(1.,float(np.linalg.norm(x))/.02)
        return np.clip(kernel@self.weights,0,1.5)*activity


class BridgeState:
    """Candidate-owned state only. This is not a full neural/body checkpoint."""
    def __init__(self,mapping,geometry,decoder,profile_sha256):
        need(type(mapping) is NeuralMap and type(geometry) is GeometryBinding and type(decoder) is FrozenDecoder, 'concrete bridge components')
        need(decoder.neurons == mapping.populations[4] and hexhash(profile_sha256),'decoder/profile binding')
        self.mapping=mapping;self.geometry=geometry;self.decoder=decoder
        self.binding=digest({'profile':profile_sha256,'map':mapping.identity,'geometry':geometry.identity,'decoder':decoder.identity})
        self.latch=ContactLatch(geometry);self.motor=MotorTransfer();self.q=0.
        self.boundary_tick=-PERIOD;self.held_current=np.zeros(mapping.count);self.intent=np.array([0.,0.,1.])
        self.held_frame=None

    @classmethod
    def from_canonical(cls,metadata_root,geometry):
        from .rich_bridge_v1_seals import DECODER_SHA256
        mapping=bind_canonical_neurons(metadata_root)
        decoder=FrozenDecoder.from_asset(Path(metadata_root)/'research-v2/readout.npz',DECODER_SHA256)
        return cls(mapping,geometry,decoder,digest(profile_manifest()))

    def propose(self,frame,rates,output_off=False):
        need(type(output_off) is bool,'output-off boolean')
        expected={'schema','binding','model','geometry','tick','channels','values','contact_start','contact_end','events'}
        need(type(frame) is dict and set(frame)==expected,'frame fields')
        need(frame['schema']=='sensory-frame4/v1' and frame['binding']==self.binding and frame['model']==self.geometry.model_sha256 and frame['geometry']==self.geometry.identity,'frame identity')
        tick=frame['tick'];need(type(tick) is int and tick==self.boundary_tick+PERIOD,'boundary tick')
        need(frame['channels']==CHANNELS,'input channel order')
        need(isinstance(frame['values'],tuple) and len(frame['values'])==4 and all(isinstance(v,(int,float,np.floating)) and not isinstance(v,(bool,np.bool_)) for v in frame['values']),'four numeric channel values')
        values=np.asarray(frame['values'],dtype=np.float64);array(values,(4,),0,1)
        need(all(v in (0.,1.) for v in values[2:]),'binary tactile')
        # Reconstruct from owned latch, so external callers cannot invent touch.
        need(type(frame['contact_start']) is int and type(frame['contact_end']) is int and frame['contact_start']==self.latch.start_tick and frame['contact_end']==self.latch.next_tick==tick,'frame contact provenance')
        need(frame['events']==tuple(self.latch.events) and tuple(values[2:])==tuple(float(v) for v in self.latch.touches),'frame latch mismatch')
        need((tick==0 and self.latch.start_tick==0) or tick-self.latch.start_tick==PERIOD,'frame interval')
        rate=array(rates,(self.mapping.count,),0)
        current=np.zeros(self.mapping.count)
        for group,value in zip(self.mapping.populations[:4],values):current[list(group)]=48.*value
        shadow=deepcopy(self.motor)
        selected=rate[list(self.mapping.populations[4]+self.mapping.populations[5])]
        if output_off or not np.any(selected):
            shadow.state.fill(0);shadow.decoded_state.fill(0);q=0.;intent=np.array([0.,0.,1.])
        else:
            u=shadow.advance(self.decoder.command(rate[list(self.mapping.populations[4])]))
            c=float(u.mean());a=float((u[1]-u[0])/(2*c)) if c else 0.
            m=float(np.clip(rate[list(self.mapping.populations[5])].mean()/100.,0.,1.))
            q=BETA*self.q+(1-BETA)*m;intent=np.array([c,a,1-.25*q])
        intent_parameters(intent,np.ones(6),np.ones((6,6)))
        proposal=copy(self);proposal.latch=deepcopy(self.latch)
        proposal.motor=shadow;proposal.q=q;proposal.intent=intent;proposal.held_current=current
        proposal.held_frame=deepcopy(frame);proposal.boundary_tick=tick
        proposal.latch.start_tick=tick;proposal.latch.touches=[False,False];proposal.latch.events=[]
        return proposal

    def checkpoint(self):
        return {'schema':'rich-bridge-owned-state/v1','binding':self.binding,
                'boundary_tick':self.boundary_tick,'q':self.q,'intent':self.intent.copy(),
                'held_current':self.held_current.copy(),'held_frame':deepcopy(self.held_frame),
                'motor_state':self.motor.state.copy(),'decoded_state':self.motor.decoded_state.copy(),
                'contact_start':self.latch.start_tick,'contact_next':self.latch.next_tick,
                'touches':self.latch.touches.copy(),'events':deepcopy(self.latch.events)}

    def restore_owned(self,checkpoint):
        need(type(checkpoint) is dict and set(checkpoint)==set(self.checkpoint()),'checkpoint fields')
        c=deepcopy(checkpoint)
        need(c['schema']=='rich-bridge-owned-state/v1' and c['binding']==self.binding,'checkpoint identity')
        tick=c['boundary_tick'];need(type(tick) is int and tick>=-PERIOD and tick%PERIOD==0,'checkpoint tick')
        need(type(c['q']) is float and np.isfinite(c['q']) and 0<=c['q']<=1,'checkpoint filter')
        intent=array(c['intent'],(3,));intent_parameters(intent,np.ones(6),np.ones((6,6)))
        need(intent[2]==1-.25*c['q'],'checkpoint excursion/filter')
        current=array(c['held_current'],(self.mapping.count,),0,48)
        ms=array(c['motor_state'],(2,),0,1.5);ds=array(c['decoded_state'],(2,),0,1.5)
        common=float(ms.mean());asymmetry=float((ms[1]-ms[0])/(2*common)) if common else 0.
        need(np.array_equal(intent[:2],np.array([common,asymmetry])),'checkpoint motor/intent mismatch')
        need(type(c['contact_start']) is int and c['contact_start']==max(0,tick),'checkpoint contact start')
        need(type(c['contact_next']) is int and c['contact_start']<=c['contact_next']<=c['contact_start']+PERIOD,'checkpoint contact next')
        need(type(c['touches']) is list and len(c['touches'])==2 and all(type(x) is bool for x in c['touches']),'checkpoint touch bits')
        latch=ContactLatch(self.geometry);latch.start_tick=c['contact_start'];latch.next_tick=c['contact_start']
        by_tick={i:[] for i in range(latch.start_tick,c['contact_next'])}
        need(type(c['events']) is list,'checkpoint events')
        previous=(-1,-1)
        for event in c['events']:
            need(type(event) is tuple and len(event)==5,'checkpoint event row')
            t,index,own,other,dist=event
            need(type(t) is int and t in by_tick and type(index) is int and index>=0,'checkpoint event time')
            need((t,index)>previous,'checkpoint event order/duplicate');previous=(t,index)
            need(type(own) is int and type(other) is int and type(dist) is float and own in range(len(self.geometry.leg_sides)) and self.geometry.leg_sides[own] in ('L','R') and other in self.geometry.obstacles and np.isfinite(dist) and dist<=0,'checkpoint event geometry')
            by_tick[t].append((own,other,dist))
        for t,rows in by_tick.items():latch.observe(t,self.geometry.model_sha256,rows)
        need(latch.touches==c['touches'],'checkpoint latch/event mismatch')
        frame=c['held_frame']
        if tick<0:need(frame is None and not current.any() and not ms.any() and not ds.any() and c['q']==0 and c['contact_next']==0 and not c['events'] and not any(c['touches']),'initial checkpoint state')
        else:
            # Validate the complete prior frame with the same proposal contract,
            # reconstructing its completed contact interval independently.
            need(type(frame) is dict and frame.get('tick')==tick,'held frame tick')
            prior=BridgeState(self.mapping,self.geometry,self.decoder,'0'*64)
            prior.binding=self.binding;prior.boundary_tick=tick-PERIOD
            prior.latch.start_tick=max(0,tick-PERIOD);prior.latch.next_tick=prior.latch.start_tick
            rows_by_tick={i:[] for i in range(prior.latch.start_tick,tick)}
            events=frame.get('events');need(type(events) is tuple,'held frame events')
            last=(-1,-1)
            for event in events:
                need(type(event) is tuple and len(event)==5,'held event row')
                t,index,own,other,dist=event
                need(type(t) is int and t in rows_by_tick and type(index) is int and index>=0 and (t,index)>last,'held event provenance')
                need(type(own) is int and type(other) is int and type(dist) is float and 0<=own<len(self.geometry.leg_sides) and self.geometry.leg_sides[own] in ('L','R') and other in self.geometry.obstacles and np.isfinite(dist) and dist<=0,'held event geometry')
                last=(t,index);rows_by_tick[t].append((own,other,dist))
            for t,rows in rows_by_tick.items():prior.latch.observe(t,self.geometry.model_sha256,rows)
            prior.latch.events=list(events)  # Preserve original solver contact indices.
            proposed=prior.propose(frame,np.zeros(self.mapping.count))
            need(np.array_equal(proposed.held_current,current),'held current/frame mismatch')
        # Commit only after every field has been checked. No caller aliases.
        self.boundary_tick=tick;self.q=c['q'];self.intent=intent;self.held_current=current;self.held_frame=frame
        self.motor.state=ms;self.motor.decoded_state=ds
        self.latch.start_tick=c['contact_start'];self.latch.next_tick=c['contact_next'];self.latch.touches=c['touches'];self.latch.events=c['events']

    def restore_full(self,*args,**kwargs):
        raise ValueError('full restore unavailable: independently bound atomic neural and native-body restoration required')


def commit_boundary(states,frames,rates,external_arrays,output_off=False):
    """Synchronous snapshot/propose/commit; no neural or body step is called.

    Current destinations must be writable native contiguous float64 arrays.
    Validate the complete batch before proposals so overlapping logical entries
    cannot collapse distinct channels or leave a partially committed subject.
    """
    count=len(states)
    need(count>0 and len(frames)==len(rates)==len(external_arrays)==count,'subject batch')
    need(all(type(s) is BridgeState for s in states),'concrete subject states')
    need(len({id(s) for s in states})==count,'duplicate subject state')
    need(len({s.geometry.subject for s in states})==count and len({s.geometry.model_sha256 for s in states})==1,'shared model/unique subject identities')
    need(all(s.geometry.geom_names==states[0].geometry.geom_names for s in states),'shared world geometry order')
    need(len({f['tick'] for f in frames})==1,'asynchronous subject frames')
    for i,a in enumerate(external_arrays):
        array(a,(states[i].mapping.count,))
        need(type(a) is np.ndarray and a.flags.writeable and a.flags.c_contiguous and a.dtype.isnative,'external destination requires writable native contiguous float64')
        need(not any(np.shares_memory(a,b) for b in external_arrays[:i]),'shared subject external state')
        need(not any(np.shares_memory(a,r) for r in rates),'external array aliases neural rates')
    proposals=[s.propose(deepcopy(f),np.array(r,copy=True),output_off) for s,f,r in zip(states,frames,rates)]
    for state,proposed,external in zip(states,proposals,external_arrays):
        external[:]=proposed.held_current
        state.__dict__=proposed.__dict__
    return np.stack([s.intent.copy() for s in states])


def snapshot_boundary(states,tick,raw_odors,rates):
    """Copy every subject's current rates/odor before decoding or writing input.

    The host owns the single integer clock and has already copied all completed
    solver contacts into the latches. No scene, browser clock or recurrence here.
    Newly committed stimulus can only affect the following readout interval.
    """
    need(len(states)>0 and len(states)==len(raw_odors)==len(rates),'snapshot subject batch')
    odor_copies=[array(x,(2,),0) for x in raw_odors]
    rate_copies=[array(x,(s.mapping.count,),0) for s,x in zip(states,rates)]
    frames=[s.latch.frame(tick,odor,s.binding) for s,odor in zip(states,odor_copies)]
    return frames,rate_copies
