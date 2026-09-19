import {useMemo} from 'react'
import type {Frame,ReplayEvent,Scene} from '../../types'
import {useI18n} from '../../shared/i18n'
import {behaviorChapters,thoraxTilt} from './behaviorSummary'

export function BehaviorChapters({scene,frame,frames,events,slot,time,onSeek}:{
  scene:Scene;frame?:Frame;frames:Frame[];events:ReplayEvent[];slot:number;time:number;onSeek:(time:number)=>void;
}){
  const {locale}=useI18n(),zh=locale==='zh-CN'
  const chapters=useMemo(()=>behaviorChapters(frames,events,slot),[frames,events,slot])
  const lastIntake=useMemo(()=>events.filter(e=>e.type==='intake'&&e.slot===slot).reduce<number|null>(
    (latest,e)=>Math.max(latest??0,e.tick/10000),null),[events,slot])
  const tilt=thoraxTilt(scene,frames[0],frame,slot)
  const firstInverted=useMemo(()=>frames.find(f=>(thoraxTilt(scene,frames[0],f,slot)??0)>90),[scene,frames,slot])
  const value=(n:number|null)=>n===null?'—':n.toFixed(2)
  if(!chapters.length)return null
  return <section className="behavior-chapters" aria-label={zh?'实际行为分段':'Recorded behavior chapters'}>
    <div className="behavior-chapters-heading"><div><strong>{zh?'这段生命记录发生了什么':'What happened in this life record'}</strong><p>{zh?'选择一段，从该时刻观察身体和大脑。':'Choose a chapter to observe its body and brain.'}</p></div>
      <span>{zh?'最后一次摄取事件':'Last intake event'}<b>{lastIntake===null?(zh?'未记录':'Not recorded'):lastIntake.toFixed(2)+' s'}</b></span><span>{zh?'身体倾角':'Body tilt'}<b>{tilt===null?'—':tilt.toFixed(1)+'°'}{tilt!==null&&tilt>90?(zh?' · 倒置':' · inverted'):''}</b></span></div>
    {firstInverted&&<button className="behavior-posture-jump" onClick={()=>onSeek(firstInverted.time)}>{zh?'查看首次倒置姿态':'Inspect first inverted pose'} · {firstInverted.time.toFixed(2)} s →</button>}
    <div className="behavior-chapters-list">{chapters.map((c,i)=>{
      const active=time>=c.start&&(time<c.end||(i===chapters.length-1&&time<=c.end))
      return <button key={c.start} className={active?'active':''} aria-pressed={active} onClick={()=>onSeek(c.start)}>
        <span className="behavior-chapter-time">{c.start.toFixed(2)}–{c.end.toFixed(2)} s <small>{zh?'观看这段':'Watch chapter'} →</small></span>
        <span className="behavior-chapter-metric">{zh?'记录路径 / 净位移':'Recorded path / displacement'}<b>{value(c.path)} / {value(c.displacement)} mm</b></span>
        <span className={'behavior-chapter-metric '+(c.intake!==null&&c.intake>0?'has-intake':'')}>{zh?'摄取增量':'Intake change'}<b>{c.intake!==null&&c.intake>0?'+':''}{value(c.intake)}</b></span>
        <span className="behavior-chapter-contacts">{zh?'接触事件':'Contact events'}<b>{zh?'食物':'Food'} {c.foodContacts} · {zh?'环境':'Environment'} {c.environmentContacts} · {zh?'对手':'Other fly'} {c.flyContacts}</b>{c.exits>0&&<em>{zh?'越界':'Boundary exit'} ×{c.exits}</em>}</span>
      </button>
    })}</div>
    <p className="behavior-chapters-note">{zh?'每段约 5 秒，边界使用实际采样时间。路径为胸部 XY 采样位移之和，也可能包含滑动；摄取增量来自该回放的记账规则。接触数统计已记录事件，不表示接触时长；缺失数据用 — 表示。倾角由胸部姿态相对初始朝向计算，大于 90° 标为倒置。':'Chapters span about 5 seconds using recorded timestamps. Path sums sampled thorax XY motion, including possible slipping. Intake follows this replay’s rules. Contact counts are recorded events, not contact duration; — means missing data. Thorax tilt is relative to the initial orientation; over 90° is labeled inverted.'}</p>
  </section>
}
