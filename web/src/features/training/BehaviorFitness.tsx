import type {BehaviorMetric} from '../../types'
import {useI18n} from '../../shared/i18n'

export function BehaviorFitness({metric}:{metric?:BehaviorMetric|null}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 if(!metric||metric.schema!=='sustained-foraging-v1')return null
 return <div className="behavior-record">
  <p className="behavior-observation">{zh?'实际记录':'Recorded'} {metric.recorded_seconds.toFixed(2)} s · {metric.food===0
   ?zh?'窗口内没有记录到摄取。':'No intake recorded in this window.'
   :`${zh?'总摄取':'Total food'} ${metric.food.toFixed(3)}.`} {metric.first_inversion_s===null
   ?zh?'窗口内未记录倒置。':'No inversion recorded in this window.'
   :`${zh?'首次倒置':'First inversion'} ${metric.first_inversion_s.toFixed(2)} s.`}</p>
  {metric.food===0&&<p className="training-hint">{zh?'打开行为与神经回放，检查它是否接近食物、发生接触、出现感觉和神经响应；没有摄取本身不能说明失败原因。':'Open the behavior and neural replay to inspect approach, contact, sensory input and neural response. No intake alone does not identify the cause.'}</p>}
  <details className="replay-analysis behavior-fitness"><summary>{zh?'持续觅食评估':'Sustained foraging evaluation'} · {metric.fitness.toFixed(3)}</summary>
  <div className="observation-metrics">
   <div><span>{zh?'总摄取':'Total food'}</span><strong>{metric.food.toFixed(3)}</strong></div>
   <div><span>{zh?'后半程摄取':'Food in second half'}</span><strong>{metric.latter_half_food.toFixed(3)}</strong></div>
   <div><span>{zh?'未倒置时间比例':'Time not inverted'}</span><strong>{(metric.upright_fraction*100).toFixed(1)}%</strong></div>
  </div>
  <p>{zh?'计算方式：（总摄取 + 后半程摄取）× 未倒置时间比例。':'Formula: (total food + food in the second half) × fraction of time not inverted.'}</p>
  <small>{zh?'倾角相对初始姿态，大于 90° 计为倒置；按记录采样间隔估算时间。用于可选训练目标，不改变本场比赛胜负，也不证明已经学会行为。':'Tilt is relative to the initial pose; over 90° counts as inverted. Time is estimated from recorded sample intervals. This optional training objective does not change the match winner or prove learned behavior.'}</small>
 </details></div>
}
