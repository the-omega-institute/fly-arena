import {useI18n} from '../../shared/i18n'

export function ObservationDuration({value,onChange}:{value:number;onChange:(value:number)=>void}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 const options=[...new Set([2,5,10,30,60,120,180,...(Number.isInteger(value)&&value>=1&&value<=180?[value]:[])])].sort((a,b)=>a-b)
 return <div className="observation-duration"><label>{zh?'每场观察时长':'Observation time per match'}<select aria-label={zh?'每场观察时长':'Observation time per match'} value={value} onChange={e=>onChange(Number(e.target.value))}>{options.map(seconds=><option key={seconds} value={seconds}>{seconds} {zh?'秒':'s'}{seconds===2?(zh?' · 快速试跑':' · workflow trial'):seconds===10?(zh?' · 初次观察':' · first observation'):seconds===180?(zh?' · 3 分钟':' · 3 minutes'):''}</option>)}</select></label>
 <p>{zh?'时间越长，越有机会观察接近食物之后的运动、摄取、翻倒或恢复；也会增加计算和等待时间。更长不保证更好，也不代表学会了什么。':'Longer runs give more opportunity to observe movement, feeding, falls or recovery after approaching food. They also require more computation and waiting; longer does not guarantee improvement or learning.'}</p>
 <p>{zh?'这是模拟世界的时间，不是出结果的倒计时。每场最多 180 秒，运行可能提前结束；换位对比需要两场，双方使用相同的时长和条件。':'This is time in the simulated world, not a countdown to results. Each match supports up to 180 seconds and may finish early; a comparison uses two swapped matches with identical duration and conditions.'}</p>
 {value<=2&&<p className="duration-trial" role="note">{zh?'2 秒仅适合试通运行和回放、观察初始反应；可能还来不及接触食物。':'Two seconds is a workflow trial for submission, replay and initial responses; the fly may not reach food.'}</p>}
 </div>
}
