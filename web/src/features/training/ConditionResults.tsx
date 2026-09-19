import {BehaviorFitness} from './BehaviorFitness'
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
    {result.fitness===0&&result.matches.some(match=>match.request?.mode==='contest')&&<p className="training-hint">{locale==='zh-CN'?'零分表示两个出生位置的平均优势为零，不代表双方都没有摄取。请查看各场、各只果蝇的实际记录。':'Zero means no average advantage across both spawn positions; it does not mean neither fly fed. Inspect each match and participant.'}</p>}
    {result.matches.map((match,position)=><div key={match.id}><button className="text-link" disabled={match.status!=='verified'} onClick={()=>onReplay(match)}><Play size={12}/>{t('Behavior and neural replay')} {position+1} · {match.status==='running'?`${Math.round(match.progress*100)}%`:t(match.status==='verified'?'Replay':match.status==='queued'?'Queued':'Failed')}</button>{match.result?.behavior?.map((metric,slot)=><div key={slot}>{metric&&<small>{t('Slot')} {slot+1}</small>}<BehaviorFitness metric={metric}/></div>)}</div>)}
  </section>)}</div>
}
