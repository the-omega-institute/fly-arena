"""Bounded training sessions, built from ordinary flies and verified matches."""
from __future__ import annotations

import fcntl
import json
import math
import time
import uuid
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from ..common import canonical
from ..contracts import CircuitId, FlySpec, MatchRequest, StrictModel


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS training_runs(
      id TEXT PRIMARY KEY, owner TEXT NOT NULL, spec TEXT NOT NULL,
      runtime_hash TEXT NOT NULL, status TEXT NOT NULL, control TEXT NOT NULL DEFAULT 'run',
      error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS training_members(
      run_id TEXT NOT NULL, generation INTEGER NOT NULL, slot INTEGER NOT NULL,
      fly_id TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0,
      fitness REAL, PRIMARY KEY(run_id,generation,slot));
    CREATE INDEX IF NOT EXISTS training_fly ON training_members(fly_id);
    CREATE TABLE IF NOT EXISTS training_evaluations(
      run_id TEXT NOT NULL, generation INTEGER NOT NULL, slot INTEGER NOT NULL,
      trial INTEGER NOT NULL, match_id TEXT NOT NULL UNIQUE,
      PRIMARY KEY(run_id,generation,slot,trial));
    CREATE TABLE IF NOT EXISTS training_keys(
      owner TEXT NOT NULL,key TEXT NOT NULL,spec TEXT NOT NULL,run_id TEXT NOT NULL,
      PRIMARY KEY(owner,key));
    CREATE TABLE IF NOT EXISTS training_publications(
      run_id TEXT PRIMARY KEY, published REAL NOT NULL);
    ''')


class EvaluationCondition(StrictModel):
    map_id: Literal['orchard','maze','scarcity','ring','terrarium']
    seed: int = Field(ge=0, le=2**31-1, strict=True)


class TrainingSpec(StrictModel):
    name: str = Field(default='My evolution', min_length=1, max_length=64)
    founder_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    opponent_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    strategy: Literal['evolution', 'random_search', 'cross_entropy', 'external'] = 'evolution'
    optimizer_name: str = Field(default='', max_length=64)
    circuits: list[CircuitId] = Field(default_factory=lambda:['olfactory','projection','descending'],max_length=8)
    mutation_strength: float = Field(default=.08,ge=.01,le=.3)
    population: int = Field(default=3,ge=2,le=6)
    generations: int = Field(default=3,ge=1,le=8)
    max_evaluations: int = Field(default=18,ge=2,le=96)
    map_id: Literal['orchard','maze','scarcity','ring','terrarium'] = 'orchard'
    mode: Literal['forage','contest'] = 'forage'
    duration_seconds: int = Field(default=2,ge=1,le=10)
    seed: int = Field(default=42,ge=0,le=2**31-1)
    evaluation_conditions: list[EvaluationCondition] | None = Field(default=None,min_length=1,max_length=4)
    bridge_profile: Literal['legacy-v1','sensorimotor-research-v2'] = 'legacy-v1'

    @property
    def positions_per_condition(self):
        return 1 if self.mode=='forage' else 2

    @property
    def conditions(self):
        return self.evaluation_conditions or [EvaluationCondition(map_id=self.map_id, seed=self.seed)]

    @property
    def trials(self):
        return len(self.conditions)*self.positions_per_condition

    @property
    def evaluations(self):
        return self.population*self.generations*self.trials

    @model_validator(mode='after')
    def bounded(self):
        if not self.name.strip():raise ValueError('Name cannot be blank')
        if self.strategy == 'external':self.circuits = []
        elif not self.circuits:raise ValueError('Choose at least one circuit')
        if len(set(self.circuits))!=len(self.circuits):raise ValueError('Choose distinct circuits')
        if self.mode=='contest' and self.opponent_id is None:raise ValueError('Choose a fixed opponent')
        if len({(c.map_id,c.seed) for c in self.conditions})!=len(self.conditions):
            raise ValueError('Choose distinct map/seed conditions')
        if self.evaluations>self.max_evaluations:
            raise ValueError(f'This plan needs {self.evaluations} evaluations; budget is {self.max_evaluations}')
        return self


def condition_results(spec, matches):
    """Only complete condition groups get a score; retain every match for replay."""
    results=[]
    for index, condition in enumerate(spec.conditions):
        group=matches[index*spec.positions_per_condition:(index+1)*spec.positions_per_condition]
        verified=sum(m is not None and m['status']=='verified' for m in group)
        fitness=None
        if len(group)==spec.positions_per_condition and verified==spec.positions_per_condition:
            scores=[m['result']['scores'][position] -
                    (m['result']['scores'][1-position] if spec.mode=='contest' else 0)
                    for position,m in enumerate(group)]
            if all(math.isfinite(score) for score in scores):fitness=sum(scores)/len(scores)
        results.append(dict(condition=condition.model_dump(),fitness=fitness,
                            evaluations_completed=verified,evaluations_total=spec.positions_per_condition,
                            matches=group))
    return results


class ProposedCandidate(StrictModel):
    generation: int = Field(ge=0, le=7, strict=True)
    slot: int = Field(ge=0, le=5, strict=True)
    spec: FlySpec


def proposal_position(spec, members):
    """The first generation still needing evaluation; indices are zero-based."""
    for generation in range(spec.generations):
        group = [m for m in members if m['generation'] == generation]
        if len(group) < spec.population or any(m['fitness'] is None for m in group):
            return generation, [slot for slot in range(spec.population)
                                if not any(m['slot'] == slot for m in group)
                                and (generation, slot) != (0, 0)]
    return None, []


def check_proposal(db, owner, position, candidate):
    """Rechecked inside candidate insertion to fence stop/admission races."""
    ident, generation, slot = position
    run = db.execute('SELECT * FROM training_runs WHERE id=? AND owner=?', (ident, owner)).fetchone()
    if run is None:
        raise ValueError('Training session not found')
    plan = TrainingSpec.model_validate_json(run['spec'])
    if plan.strategy != 'external':
        raise ValueError('Candidate submission requires an external strategy session')
    old = db.execute('SELECT f.id,f.spec FROM training_members m JOIN flies f ON f.id=m.fly_id WHERE m.run_id=? AND m.generation=? AND m.slot=?', position).fetchone()
    if old:
        prior = FlySpec.model_validate_json(old['spec']).model_dump(by_alias=True)
        if prior != candidate:
            raise ValueError('This generation slot already contains a different candidate')
        return old['id']
    if run['status'] in {'complete', 'stopped', 'failed'} or run['control'] == 'stop':
        raise ValueError('Training session is already terminal')
    members = [dict(r) for r in db.execute('SELECT * FROM training_members WHERE run_id=?', (ident,))]
    current, slots = proposal_position(plan, members)
    if generation != current or slot not in slots:
        raise ValueError('Submit an open slot in the current generation; G1 slot 0 is the server baseline')
    allowed_parents = {plan.founder_id} | {m['fly_id'] for m in members
        if m['generation'] < generation and m['fitness'] is not None}
    founder=json.loads(db.execute('SELECT spec FROM flies WHERE id=?',(plan.founder_id,)).fetchone()[0])
    if candidate['model_profile']!=founder['model_profile']:raise ValueError('Keep the founder neural model within a training session')
    if candidate['parent_id'] not in allowed_parents:
        raise ValueError('Parent must be the founder or an evaluated earlier-generation individual in this session')
    return None


class TrainingService:
    def __init__(self,store,compiler):
        self.store,self.compiler=store,compiler

    def create(self,owner,spec,runtime_hash,key=None):
        spec=TrainingSpec.model_validate(spec);raw=canonical(spec.model_dump()).decode()
        if key is not None and (not key or len(key)>128):raise ValueError('Invalid idempotency key')
        ident=uuid.uuid4().hex;now=time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                prior=db.execute('SELECT * FROM training_keys WHERE owner=? AND key=?',(owner,key)).fetchone()
                if prior:
                    # Historical plans have no evaluation_conditions field. Compare
                    # parsed plans so their original idempotency keys still work.
                    if TrainingSpec.model_validate_json(prior['spec']).model_dump()!=spec.model_dump():
                        raise ValueError('Idempotency key already used for another training plan')
                    return self.get(prior['run_id'])
            for fly_id in [spec.founder_id]+([spec.opponent_id] if spec.mode=='contest' else []):
                row=db.execute('SELECT spec FROM flies WHERE id=?',(fly_id,)).fetchone()
                if row is None:raise ValueError('Starting fly or opponent does not exist')
                from ..models import require_model_bridge
                require_model_bridge(json.loads(row['spec']).get('model_profile','malecns-lif-cpu-v1'),spec.bridge_profile)
            active=db.execute("SELECT count(*) FROM training_runs WHERE owner=? AND status NOT IN ('complete','stopped','failed')",(owner,)).fetchone()[0]
            if active>=2:raise ValueError('Finish or stop a session first; at most 2 unfinished training sessions')
            db.execute("INSERT INTO training_runs(id,owner,spec,runtime_hash,status,created,updated) VALUES(?,?,?,?,'queued',?,?)",(ident,owner,raw,runtime_hash,now,now))
            if key:db.execute('INSERT INTO training_keys VALUES(?,?,?,?)',(owner,key,raw,ident))
        return self.get(ident)

    def get(self,ident):
        with self.store.db() as db:
            row=db.execute('SELECT * FROM training_runs WHERE id=?',(ident,)).fetchone()
            if row is None:return None
            members=[dict(r) for r in db.execute('SELECT * FROM training_members WHERE run_id=? ORDER BY generation,slot',(ident,))]
            evaluations=[dict(r) for r in db.execute('SELECT * FROM training_evaluations WHERE run_id=? ORDER BY generation,slot,trial',(ident,))]
        result=dict(row);result['spec']=json.loads(result['spec']);spec=TrainingSpec.model_validate(result['spec'])
        matches={r['match_id']:self.store.match(r['match_id']) for r in evaluations}
        for member in members:
            member['fly']=self.store.fly(member['fly_id'])
            member['matches']=[matches[r['match_id']] for r in evaluations if r['generation']==member['generation'] and r['slot']==member['slot']]
            member['condition_results']=condition_results(spec,member['matches'])
        completed=sum(m is not None and m['status']=='verified' for m in matches.values())
        result.update(members=members,evaluations_total=spec.evaluations,evaluations_started=len(evaluations),evaluations_completed=completed,
                      progress=completed/spec.evaluations)
        scored=[m for m in members if m['fitness'] is not None]
        result['best_fly_id']=max(scored,key=lambda m:(m['fitness'],-m['generation'],-m['slot']))['fly_id'] if scored else None
        result['baseline_fitness']=next((m['fitness'] for m in members if m['generation']==0 and m['slot']==0),None)
        if result['control']!='run' and result['status'] not in {'complete','stopped','failed'}:
            pending=any(m and m['status'] in {'queued','running'} for m in matches.values())
            result['status']=('pausing' if pending else 'paused') if result['control']=='pause' else ('stopping' if pending else 'stopped')
        position, slots = proposal_position(spec, members) if spec.strategy == 'external' else (None, [])
        if result['status'] in {'complete', 'failed', 'stopped', 'stopping'}:
            position, slots = None, []
        result.update(proposal_generation=position, open_slots=slots)
        # Existing immutable runtime identity lets the UI distinguish evaluations
        # made under different engine/connectome versions without new storage.
        result['evaluation_context'] = result.pop('runtime_hash')
        result['model_profile'] = self.store.fly(spec.founder_id)['spec'].get('model_profile','malecns-lif-cpu-v1')
        return result

    def list(self,owner):
        with self.store.db() as db:
            ids=[r[0] for r in db.execute('SELECT id FROM training_runs WHERE owner=? ORDER BY created DESC LIMIT 40',(owner,))]
        return [self.get(i) for i in ids]

    def publish(self,ident,owner):
        with self.store.db() as db:
            row=db.execute('SELECT status FROM training_runs WHERE id=? AND owner=?',(ident,owner)).fetchone()
            if row is None:raise ValueError('Training session not found')
            if row['status']!='complete':raise ValueError('Only completed sessions can be published')
            db.execute('INSERT OR IGNORE INTO training_publications VALUES(?,?)',(ident,time.time()))
        return self.showcase(ident)

    def showcase(self,ident=None):
        with self.store.db() as db:
            ids=[r[0] for r in db.execute('SELECT run_id FROM training_publications ORDER BY published DESC LIMIT 40')]
        if ident is None:return [self.showcase(i) for i in ids]
        with self.store.db() as db:
            if not db.execute('SELECT 1 FROM training_publications WHERE run_id=?',(ident,)).fetchone():return None
        # Publishing explicitly shares designs, lineage, scores and replay links.
        # Strip account identifiers and operational fields at every nested level.
        def public(value):
            if isinstance(value,dict):
                return {k:public(v) for k,v in value.items() if k not in
                        {'owner','designer','control','error','experiment_error','lease','expires','runtime_hash'}}
            if isinstance(value,list):return [public(v) for v in value]
            return value
        return public(self.get(ident))

    def control(self,ident,owner,action):
        if action not in {'pause','resume','stop'}:raise ValueError('Unknown training action')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM training_runs WHERE id=? AND owner=?',(ident,owner)).fetchone()
            if row is None:raise ValueError('Training session not found')
            if row['status'] in {'complete','failed','stopped'} or row['control']=='stop':raise ValueError('Training session is already terminal')
            control={'resume':'run','pause':'pause','stop':'stop'}[action]
            db.execute('UPDATE training_runs SET control=?,updated=? WHERE id=?',(control,time.time(),ident))
        return self.get(ident)

    def save(self,ident,owner,fly_id):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            member=db.execute('SELECT m.* FROM training_members m JOIN training_runs r ON r.id=m.run_id WHERE r.id=? AND r.owner=? AND m.fly_id=?',(ident,owner,fly_id)).fetchone()
            if member is None:raise ValueError('Training individual not found')
            if member['fitness'] is None:raise ValueError('Finish evaluating the individual before saving it')
            if not member['saved'] and db.execute("SELECT count(*) FROM flies f WHERE owner=? AND NOT EXISTS(SELECT 1 FROM training_members m WHERE m.fly_id=f.id AND m.saved=0)",(owner,)).fetchone()[0]>=100:
                raise ValueError('This workspace allows 100 published flies per designer')
            db.execute('UPDATE training_members SET saved=1 WHERE run_id=? AND fly_id=?',(ident,fly_id))
        return self.store.fly(fly_id)

    def propose(self, ident, owner, proposal, *, agent_channel=False):
        proposal = ProposedCandidate.model_validate(proposal)
        spec = proposal.spec.model_dump(by_alias=True)
        position = (ident, proposal.generation, proposal.slot)
        with self.store.db() as db:
            prior = check_proposal(db, owner, position, spec)
        if prior:
            return self.store.fly(prior)
        report = self.compiler().compile(proposal.spec, publish=True, root=self.store.root)
        return self.store.add_fly(owner, spec, report, submission_channel='api',
                                  training=position, external_proposal=True, agent_channel=agent_channel)

    def _candidate(self,run,spec,generation,slot,parent,members=()):
        compiler=self.compiler()
        raw=dict(parent['spec']);raw['parent_id']=parent['id']
        raw['name']=f"{spec.name[:42]} · G{generation+1}.{slot+1}"
        if slot == 0:
            candidate = FlySpec.model_validate(raw)
            report = compiler.compile(candidate, publish=True, root=self.store.root)
            return self.store.add_fly(run['owner'], candidate.model_dump(by_alias=True), report,
                                       training=(run['id'], generation, slot))
        rng=np.random.default_rng(np.random.SeedSequence([spec.seed,generation,slot]))
        scales={}
        for mutation in raw['weight_mutations']:
            scales[mutation['selector']]=scales.get(mutation['selector'],1.)*mutation['scale']
        # Slot zero is the retained parent, so every generation has an incumbent.
        perturb={c:float(rng.normal(0,spec.mutation_strength)) for c in spec.circuits} if spec.strategy!='cross_entropy' else {}
        if spec.strategy=='cross_entropy':
            # Diagonal Gaussian CEM in log-weight space, with elite retention.
            # Rebuild its smoothed distribution from completed generations so a
            # restart needs no hidden optimizer state. Alpha=.7, elite fraction=.5.
            def vector(fly):
                values={c:0. for c in spec.circuits}
                for mutation in fly['spec']['weight_mutations']:
                    if mutation['selector'] in values:values[mutation['selector']]+=math.log(mutation['scale'])
                return np.array([values[c] for c in spec.circuits])
            mean=vector(self.store.fly(spec.founder_id))
            sigma=np.full(len(mean),spec.mutation_strength)
            for previous in range(generation):
                ranked=sorted((m for m in members if m['generation']==previous and m['fitness'] is not None),
                              key=lambda m:(-m['fitness'],m['slot']))
                if len(ranked)!=spec.population:raise ValueError('CEM needs a fully evaluated previous generation')
                elite=np.array([vector(m['fly']) for m in ranked[:max(1,math.ceil(spec.population*.5))]])
                mean=.3*mean+.7*elite.mean(axis=0)
                sigma=np.maximum(.01,.3*sigma+.7*elite.std(axis=0))
            target=rng.normal(mean,sigma)
            perturb={c:float(target[i]-math.log(scales.get(c,1.))) for i,c in enumerate(spec.circuits)}
        original=compiler.compile(FlySpec.model_validate(raw))['artifact_id']
        for shrink in range(9):
            values=dict(scales)
            for circuit,delta in perturb.items():values[circuit]=float(np.clip(scales.get(circuit,1.)*math.exp(delta*.5**shrink),.5,2.))
            raw['weight_mutations']=[{'selector':c,'scale':v} for c,v in sorted(values.items()) if abs(v-1)>1e-12]
            candidate=FlySpec.model_validate(raw)
            try:report=compiler.compile(candidate)
            except ValueError:
                if not perturb:raise
                continue
            if slot and report['artifact_id']==original:continue
            report=compiler.compile(candidate,publish=True,root=self.store.root)
            return self.store.add_fly(run['owner'],candidate.model_dump(),report,submission_channel='web',training=(run['id'],generation,slot))
        raise ValueError('No legal mutation fits this design. Reduce existing edits or choose other circuits.')

    def tick(self):
        # One lightweight coordinator per workspace; simulations remain ordinary jobs.
        with (self.store.root/'training-controller.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            with self.store.db() as db:
                rows=[dict(r) for r in db.execute("SELECT * FROM training_runs WHERE status NOT IN ('complete','stopped','failed') ORDER BY updated")]
            for run in rows:
                try:self._advance(run)
                except Exception as exc:
                    with self.store.db() as db:db.execute("UPDATE training_runs SET status='failed',error=?,updated=? WHERE id=?",(str(exc),time.time(),run['id']))

    def _advance(self,run):
        spec=TrainingSpec.model_validate_json(run['spec']);detail=self.get(run['id'])
        members=detail['members']
        for member in members:
            matches=member['matches']
            if any(m['status']=='failed' for m in matches):
                raise ValueError('Evaluation failed: '+next(m['error'] or m['id'] for m in matches if m['status']=='failed'))
            if member['fitness'] is None and len(matches)==spec.trials and all(m['status']=='verified' for m in matches):
                # Equal weight per complete condition; contest conditions each
                # contain the two mirrored positions, never a partial pair.
                scores=[r['fitness'] for r in member['condition_results']]
                if any(score is None for score in scores):raise ValueError('Non-finite evaluation score')
                member['fitness']=sum(scores)/len(scores)
                with self.store.db() as db:db.execute('UPDATE training_members SET fitness=? WHERE run_id=? AND generation=? AND slot=?',(member['fitness'],run['id'],member['generation'],member['slot']))
        # Read control again: a user may pause while compilation/recording is in flight.
        with self.store.db() as db:control=db.execute('SELECT control FROM training_runs WHERE id=?',(run['id'],)).fetchone()[0]
        pending=any(m['status'] in {'queued','running'} for member in members for m in member['matches'])
        if control!='run':
            if control=='stop' and not pending:
                with self.store.db() as db:db.execute("UPDATE training_runs SET status='stopped',updated=? WHERE id=?",(time.time(),run['id']))
            return
        if pending:return
        generation=max((m['generation'] for m in members),default=0)
        current=[m for m in members if m['generation']==generation]
        if len(current)==spec.population and all(m['fitness'] is not None for m in current):
            generation+=1;current=[]
        if generation>=spec.generations:
            with self.store.db() as db:db.execute("UPDATE training_runs SET status='complete',updated=? WHERE id=?",(time.time(),run['id']))
            return
        if spec.strategy == 'external':
            if generation == 0 and not any(m['slot'] == 0 for m in current):
                self._candidate(run, spec, 0, 0, self.store.fly(spec.founder_id))
                return
            if not any(m['fitness'] is None for m in current):
                with self.store.db() as db:
                    db.execute("UPDATE training_runs SET status='awaiting_candidates' WHERE id=?", (run['id'],))
                return
        elif len(current)<spec.population:
            parent=self.store.fly(spec.founder_id)
            if generation and spec.strategy in {'evolution','cross_entropy'}:
                previous=[m for m in members if m['generation']==generation-1]
                parent=max(previous,key=lambda m:(m['fitness'],-m['slot']))['fly']
            self._candidate(run,spec,generation,len(current),parent,members)
            return
        member=next(m for m in current if m['fitness'] is None)
        trial=len(member['matches']);ids=[member['fly_id']]
        condition=spec.conditions[trial//spec.positions_per_condition]
        position=trial%spec.positions_per_condition
        if spec.mode=='contest':ids=[member['fly_id'],spec.opponent_id] if position==0 else [spec.opponent_id,member['fly_id']]
        request=MatchRequest(fly_ids=ids,map_id=condition.map_id,mode=spec.mode,seed=condition.seed,duration_seconds=spec.duration_seconds,bridge_profile=spec.bridge_profile).model_dump()
        # Admission checks the control flag again within the same DB transaction.
        match=self.store.add_match(run['owner'],request,run['runtime_hash'],training=(run['id'],generation,member['slot'],trial))
        if match:
            with self.store.db() as db:db.execute("UPDATE training_runs SET status='running',updated=? WHERE id=?",(time.time(),run['id']))
