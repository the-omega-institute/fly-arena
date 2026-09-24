"""Conservative comparisons of recorded evaluations, never inferred performance."""
from __future__ import annotations

import json


CONDITIONS = ('map_id','seed','duration_seconds','bridge_profile','sensory_profile',
              'motor','runtime','mode','slots','opponents','silence_output')


def comparison_reasons(left, right):
    reasons=[]
    for field in CONDITIONS:
        a=left['condition'].get(field);b=right['condition'].get(field)
        if a is None or b is None:reasons.append({'field':field,'code':'missing'})
        elif a!=b:reasons.append({'field':field,'code':'different'})
    if left['status']!='verified' or right['status']!='verified':
        reasons.append({'field':'status','code':'unverified'})
    if left['scores'] is None or right['scores'] is None:
        reasons.append({'field':'scores','code':'missing'})
    return reasons


class LifeComparison:
    def __init__(self, ledger):
        self.ledger=ledger
        self.store=ledger.store

    def evaluations(self, record):
        from .training import TrainingService
        training=TrainingService(self.store,None)
        result=[]
        for experience in record['experiences'][:100]:
            match=experience['match'];request=match.get('request') or {}
            condition={key:request.get(key) for key in CONDITIONS[:5]}
            condition.update(motor=None,silence_output=None,runtime=experience.get('evaluation_context'),mode=request.get('mode'),
                             slots=experience['slots'],opponents=[fid for fid in request.get('fly_ids',[]) if fid!=record['fly']['id']])
            # Read frozen evidence, never the current runner's defaults or sources.
            try:
                local=self.store.match(match['id'])
                path=(self.store.result_folder(local)/'receipt.json' if local else
                      training.bundled_replay_artifact(match['id'],'receipt') or training.gallery_artifact(match['id'],'receipt'))
                receipt=json.loads(path.read_text()) if path else {}
                from ..common import digest
                bound=(match.get('result') or {}).get('receipt_sha256')
                valid=bool(bound and receipt.get('sha256')==bound and digest({k:v for k,v in receipt.items() if k!='sha256'})==bound)
                if valid and receipt.get('request')==request:
                    runtime=receipt.get('runtime') or {}
                    condition['runtime']=digest(runtime) if runtime else None
                    condition['silence_output']=receipt.get('silence_output')
                    profile=runtime.get('profile') or {}
                    # Legacy transfer is implemented in these pinned source files.
                    motor=receipt.get('observation_motor') or profile.get('hashes',{}).get('motor')
                    if motor is None and all(runtime.get('sources',{}).get(k) for k in ('runner.py','body.py')):
                        motor={k:runtime['sources'][k] for k in ('runner.py','body.py')}
                    condition['motor']=motor
            except (OSError,ValueError,TypeError,AttributeError):
                pass
            result.append({'match_id':match['id'],'condition':condition,'status':match['status'],
                           'scores':experience.get('scores') if match['status']=='verified' else None,
                           'error':match.get('error')})
        return result

    def get(self, ident, owner=None, *, relative=None, offset=0):
        record=self.ledger.get(ident,owner)
        if record is None:return None
        parent=record['fly']['spec'].get('parent_id')
        children=self.ledger._lineage_children(ident,offset=offset)
        relatives=[]
        if parent and self.ledger.visible(parent,owner):relatives.append(self.ledger.card(parent,owner)|{'relation':'parent'})
        relatives.extend(self.ledger.card(child,owner)|{'relation':'child'} for child in children[:50] if self.ledger.visible(child,owner))
        response={'center_id':ident,'relatives':relatives,'parent_unavailable':bool(parent and not self.ledger.visible(parent,owner)),
                  'next_offset':offset+50 if len(children)>50 else None,'comparison':None,'evaluation_limit':100}
        if relative is None:return response
        if not self.ledger.visible(relative,owner):return None
        other=self.ledger.get(relative,owner)
        is_parent=relative==parent
        if not is_parent and other['fly']['spec'].get('parent_id')!=ident:return None
        child_record,parent_record=(record,other) if is_parent else (other,record)
        left=self.evaluations(record);right=self.evaluations(other)
        # Emit every pairing as references, so no unmatched evaluation disappears.
        pairs=[{'left':i,'right':j,'reasons':comparison_reasons(a,b)}
               for i,a in enumerate(left) for j,b in enumerate(right)]
        response['comparison']={'relative':self.ledger.card(relative,owner),'relation':'parent' if is_parent else 'child',
            'delta':self.ledger._design_delta(child_record['fly']['spec'],parent_record['fly']['spec'],parent_record['fly']['id']),
            'left':left,'right':right,'pairs':pairs}
        return response
