import type {Match} from '../../types'
import {useI18n} from '../../shared/i18n'
import {recordedDescriptorDeltas} from './recordedDescriptors'

type SignalMember={fly_id:string;matches:Match[]}
const labels={food:'Recorded food',latter_half_food:'Recorded second-half food',upright_fraction:'Recorded upright fraction',path_length_mm:'Recorded path length'} as const

export function EvolutionSignal({candidate,parent}:{candidate:SignalMember;parent?:SignalMember}){
 const {t}=useI18n()
 const deltas=parent?recordedDescriptorDeltas(candidate.matches,candidate.fly_id,parent.matches,parent.fly_id):[]
 const changed=deltas.filter(item=>Math.abs(item.delta)>1e-9)
 const format=(key:typeof deltas[number]['key'],value:number)=>key==='upright_fraction'?`${(value*100).toFixed(1)}%`:key==='path_length_mm'?`${value.toFixed(2)} mm`:value.toFixed(3)
 return <div className="evolution-signal">
  <div className="evolution-signal-title">{t('Recorded descriptor change')} <small>{t('Descriptive only; not fitness or improvement.')}</small></div>
  {!parent?<small>{t('Parent descriptor record unavailable.')}</small>:!deltas.length?<small>{t('No paired descriptors recorded.')}</small>:!changed.length?<small>{t('No measurable change in the shared recorded descriptors.')}</small>:<div className="evolution-signal-values">{changed.map(item=><span key={item.key}><b>{t(labels[item.key])}</b> Δ {item.delta>0?'+':''}{format(item.key,item.delta)} <small>{format(item.key,item.parent)} → {format(item.key,item.candidate)}</small></span>)}</div>}
 </div>
}
