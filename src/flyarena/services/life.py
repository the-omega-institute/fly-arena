"""Life records project existing facts; researcher interpretations are append-only."""
from __future__ import annotations

import json
from collections import Counter
import hashlib
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
            present=db.execute('''SELECT 1 FROM flies f WHERE f.id=? AND (
                f.owner=? OR NOT EXISTS(SELECT 1 FROM training_members m WHERE m.fly_id=f.id AND m.saved=0)
                OR EXISTS(SELECT 1 FROM training_members m JOIN training_publications p ON p.run_id=m.run_id WHERE m.fly_id=f.id))''',
                (ident,owner)).fetchone() is not None
            exists=db.execute('SELECT 1 FROM flies WHERE id=?',(ident,)).fetchone() is not None
        # A bundle must never make a private database record public by ID collision.
        return present if exists else self.store.published_fly(ident) is not None

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
                'created':fly['created'],'reference_kind':fly['reference_kind'],'can_annotate':owner is not None and fly['owner']==owner}

    def visible_match(self,match,owner):
        with self.store.db() as db:
            row=db.execute('SELECT run_id FROM training_evaluations WHERE match_id=?',(match['id'],)).fetchone()
            if not row:return True
            return db.execute('''SELECT 1 FROM training_runs r WHERE r.id=? AND
                (r.owner=? OR EXISTS(SELECT 1 FROM training_publications p WHERE p.run_id=r.id))''',(row[0],owner)).fetchone() is not None

    def get(self,ident,owner=None):
        if not self.visible(ident,owner):return None
        fly=self.store.fly(ident);can_annotate=owner is not None and fly['owner']==owner
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
        from .training import TrainingService
        training=TrainingService(self.store,None)
        public_matches={m['id']:m for m in training.gallery_matches()+training.bundled_replay_matches()
                        if ident in m.get('request',{}).get('fly_ids',[])}
        match_ids+= [mid for mid in public_matches if mid not in match_ids]
        experiences=[]
        for mid in match_ids:
            match=self.store.match(mid) or public_matches.get(mid)
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
        if origin_info is None and fly.get('source',{}).get('kind')=='published-training':
            source=fly['source'];plan=source['plan']
            origin_info={'run_id':source['run_id'],'strategy':plan['strategy'],'optimizer_name':plan.get('optimizer_name',''),
                         'round':source['generation']+1,'slot':source['slot'],'fitness':source['fitness'],'saved':False,
                         'evaluation_context':source['evaluation_context'],'plan':plan}
        return {'fly':fly,'can_annotate':can_annotate,'origin':origin_info,'ancestors':ancestors,
                'descendants':[self.card(c,owner) for c in children if self.visible(c,owner)],
                'experiences':experiences,'notes':notes,
                'limits':{'experiences':100,'descendants':100,'ancestors':24},
                'learning':{'birth_spec':True,'within_match_plasticity':fly['spec']['plasticity'],
                            'acquired_state_inherited':False},
                'interpretation':'Scores apply only to their recorded conditions. Notes are researcher statements, not automatic qualification.'}

    def _lineage_children(self, ident):
        """Return child ids from the immutable FlySpec parent links.

        Bundled gallery snapshots are read as public source records in the same
        way as bundled replays.  There is deliberately no second lineage table.
        """
        children=[]
        with self.store.db() as db:
            children.extend(r[0] for r in db.execute(
                "SELECT id FROM flies WHERE json_extract(spec,'$.parent_id')=? ORDER BY created,id LIMIT 51", (ident,)))
        from .training import TrainingService
        for run in TrainingService(self.store,None)._bundled_showcase():
            for member in run.get('members',[]):
                sample=member.get('fly') or {}
                if member.get('fly_id') and sample.get('spec',{}).get('parent_id')==ident:
                    children.append(member['fly_id'])
        return list(dict.fromkeys(children))[:51]

    def _lineage_generation(self, ident, owner):
        with self.store.db() as db:
            rows=db.execute('''SELECT r.id,m.generation,m.slot,m.fitness,m.saved,r.spec,r.owner
                FROM training_members m JOIN training_runs r ON r.id=m.run_id
                WHERE m.fly_id=? ORDER BY r.created DESC LIMIT 8''',(ident,)).fetchall()
        for row in rows:
            if row['owner'] != owner:
                with self.store.db() as db:
                    if not db.execute('SELECT 1 FROM training_publications WHERE run_id=?',(row['id'],)).fetchone():
                        continue
            plan=json.loads(row['spec'])
            round_number=row['generation']+1
            return {'generation':round_number,'generation_index':row['generation'],
                    'search_round':round_number if plan.get('strategy')=='random_search' else None,
                    'run_id':row['id'],'slot':row['slot'],'fitness':row['fitness'],'saved':bool(row['saved'])}
        fly=self.store.fly(ident)
        source=fly.get('source') if fly else None
        if source and source.get('generation') is not None:
            round_number=source['generation']+1
            plan=source.get('plan') or {}
            return {'generation':round_number,'generation_index':source['generation'],
                    'search_round':round_number if plan.get('strategy')=='random_search' else None,
                    'run_id':source.get('run_id'),'slot':source.get('slot'),'fitness':source.get('fitness'),
                    'saved':False}
        return None

    @staticmethod
    def _design_delta(child, parent, parent_id=None):
        """Summarize absolute FlySpecs relative to their recorded parent."""
        if parent is None:
            return {'relative_to_parent':None,'changed':False,'changed_circuits':[],
                    'changed_parameters':[],'edge_changes':{'count':0,'edges':[]},
                    'intervention_changes':{'count':0,'items':[]},
                    'code':'founder',
                    'summary':'Founder design; no parent design was recorded.'}
        changed_circuits=[];circuit_scales=[]
        # Preserve every occurrence: the compiler adds each log multiplier.
        def circuit_lists(spec):
            result={}
            for mutation in spec.get('weight_mutations',[]):
                result.setdefault(mutation['selector'],[]).append(mutation['scale'])
            return result
        parent_mut=circuit_lists(parent);child_mut=circuit_lists(child)
        for selector in sorted(set(parent_mut)|set(child_mut)):
            before_scales=parent_mut.get(selector,[]);after_scales=child_mut.get(selector,[])
            before=math.prod(before_scales);after=math.prod(after_scales)
            if before_scales != after_scales:
                changed_circuits.append(selector)
                circuit_scales.append({'selector':selector,'parent':before,'child':after,'delta':after-before,
                                       'parent_scales':before_scales,'child_scales':after_scales})
        changed_parameters=[]
        for name in ('tau_scale','threshold_shift_mv'):
            before=parent.get('neuron_parameters',{}).get(name,1.0 if name=='tau_scale' else 0.0)
            after=child.get('neuron_parameters',{}).get(name,1.0 if name=='tau_scale' else 0.0)
            if before != after:changed_parameters.append({'name':name,'parent':before,'child':after,'delta':after-before})
        parent_edges={d['edge']:d['log_delta'] for d in parent.get('edge_deltas',[])}
        child_edges={d['edge']:d['log_delta'] for d in child.get('edge_deltas',[])}
        edge_changes=[]
        for edge in sorted(set(parent_edges)|set(child_edges)):
            before=parent_edges.get(edge,0.0);after=child_edges.get(edge,0.0)
            if before != after:edge_changes.append({'edge':edge,'parent':before,'child':after,'delta':after-before})
        def interventions(spec):
            return Counter(json.dumps(v,sort_keys=True,separators=(',',':')) for v in spec.get('interventions',[]))
        parent_interventions=interventions(parent);child_interventions=interventions(child)
        intervention_items=[]
        for key in sorted(set(parent_interventions)|set(child_interventions)):
            before=parent_interventions[key];after=child_interventions[key]
            if before != after:
                intervention_items.append({'parent':json.loads(key) if before else None,
                                           'child':json.loads(key) if after else None,
                                           'parent_count':before,'child_count':after})
        design_changes=[]
        for name,default in (('model_profile','malecns-lif-cpu-v1'),('connectome_sha256',None),('plasticity','none')):
            before=parent.get(name,default);after=child.get(name,default)
            if before != after:design_changes.append({'name':name,'parent':before,'child':after})
        changed=bool(changed_circuits or changed_parameters or edge_changes or intervention_items or design_changes)
        return {'relative_to_parent':parent_id,'changed':changed,
                'changed_circuits':changed_circuits,'circuit_scales':circuit_scales,
                'changed_parameters':changed_parameters,'design_changes':design_changes,
                'edge_changes':{'count':len(edge_changes),'edges':edge_changes[:128]},
                'intervention_changes':{'count':len(intervention_items),'items':intervention_items[:64]},
                'code':'changed' if changed else 'unchanged',
                'summary':('Recorded changes relative to the parent FlySpec.' if changed else
                           'No design change relative to the parent FlySpec was recorded.')}

    def lineage(self, ident, owner=None, depth=3):
        """Return a bounded tree made solely from existing immutable records."""
        if not self.visible(ident,owner):return None
        depth=max(0,min(int(depth),6))
        root=self.store.fly(ident)
        if root is None:return None
        nodes=[];edges=[];seen=set();markers=set()
        def redacted_id(kind, anchor):
            digest=hashlib.sha256(f'{kind}:{anchor}'.encode()).hexdigest()[:16]
            return f'redacted:{kind}:{digest}'
        def add_marker(kind, anchor, omitted=None, relative_depth=None):
            marker_id=f'truncated:{kind}:{anchor}'
            if marker_id in seen:return marker_id
            seen.add(marker_id);markers.add(marker_id)
            nodes.append({'id':marker_id,'label':'More lineage…','marker':True,'truncated':True,
                          'direction':kind,'depth':relative_depth if relative_depth is not None else (0 if kind=='siblings' else (-1 if kind=='ancestors' else 1)),
                          'relation':kind,'omitted_count':omitted,'reference_kind':None,
                          'evaluation_conditions':[],'evaluation_results':[],'replay_links':[]})
            return marker_id
        def add_node(node_id, relation, relative_depth, *, redacted=False, anchor=None):
            if node_id in seen:return node_id
            seen.add(node_id)
            if redacted:
                node={'id':node_id,'label':'Private design','name':'Private design','redacted':True,
                      'marker':False,'relation':relation,'depth':relative_depth,'reference_kind':None,
                      'parent_id':None,'generation':None,'generation_index':None,'search_round':None,
                      'delta':None,'evaluation_conditions':[],'evaluation_results':[],'replay_links':[]}
                nodes.append(node);return node_id
            fly=self.store.fly(node_id)
            if fly is None:
                return add_node(redacted_id('missing',anchor or node_id),relation,relative_depth,redacted=True)
            generation=self._lineage_generation(node_id,owner)
            rec=self.get(node_id,owner)
            experiences=rec.get('experiences',[]) if rec else []
            parent_id=fly.get('spec',{}).get('parent_id')
            parent_visible=bool(parent_id and self.visible(parent_id,owner))
            parent=self.store.fly(parent_id) if parent_visible else None
            evaluations=[];replay_links=[]
            for experience in experiences:
                match=experience['match'];request=match.get('request') or {};result=match.get('result') or {}
                condition={'map_id':request.get('map_id'),'mode':request.get('mode'),'seed':request.get('seed'),
                           'duration_seconds':request.get('duration_seconds'),'bridge_profile':request.get('bridge_profile'),
                           'sensory_profile':request.get('sensory_profile')}
                evaluations.append({'match_id':match['id'],'condition':condition,'status':match.get('status'),
                                   'scores':experience.get('scores'),'result':result if match.get('status')=='verified' else None})
                replay_links.extend((f'/api/v1/matches/{match["id"]}',f'/api/v1/lives/{node_id}/experiences/{match["id"]}'))
            delta=(self._design_delta(fly.get('spec',{}),parent.get('spec',{}) if parent else None,parent_id)
                   if parent_visible or not parent_id else
                   {'relative_to_parent':None,'available':False,'changed':None,'changed_circuits':[],
                    'changed_parameters':[],'edge_changes':{'count':None,'edges':[]},
                    'intervention_changes':{'count':None,'items':[]},
                    'code':'parent_unavailable',
                    'summary':'Parent design is private; the relative delta is unavailable.'})
            node={'id':node_id,'label':fly.get('name') or node_id,'name':fly.get('name') or node_id,
                  'redacted':False,'marker':False,'relation':relation,'depth':relative_depth,
                  'parent_id':parent_id if parent_visible else None,'parent_visible':parent_visible,
                  'reference_kind':fly.get('reference_kind'),'generation':generation.get('generation') if generation else None,
                  'generation_index':generation.get('generation_index') if generation else None,
                  'search_round':generation.get('search_round') if generation else None,
                  'training':generation,
                  'delta':delta,'design_delta':delta,'parent_relative_delta':delta,
                  'evaluation_conditions':[e['condition'] for e in evaluations],
                  'evaluation_results':evaluations,'evaluation':{'conditions':[e['condition'] for e in evaluations],'results':evaluations},
                  'replay_links':replay_links,'replays':replay_links,
                  'match_ids':[e['match_id'] for e in evaluations]}
            nodes.append(node);return node_id
        def link(parent_id, child_id, relation):
            if parent_id==child_id:return
            edge={'from':parent_id,'to':child_id,'relation':relation}
            if edge not in edges:edges.append(edge)
        add_node(ident,'center',0)
        # Construct links nearest-first; visual ordering must not reverse ancestry.
        ancestor_ids=[];current=root.get('spec',{}).get('parent_id');steps=0
        # The immediate parent is also needed to anchor siblings at depth zero.
        while current and steps<max(1,depth):
            if self.visible(current,owner):ancestor_ids.append((current,-steps-1))
            else:ancestor_ids.append((redacted_id('ancestor',current), -steps-1))
            current_fly=self.store.fly(current)
            current=current_fly.get('spec',{}).get('parent_id') if current_fly else None
            steps+=1
        previous=ident
        for ancestor,relative_depth in ancestor_ids:
            add_node(ancestor,'ancestor',relative_depth,redacted=ancestor.startswith('redacted:'),anchor=ident)
            link(ancestor,previous,'parent')
            previous=ancestor
        if current:
            marker=add_marker('ancestors',ident,relative_depth=-steps-1)
            link(marker,previous,'ancestor')
        # Siblings share the selected individual's parent. Private siblings are
        # represented without their id, name, owner, or design details.
        parent_id=root.get('spec',{}).get('parent_id')
        if parent_id:
            siblings=[child for child in self._lineage_children(parent_id) if child!=ident]
            if len(siblings)>50:
                visible_siblings=siblings[:50];omitted=len(siblings)-50
            else:visible_siblings=siblings;omitted=0
            sibling_parent=parent_id if self.visible(parent_id,owner) else redacted_id('ancestor',parent_id)
            if sibling_parent not in seen:
                add_node(sibling_parent,'ancestor',-1,redacted=sibling_parent.startswith('redacted:'),anchor=ident)
            link(sibling_parent,ident,'parent')
            for sibling in visible_siblings:
                if self.visible(sibling,owner):
                    add_node(sibling,'sibling',0);link(sibling_parent,sibling,'sibling')
                else:
                    private=redacted_id('sibling',ident+sibling)
                    add_node(private,'sibling',0,redacted=True);link(sibling_parent,private,'sibling')
            if omitted:add_marker('siblings',ident,omitted)
        # Descendant breadth is bounded at each branch; the depth query is the
        # only source of truncation, so the response cannot grow unboundedly.
        frontier=[(ident,0)]
        max_nodes=200
        while frontier:
            parent_node,level=frontier.pop(0)
            children=self._lineage_children(parent_node)
            if not children:continue
            if level>=depth:
                add_marker('descendants',parent_node,len(children));link(parent_node,add_marker('descendants',parent_node,len(children)),'descendant');continue
            shown=children[:50];omitted=max(0,len(children)-50)
            for child in shown:
                if len(nodes)>=max_nodes:
                    marker=add_marker('descendants',parent_node,len(children));link(parent_node,marker,'descendant');break
                child_level=level+1
                if self.visible(child,owner):
                    add_node(child,'descendant',child_level);link(parent_node,child,'child');frontier.append((child,child_level))
                else:
                    private=redacted_id('descendant',parent_node+child)
                    add_node(private,'descendant',child_level,redacted=True);link(parent_node,private,'child')
            if omitted:
                marker=add_marker('descendants',parent_node,omitted);link(parent_node,marker,'descendant')
        # Ensure the center node is always present first for keyboard navigation
        # consumers while retaining a root-to-leaf visual order elsewhere.
        center=next(n for n in nodes if n['id']==ident)
        nodes=[center]+sorted((n for n in nodes if n is not center),key=lambda n:n['depth'])
        return {'center_id':ident,'depth':depth,'nodes':nodes,'edges':edges,
                'truncated':list(markers),'limits':{'depth':depth,'branch':50,'nodes':len(nodes)}}

    def annotate(self,ident,owner,note,key):
        note=LifeNote.model_validate(note)
        if not key or len(key)>128:raise ValueError('Provide an Idempotency-Key of at most 128 characters')
        fly=self.store.fly(ident)
        if owner is None or fly is None or fly['owner']!=owner:raise ValueError('Only the designer can annotate this fly')
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
        from .training import TrainingService
        training=TrainingService(self.store,None)
        local=self.store.match(mid)
        match=local or training.gallery_match(mid) or training.bundled_replay_match(mid)
        if not match or ident not in match['request']['fly_ids'] or not self.visible_match(match,owner):return None
        if match['status']!='verified':return {'status':match['status'],'observations':None}
        folder=self.store.result_folder(match)
        try:
            def artifact(name):
                if local:return folder/(name+'.json')
                path=training.bundled_replay_artifact(mid,name) or training.gallery_artifact(mid,name)
                if path is None:raise FileNotFoundError(name)
                return path
            frames=json.loads(artifact('frames').read_text());events=json.loads(artifact('events').read_text())
            receipt=json.loads(artifact('receipt').read_text())
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
