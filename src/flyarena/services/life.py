"""Life records project existing facts; researcher interpretations are append-only."""
from __future__ import annotations

import json
import math
import time
import uuid
from typing import Literal
from pydantic import Field, model_validator
from ..contracts import StrictModel


class LifeNote(StrictModel):
    action: Literal['retain','investigate','stop_exploring','hypothesis','correction']
    reason: str = Field(min_length=1,max_length=2000)
    match_id: str | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')
    supersedes: str | None = Field(default=None,pattern=r'^[0-9a-f]{32}$')

    @model_validator(mode='after')
    def meaningful(self):
        if not self.reason.strip():raise ValueError('Explain your interpretation or decision')
        if self.action=='correction' and not self.supersedes:raise ValueError('Choose the note being corrected')
        if self.supersedes and self.action!='correction':raise ValueError('Only corrections can reference an earlier note')
        return self


class LifeLedger:
    def __init__(self,store):
        self.store=store
        with store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS life_notes(
                id TEXT PRIMARY KEY,fly_id TEXT NOT NULL,owner TEXT NOT NULL,
                action TEXT NOT NULL,reason TEXT NOT NULL,match_id TEXT,supersedes TEXT,
                created REAL NOT NULL,request_key TEXT NOT NULL,
                UNIQUE(owner,request_key))''')
            db.execute('CREATE INDEX IF NOT EXISTS life_note_fly ON life_notes(fly_id,created)')

    def visible(self,ident,owner=None):
        with self.store.db() as db:
            return db.execute('''SELECT 1 FROM flies f WHERE f.id=? AND (
                f.owner=? OR NOT EXISTS(SELECT 1 FROM training_members m WHERE m.fly_id=f.id AND m.saved=0)
                OR EXISTS(SELECT 1 FROM training_members m JOIN training_publications p ON p.run_id=m.run_id WHERE m.fly_id=f.id))''',
                (ident,owner)).fetchone() is not None

    def listing(self,owner=None):
        with self.store.db() as db:
            rows=db.execute('''SELECT f.id FROM flies f WHERE f.owner=?
                OR NOT EXISTS(SELECT 1 FROM training_members m WHERE m.fly_id=f.id AND m.saved=0)
                OR EXISTS(SELECT 1 FROM training_members m JOIN training_publications p ON p.run_id=m.run_id WHERE m.fly_id=f.id)
                ORDER BY f.created DESC LIMIT 200''',(owner,)).fetchall()
        return [self.card(r[0],owner) for r in rows]

    def card(self,ident,owner=None):
        fly=self.store.fly(ident)
        return {'id':ident,'name':fly['name'],'color':fly['color'],'parent_id':fly['spec']['parent_id'],
                'created':fly['created'],'reference_kind':fly['reference_kind'],'can_annotate':fly['owner']==owner}

    def visible_match(self,match,owner):
        with self.store.db() as db:
            row=db.execute('SELECT run_id FROM training_evaluations WHERE match_id=?',(match['id'],)).fetchone()
            if not row:return True
            return db.execute('''SELECT 1 FROM training_runs r WHERE r.id=? AND
                (r.owner=? OR EXISTS(SELECT 1 FROM training_publications p WHERE p.run_id=r.id))''',(row[0],owner)).fetchone() is not None

    def get(self,ident,owner=None):
        if not self.visible(ident,owner):return None
        fly=self.store.fly(ident);can_annotate=fly['owner']==owner
        fly.pop('owner',None);fly.pop('designer',None)
        with self.store.db() as db:
            origin=db.execute('''SELECT r.*,m.generation,m.slot,m.fitness,m.saved FROM training_members m
                JOIN training_runs r ON r.id=m.run_id WHERE m.fly_id=?''',(ident,)).fetchone()
            match_ids=[r[0] for r in db.execute('''SELECT m.id FROM matches m
                WHERE EXISTS(SELECT 1 FROM json_each(m.request,'$.fly_ids') j WHERE j.value=?)
                ORDER BY m.created DESC LIMIT 100''',(ident,))]
            children=[r[0] for r in db.execute("SELECT id FROM flies WHERE json_extract(spec,'$.parent_id')=? ORDER BY created LIMIT 100",(ident,))]
            notes=[dict(r) for r in db.execute('SELECT id,action,reason,match_id,supersedes,created FROM life_notes WHERE fly_id=? ORDER BY created,id',(ident,))]
            if origin and origin['owner']!=owner and not db.execute('SELECT 1 FROM training_publications WHERE run_id=?',(origin['id'],)).fetchone():origin=None
        experiences=[]
        for mid in match_ids:
            match=self.store.match(mid)
            if not self.visible_match(match,owner):continue
            match.pop('owner',None);runtime=match.pop('runtime_hash',None)
            slots=[i for i,f in enumerate(match['request']['fly_ids']) if f==ident]
            experiences.append({'match':match,'slots':slots,'evaluation_context':runtime,
                                'scores':[match['result']['scores'][i] for i in slots] if match['status']=='verified' else None})
        visible_ids={e['match']['id'] for e in experiences}
        for note in notes:
            mid=note['match_id']
            if mid and mid not in visible_ids:
                linked=self.store.match(mid)
                if linked and self.visible_match(linked,owner):visible_ids.add(mid)
        # Notes may predate publication of a candidate. Never disclose linked
        # private experiences through a subsequently saved/public fly.
        notes=[n for n in notes if n['match_id'] is None or n['match_id'] in visible_ids]
        # Every correction must retain its visible predecessor, including chains.
        visible_notes=[];note_ids=set()
        for note in notes:
            if note['supersedes'] is None or note['supersedes'] in note_ids:
                visible_notes.append(note);note_ids.add(note['id'])
        notes=visible_notes
        ancestors=[];parent=fly['spec']['parent_id'];seen={ident}
        while parent and parent not in seen and len(ancestors)<24 and self.visible(parent,owner):
            seen.add(parent);card=self.card(parent,owner);ancestors.append(card);parent=card['parent_id']
        origin_info=None
        if origin:
            plan=json.loads(origin['spec'])
            origin_info={'run_id':origin['id'],'strategy':plan['strategy'],'optimizer_name':plan.get('optimizer_name',''),
                         'round':origin['generation']+1,'slot':origin['slot'],'fitness':origin['fitness'],'saved':bool(origin['saved']),
                         'evaluation_context':origin['runtime_hash'],'plan':plan}
        return {'fly':fly,'can_annotate':can_annotate,'origin':origin_info,'ancestors':ancestors,
                'descendants':[self.card(c,owner) for c in children if self.visible(c,owner)],
                'experiences':experiences,'notes':notes,
                'limits':{'experiences':100,'descendants':100,'ancestors':24},
                'learning':{'birth_spec':True,'within_match_plasticity':fly['spec']['plasticity'],
                            'acquired_state_inherited':False},
                'interpretation':'Scores apply only to their recorded conditions. Notes are researcher statements, not automatic qualification.'}

    def annotate(self,ident,owner,note,key):
        note=LifeNote.model_validate(note)
        if not key or len(key)>128:raise ValueError('Provide an Idempotency-Key of at most 128 characters')
        fly=self.store.fly(ident)
        if fly is None or fly['owner']!=owner:raise ValueError('Only the designer can annotate this fly')
        if note.match_id:
            match=self.store.match(note.match_id)
            if not match or ident not in match['request']['fly_ids'] or not self.visible_match(match,owner):
                raise ValueError('Choose an accessible experience of this fly')
            # A public note must never leak a private training experience ID.
            if self.visible(ident) and not self.visible_match(match,None):
                raise ValueError('Publish that training trajectory before linking it from a public note')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT * FROM life_notes WHERE owner=? AND request_key=?',(owner,key)).fetchone()
            if prior:
                if prior['fly_id']!=ident or any(prior[k]!=v for k,v in note.model_dump().items()):raise ValueError('Idempotency key already used for another note')
                return prior['id']
            if note.supersedes and not db.execute('SELECT 1 FROM life_notes WHERE id=? AND fly_id=? AND owner=?',(note.supersedes,ident,owner)).fetchone():
                raise ValueError('Correction must reference your earlier note on this fly')
            if db.execute('SELECT count(*) FROM life_notes WHERE fly_id=?',(ident,)).fetchone()[0]>=200:
                raise ValueError('This fly has reached the 200-note limit')
            nid=uuid.uuid4().hex
            db.execute('INSERT INTO life_notes VALUES(?,?,?,?,?,?,?,?,?)',
                       (nid,ident,owner,note.action,note.reason,note.match_id,note.supersedes,time.time(),key))
        return nid

    def observation(self,ident,mid,owner=None):
        if not self.visible(ident,owner):return None
        match=self.store.match(mid)
        if not match or ident not in match['request']['fly_ids'] or not self.visible_match(match,owner):return None
        if match['status']!='verified':return {'status':match['status'],'observations':None}
        folder=self.store.result_folder(match)
        try:
            frames=json.loads((folder/'frames.json').read_text());events=json.loads((folder/'events.json').read_text())
            receipt=json.loads((folder/'receipt.json').read_text())
        except (OSError,ValueError):return {'status':'evidence_unavailable','observations':None}
        if not frames:return {'status':'evidence_unavailable','observations':None}
        observations=[]
        dt=receipt['runtime']['rules']['physics_dt']
        for slot in [i for i,f in enumerate(match['request']['fly_ids']) if f==ident]:
            intake=[e for e in events if e['type']=='intake' and e['slot']==slot]
            exits=[e for e in events if e['type']=='exit' and e['slot']==slot]
            path=sum(math.dist(a['positions'][slot],b['positions'][slot]) for a,b in zip(frames,frames[1:]))
            food=sum(e['amount'] for e in intake)
            observations.append({'slot':slot,'model_profile':self.store.fly(ident)['spec'].get('model_profile','malecns-lif-cpu-v1'),'food_consumed':food,'food_outcome':'no_intake_observed' if not intake else 'intake_observed',
                'first_intake_record_seconds':min((e['tick']*dt for e in intake),default=None),
                'exit_seconds':min((e['tick']*dt for e in exits),default=None),
                'sampled_path_mm':path,'final_energy':frames[-1].get('energy',[None]*len(match['request']['fly_ids']))[slot],
                'total_spikes':receipt.get('total_spikes',[None]*len(match['request']['fly_ids']))[slot],
                'final_neural_activity':frames[-1].get('traces',[None]*len(match['request']['fly_ids']))[slot]})
        return {'status':'recorded','observations':observations,'duration_seconds':frames[-1]['time'],
                'frame_count':len(frames),'receipt':f'/api/v1/matches/{mid}/receipt',
                'limitations':['first_intake_is_event_batch_time','path_is_sampled_thorax_motion','mouth_distance_not_recorded']}
