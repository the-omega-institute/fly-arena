import {ArrowRight,Leaf} from 'lucide-react'
import type {Fly} from '../../types'
import {useI18n} from '../../shared/i18n'
import {wildTypeChallenge} from './wildtype'

export function WildTypeChallenge({flies,selected,onPrepare}:{flies:Fly[];selected:string;onPrepare:(plan:NonNullable<ReturnType<typeof wildTypeChallenge>>)=>void}) {
  const {t}=useI18n(),plan=wildTypeChallenge(flies,selected)
  return <section className="wt-challenge" aria-label={t('WT comparison challenge')}>
    <div><Leaf size={18}/><strong>{t('Start with a fair comparison')}</strong></div>
    <p>{t('WT is the unmodified simulated baseline. Compete against it to see what your design changes.')}</p>
    {plan?<p className="wt-participants"><b>{plan.subject.name}</b> vs <b>{plan.reference.name}</b></p>:<p>{t('Choose a different saved fly. The WT reference must use the same connectome and neural model.')}</p>}
    <button className="secondary wide" disabled={!plan} onClick={()=>{if(plan)onPrepare(plan)}}><Leaf size={15}/>{t('Prepare WT challenge')}<ArrowRight size={15}/></button>
    <small>{t('Preset: orchard · seed 42 · 2 seconds per match. Review the plan, then create the paired series: two swapped matches, 4 simulated seconds total.')}</small>
  </section>
}
