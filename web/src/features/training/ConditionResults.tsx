import {Play} from 'lucide-react'
import type {ArenaMap,Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import type {EvaluationCondition} from './comparison'

export type ConditionResult={condition:EvaluationCondition;fitness:number|null;evaluations_completed:number;evaluations_total:number;matches:Match[]}

export function ConditionResults({results,maps,onReplay}:{results:ConditionResult[];maps:ArenaMap[];onReplay:(match:Match)=>void}){
  const {t,locale}=useI18n()
  return <div className="condition-results">{results.map((result,index)=><section key={index}>
    <div className="condition-heading"><strong>{t('Condition')} {index+1} · {maps.find(m=>m.id===result.condition.map_id)?.[locale==='en'?'english':'name']||result.condition.map_id}</strong><span>{result.fitness===null?'—':result.fitness.toFixed(3)}</span></div>
    <small>{t('Seed')} {result.condition.seed} · {result.evaluations_completed}/{result.evaluations_total} {t('evaluated')}{result.fitness===null?' · '+t('Awaiting complete condition'):''}</small>
    {result.matches.map((match,position)=><button className="text-link" key={match.id} disabled={match.status!=='verified'} onClick={()=>onReplay(match)}><Play size={12}/>{t('Behavior and neural replay')} {position+1} · {match.status==='running'?`${Math.round(match.progress*100)}%`:t(match.status==='verified'?'Replay':match.status==='queued'?'Queued':'Failed')}</button>)}
  </section>)}</div>
}
