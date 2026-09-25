import type {Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import {recordedDescriptorComparison,type RecordedDescriptorRecord} from './recordedDescriptors'

export type SignalMember={fly_id:string;matches:Match[]}
const labels={food:'Recorded food',latter_half_food:'Recorded second-half food',upright_fraction:'Recorded upright fraction',path_length_mm:'Recorded path length'} as const

export function recordedParentSignal(parentId:string|null|undefined,members:SignalMember[],matches:Match[]):SignalMember|undefined{
 if(!parentId)return undefined
 return members.find(member=>member.fly_id===parentId)||{fly_id:parentId,matches:matches.filter(match=>match.status==='verified'&&match.request?.fly_ids?.includes(parentId))}
}

export function EvolutionSignal({candidate,parent}:{candidate:SignalMember;parent?:SignalMember}){
 const {t}=useI18n()
 const comparison=parent?recordedDescriptorComparison(candidate.matches,candidate.fly_id,parent.matches,parent.fly_id):null
 const deltas=comparison?.deltas||[]
 const changed=deltas.filter(item=>Math.abs(item.delta)>1e-9)
 const format=(key:typeof deltas[number]['key'],value:number)=>key==='upright_fraction'?`${(value*100).toFixed(1)}%`:key==='path_length_mm'?`${value.toFixed(2)} mm`:value.toFixed(3)
 const keys=(records:RecordedDescriptorRecord[])=>records.map(record=><code key={record.matchId}>{record.conditionKey}</code>)
 return <div className="evolution-signal">
  <div className="evolution-signal-title">{t('Recorded descriptor change')} <small>{t('Descriptive only; not fitness or improvement.')}</small></div>
 {!parent?<small>{t('No parent comparison exists.')}</small>:!comparison?.pairs.length?<><small>{t('Compared recorded condition pairs')}: 0</small><small>{t('No comparable recorded conditions.')}</small><ConditionAccounting comparison={comparison!} keys={keys} t={t}/></>:<><small>{t('Compared recorded condition pairs')}: {comparison.pairs.length}</small><ConditionAccounting comparison={comparison} keys={keys} t={t}/>{!deltas.length?<small>{t('No paired descriptors recorded.')}</small>:!changed.length?<small>{t('No measurable change in the shared recorded descriptors.')}</small>:<div className="evolution-signal-values">{changed.map(item=><span key={item.key}><b>{t(labels[item.key])}</b> Δ {item.delta>0?'+':''}{format(item.key,item.delta)} <small>{format(item.key,item.parent)} → {format(item.key,item.candidate)}</small></span>)}</div>}</>}
 </div>
}

function ConditionAccounting({comparison,keys,t}:{comparison:NonNullable<ReturnType<typeof recordedDescriptorComparison>>;keys:(records:RecordedDescriptorRecord[])=>React.ReactNode;t:(key:string)=>string}){
 const row=(label:string,records:RecordedDescriptorRecord[])=>records.length?<small>{t(label)}: {records.length} · {keys(records)}</small>:null
 return <div className="evolution-signal-accounting">{row('Candidate-only recorded conditions',comparison.unmatchedCandidate)}{row('Parent-only recorded conditions',comparison.unmatchedParent)}{row('Candidate unavailable recorded conditions',comparison.unavailableCandidate)}{row('Parent unavailable recorded conditions',comparison.unavailableParent)}</div>
}
