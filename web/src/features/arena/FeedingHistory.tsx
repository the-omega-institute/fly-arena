import {useMemo} from 'react'
import {useI18n} from '../../shared/i18n'
import type {ReplayEvent,Scene} from '../../types'
import {feedingEpisodes} from './feedingEpisodes'

export function FeedingHistory({events,scene,slot,endTime,time,physicsDt,accountingTicks,onSeek}:{events:ReplayEvent[];scene:Scene;slot:number;endTime:number;time:number;physicsDt:number|null;accountingTicks:number|null;onSeek:(time:number)=>void}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 const result=useMemo(()=>feedingEpisodes(events,slot,(scene.food||[]).map(f=>f.id),physicsDt??NaN,accountingTicks??NaN),[events,scene.food,slot,physicsDt,accountingTicks])
 if(!scene.food?.length)return null
 const {episodes}=result,last=episodes.length?Math.max(...episodes.map(e=>e.end)):null
 const total=episodes.reduce((sum,e)=>sum+e.amount,0),foods=new Set(episodes.map(e=>e.food)).size
 const tail=last===null?null:Math.max(0,endTime-last),interval=(physicsDt??0)*(accountingTicks??0)
 return <section className="feeding-history" aria-label={zh?'实际摄取过程':'Recorded feeding history'}>
  <div className="feeding-history__heading"><div><strong>{zh?'它究竟吃到了什么':'What did this fly actually eat?'}</strong><p>{zh?'点击一段摄取记录，定位身体、感觉和大脑。':'Select a feeding record to inspect the body, senses and brain.'}</p></div>{result.timingAvailable&&episodes.length>0&&<span>{foods} {zh?'处食物':'food patches'} · {total.toFixed(3)} {zh?'摄取单位':'food units'}</span>}</div>
  {!result.timingAvailable?<p>{zh?'未提供事件时钟，无法把摄取事件定位到回放。':'The event clock is unavailable; intake events cannot be placed on the replay.'}</p>:!episodes.length?<p>{zh?'这份记录没有可用的摄取事件。':'This record contains no usable intake events.'}</p>:<>
   <div className="feeding-history__episodes">{episodes.map((e,i)=>{
    const active=time>=Math.max(0,e.start-interval)&&time<=e.end
    const seek=e.contactTimes[0]??e.start
    return <article key={`${e.food}:${e.firstTick}`} className={active?'active':''}>
     <button className="feeding-history__jump" onClick={()=>onSeek(seek)} aria-current={active?'step':undefined}><span>{zh?'摄取记录':'Feeding record'} {i+1} · <b>{e.foodId}</b></span><strong>+{e.amount.toFixed(3)}</strong><small>{e.start.toFixed(2)}{e.start===e.end?'':`–${e.end.toFixed(2)}`} s →</small></button>
     <div className="feeding-history__detail">{e.contactTimes.length?<button onClick={()=>onSeek(e.contactTimes[0])}>{zh?'观察对应的食物接触':'Inspect recorded food contact'} · {e.contactTimes[0].toFixed(2)} s →</button>:<span>{zh?'该摄取区间未记录到食物接触事件；不能据此补出味觉响应。':'No food-contact event was recorded in this intake interval; a taste response cannot be inferred.'}</span>}{e.batches===1&&<span>{zh?'仅一批摄取记账，不代表持续停留。':'One accounting batch; this does not establish sustained feeding.'}</span>}</div>
    </article>
   })}</div>
   {last!==null&&tail!==null&&tail>interval&&<div className="feeding-history__tail"><span>{zh?'最后一笔摄取之后':'After the last intake record'}</span><strong>{tail.toFixed(2)} s {zh?'未再记录摄取':'without another recorded intake'}</strong><div><button onClick={()=>onSeek(last)}>{zh?'从这里看后续行为':'Inspect subsequent behavior'} · {last.toFixed(2)} s →</button><button onClick={()=>onSeek(endTime)}>{zh?'查看结束姿态':'Inspect final posture'} · {endTime.toFixed(2)} s →</button></div></div>}
  </>}
  {result.invalid>0&&<p role="status">{zh?'部分摄取事件缺少有效数据；上方仅展示可读取的记录。':'Some intake events are invalid or incomplete; only readable records are shown above.'}</p>}
  <p className="feeding-history__note">{zh?'按同一食物点的连续非零记账批次分段，时间为记账批次结束时刻，不是精确的进食起止时间。缺少接触记录不等于没有摄取；也不能用摄取量替代神经活动证据。':'Records group consecutive positive accounting batches for the same food patch. Times are batch ends, not exact feeding onset or duration. Missing contact records do not negate measured intake; intake is not evidence of a neural response.'}</p>
 </section>
}
