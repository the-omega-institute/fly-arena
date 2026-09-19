import {useEffect,useMemo,useState} from 'react'
import type {Frame,ReplayEvent} from '../../types'
import {useI18n} from '../../shared/i18n'
import {responsePath,responsePointAt,responseSignals} from './responseSignals'

export function ResponseStory({frames,events,slot,time,onSeek,inputInterval=null,physicsDt=null}:{
  frames:Frame[];events:ReplayEvent[];slot:number;time:number;onSeek:(time:number)=>void;inputInterval?:number|null;physicsDt?:number|null
}){
  const {locale}=useI18n(),zh=locale==='zh-CN'
  const [focus,setFocus]=useState<number|null>(null)
  useEffect(()=>setFocus(null),[frames,slot])
  const rows=useMemo(()=>responseSignals(frames,slot,inputInterval),[frames,slot,inputInterval])
  const contacts=useMemo(()=>physicsDt===null?[]:events.filter(e=>e.type==='food_contact'&&e.slot===slot).map(e=>({time:e.tick*physicsDt,food:Array.isArray(e.food)?e.food.join(', '):e.food===undefined?'':String(e.food)})),[events,slot,physicsDt])
  const environmentContacts=useMemo(()=>physicsDt===null?[]:events.filter(e=>e.type==='environment_contact'&&e.slot===slot).map(e=>({time:e.tick*physicsDt,objects:(e.objects||[]).join(', ')})),[events,slot,physicsDt])
  const supportStarts=useMemo(()=>frames.filter((f,i)=>f.senses?.[slot]?.contact_support?.length&&!frames[i-1]?.senses?.[slot]?.contact_support?.length).map(f=>({time:f.time,objects:f.senses![slot].contact_support!.join(', ')})),[frames,slot])
  const first=frames[0]?.time??0,last=frames.at(-1)?.time??first
  const start=focus===null?first:Math.max(first,focus-.1),end=focus===null?last:Math.min(last,focus+.7)
  const paths=useMemo(()=>rows.map(row=>row.signals.map(s=>responsePath(s.points,start,end,row.maximum,row.id==='input'))),[rows,start,end])
  if(frames.length<2||!rows.some(row=>row.signals.some(s=>s.points.some(p=>p.value!==null))))return null
  const cursor=(time-start)/(end-start)*600
  const labels:Record<string,string>=zh?{input:'接触输入',activity:'感觉神经群',descending:'下行神经群',drive:'左右运动驱动',speed:'身体 XY 速度',intake:'累计摄取',taste:'味觉',touch_left:'左触觉',touch_right:'右触觉',left:'左',right:'右'}:{input:'Contact input',activity:'Sensory populations',descending:'Descending population',drive:'Left / right motor drive',speed:'Body XY speed',intake:'Cumulative intake',taste:'Taste',touch_left:'Left touch',touch_right:'Right touch',left:'Left',right:'Right'}
  const show=(value:number|null|undefined)=>value==null?'—':value.toFixed(2)
  return <section className="response-story" aria-label={zh?'感觉、大脑与身体同步曲线':'Synchronized sensory, brain and body signals'}>
    <div className="response-story-heading"><div><strong>{zh?'从接触到身体反应':'From contact to body response'}</strong><p>{zh?'沿同一时间轴，观察你的大脑怎样响应，以及身体随后发生了什么。':'Follow your brain’s response and the body’s subsequent behavior on one timeline.'}</p></div><b>{time.toFixed(2)} s</b></div>
    <div className="response-story-controls"><label>{zh?'观察范围':'Observation window'} <select aria-label={zh?'观察范围':'Observation window'} value={focus===null?'all':String(focus)} onChange={e=>{const value=e.target.value==='all'?null:Number(e.target.value);setFocus(value);if(value!==null)onSeek(value)}}><option value="all">{zh?'完整生命记录':'Entire life record'}</option>{contacts.map((c,i)=><option key={i} value={c.time}>{zh?'食物接触':'Food contact'} {i+1} · {c.time.toFixed(2)} s {c.food}</option>)}{environmentContacts.map((c,i)=><option key={'environment-'+i} value={c.time}>{zh?'环境接触':'Environment contact'} · {c.time.toFixed(2)} s {c.objects}</option>)}{supportStarts.map((c,i)=><option key={'support-'+i} value={c.time}>{zh?'首次采样到足部支撑':'First sampled foot support'} · {c.time.toFixed(2)} s {c.objects}</option>)}</select></label><span>{zh?'点击曲线定位身体和脑图；也可使用下方时间滑块。':'Click a curve to seek the body and brain, or use the time slider below.'}</span></div>
    <div className="response-story-rows">{rows.map((row,rowIndex)=><div className="response-story-row" key={row.id} data-signal-row={row.id}>
      <div className="response-story-label"><strong>{labels[row.id]}</strong><small>0–{show(row.maximum)} {row.unit}</small></div>
      <svg viewBox="0 0 600 54" preserveAspectRatio="none" role="img" aria-label={labels[row.id]} onClick={e=>{const rect=e.currentTarget.getBoundingClientRect();if(rect.width>0)onSeek(start+Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width))*(end-start))}}>
        <line x1="0" x2="600" y1="48" y2="48" stroke="currentColor" opacity=".14"/>
        {contacts.filter(c=>c.time>=start&&c.time<=end).map((c,i)=><line key={i} x1={(c.time-start)/(end-start)*600} x2={(c.time-start)/(end-start)*600} y1="2" y2="50" stroke="#b58728" strokeDasharray="3 4" opacity=".4"/>)}
        {row.signals.map((s,signalIndex)=><path key={s.id} d={paths[rowIndex][signalIndex]} fill="none" stroke={s.color} strokeWidth="1.7" vectorEffect="non-scaling-stroke"/>)}
        {cursor>=0&&cursor<=600&&<line x1={cursor} x2={cursor} y1="0" y2="54" stroke="currentColor" opacity=".65"/>}
      </svg>
      <div className="response-story-values">{row.signals.map(s=><span key={s.id} style={{color:s.color}}>{row.signals.length>1?labels[s.id]+' ':''}<b>{show(responsePointAt(s.points,time)?.value)}</b></span>)}</div>
    </div>)}</div>
    <div className="response-story-seek"><span>{start.toFixed(2)} s</span><input type="range" aria-label={zh?'定位身体和脑图':'Seek body and brain'} min={start} max={end} step="any" value={Math.max(start,Math.min(end,time))} onChange={e=>onSeek(Number(e.target.value))}/><span>{end.toFixed(2)} s</span></div>
    <p className="response-story-note">{zh?'虚线为真实食物接触事件；曲线来自该果蝇的记录，缺失处留空。各行纵轴独立，缩放时间不会改变纵轴。XY 速度可能包含滑动。':'Dashed lines mark actual food contacts. Curves use this fly’s recorded samples; missing observations stay blank. Each row has its own fixed vertical scale. XY speed can include slipping.'} {inputInterval===null?(zh?'输入采样时延未知，按原时间显示。':'Input timing is unavailable; original timestamps are shown.'):(zh?`输入按记录的 ${Math.round(inputInterval*1000)} ms 区间起点显示，神经与身体按区间终点显示。`:`Inputs use the recorded ${Math.round(inputInterval*1000)} ms block start; brain and body use its end.`)} {zh?'这些是观测变化，不自动证明因果。':'These observations do not by themselves establish causality.'}</p>
  </section>
}
