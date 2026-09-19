import type {BehaviorMetric} from '../../types'
import {useI18n} from '../../shared/i18n'

export function BehaviorFitness({metric}:{metric?:BehaviorMetric|null}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 if(!metric||metric.schema!=='sustained-foraging-v1')return null
 return <details className="replay-analysis behavior-fitness"><summary>{zh?'持续觅食评估':'Sustained foraging evaluation'} · {metric.fitness.toFixed(3)}</summary>
  <div className="observation-metrics">
   <div><span>{zh?'总摄取':'Total food'}</span><strong>{metric.food.toFixed(3)}</strong></div>
   <div><span>{zh?'后半程摄取':'Food in second half'}</span><strong>{metric.latter_half_food.toFixed(3)}</strong></div>
   <div><span>{zh?'未倒置时间比例':'Time not inverted'}</span><strong>{(metric.upright_fraction*100).toFixed(1)}%</strong></div>
  </div>
  <p>{zh?'计算方式：（总摄取 + 后半程摄取）× 未倒置时间比例。':'Formula: (total food + food in the second half) × fraction of time not inverted.'}</p>
  <small>{zh?'倾角相对初始姿态，大于 90° 计为倒置；按记录采样间隔估算时间。用于可选训练目标，不改变本场比赛胜负，也不证明已经学会行为。':'Tilt is relative to the initial pose; over 90° counts as inverted. Time is estimated from recorded sample intervals. This optional training objective does not change the match winner or prove learned behavior.'}</small>
 </details>
}
