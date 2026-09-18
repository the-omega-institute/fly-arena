import {useState} from 'react'
import {ArrowDownToLine,AudioLines,GitBranch} from 'lucide-react'
import type {Fly,Frame,Match,Scene,Season} from '../../types'
import {colors} from '../../types'
import {useI18n} from '../../shared/i18n'

function tracePath(frames:Frame[],read:(frame:Frame)=>number|undefined,max:number) {
  const start=frames[0]?.time||0,end=frames.at(-1)?.time||start
  let connected=false
  return frames.map(frame=>{
    const value=read(frame)
    if(value===undefined||!Number.isFinite(value)){connected=false;return ''}
    const x=end>start?(frame.time-start)/(end-start)*240:0,y=48-value/max*44
    const part=`${connected?'L':'M'}${x.toFixed(2)},${y.toFixed(2)}`;connected=true;return part
  }).join(' ')
}
function shown(value:number|undefined,digits=1){return value===undefined?'—':value.toFixed(digits)}

export function MatchObservations({scene,frame,frames,flies,selectedId,season,match}:{scene:Scene;frame?:Frame;frames:Frame[];flies:Fly[];selectedId:string;season:Season|null;match?:Match}) {
  const {t,locale}=useI18n()
  const [slot,setSlot]=useState(()=>Math.max(0,scene.flies.findIndex(f=>f.id===selectedId)))
  const participant=scene.flies[slot],fly=flies.find(f=>f.id===participant?.id)
  const parent=flies.find(f=>f.id===fly?.spec.parent_id)
  const circuits=season?.connectome.circuits||[]
  const circuitPeak=(id:string)=>Math.max(1,...frames.map(f=>f.traces?.[slot]?.[id]??0))
  const scorePeak=Math.max(1,...frames.map(f=>f.scores?.[slot]??0))
  const color=colors[participant?.color]||colors.mint
  function download(){
    const payload={schema_version:'match-observations/v1',match_id:match?.id,request:match?.request,result:match?.result,
      units:{time:'seconds',position:'mm',circuit_activity:'Hz',energy:'game reserve units',score:'food units'},
      scope:'Recorded circuit average firing rates and body observations, not individual neuron spike trains.',
      participants:scene.flies.map((entry,slot)=>({slot,...entry,spec:flies.find(f=>f.id===entry.id)?.spec||null})),
      samples:frames.map(({time,tick,positions,scores,energy,drives,traces})=>({time,tick,positions,scores,energy,drives,traces}))}
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}))
    const link=document.createElement('a');link.href=url;link.download=`fly-arena-${match?.id||'match'}-observations.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <section className="trace-panel panel observations">
    <div className="panel-heading"><span><AudioLines size={16}/>{t('Neural & behavior records')}</span><button className="text-link" onClick={download}><ArrowDownToLine size={14}/>{t('Export records')}</button></div>
    <div className="observation-subjects" role="group" aria-label={t('Observed fly')}>{scene.flies.map((entry,i)=><button key={i} className={slot===i?'active':''} aria-pressed={slot===i} onClick={()=>setSlot(i)}><i style={{background:colors[entry.color]}}/>{t('Slot')} {i+1} · {entry.name}<small>{entry.id.slice(0,8)}</small></button>)}</div>
    <div className="observation-metrics"><div><span>{t('Food collected')}</span><strong>{shown(frame?.scores?.[slot],2)}</strong><svg viewBox="0 0 240 52" role="img" aria-label={t('Food score over time')}><path d={tracePath(frames,f=>f.scores?.[slot],scorePeak)} fill="none" stroke={color} strokeWidth="2"/></svg></div><div><span>{t('Energy reserve')}</span><strong>{shown(frame?.energy?.[slot])}</strong><svg viewBox="0 0 240 52" role="img" aria-label={t('Energy over time')}><path d={tracePath(frames,f=>f.energy?.[slot],Math.max(100,...frames.map(f=>f.energy?.[slot]??0)))} fill="none" stroke={color} strokeWidth="2"/></svg></div><div><span>{t('Left / right motor drive')}</span><strong>{shown(frame?.drives?.[slot]?.[0],2)} / {shown(frame?.drives?.[slot]?.[1],2)}</strong><small>{t('Recorded at')} {shown(frame?.time,2)} s</small></div></div>
    {scene.habitat==='forest-floor'&&<div className="observation-metrics"><div><span>{locale==='zh-CN'?'胸部高度 · mm':'Thorax height · mm'}</span><strong>{shown(frame?.positions?.[slot]?.[2],2)}</strong><svg viewBox="0 0 240 52" role="img" aria-label={locale==='zh-CN'?'记录到的身体高度':'Recorded body height'}><path d={tracePath(frames,f=>f.positions?.[slot]?.[2],Math.max(1,...frames.map(f=>f.positions?.[slot]?.[2]??0)))} fill="none" stroke={color} strokeWidth="2"/></svg><small>{locale==='zh-CN'?'世界坐标 Z；高度变化也可能来自姿态变化或翻倒。':'World Z; height changes may also reflect posture or a fall.'}</small></div></div>}
    <div className="trace-circuits">{circuits.map(c=><div key={c.id}><span style={{color:c.color}}>{t(c.label)}</span><strong>{shown(frame?.traces?.[slot]?.[c.id])}<small> Hz</small></strong><svg viewBox="0 0 240 52" role="img" aria-label={`${t(c.label)} · Hz`}><path fill="none" stroke={c.color} strokeWidth="1.8" d={tracePath(frames,f=>f.traces?.[slot]?.[c.id],circuitPeak(c.id))}/></svg><small>0–{circuitPeak(c.id).toFixed(1)} Hz</small></div>)}</div>
    <div className="observation-lineage"><GitBranch size={16}/><span>{t('Parent design')}: <strong>{fly?.spec.parent_id?`${parent?.name||t('Unavailable')} · ${fly.spec.parent_id.slice(0,8)}`:fly?t('Founder / no parent'):t('Not recorded')}</strong></span><span>{t('Mutation budget')}: {shown(fly?.report.budget_used)} / {fly?.report.budget_limit??'—'}</span></div>
    <p className="observation-note">{frames.length} {t('recorded samples')} · {frames[0]?.time.toFixed(2)}–{frames.at(-1)?.time.toFixed(2)} s · {t('Circuit averages; each chart uses its own scale. Energy is a game reserve, not metabolic measurement.')}</p>
  </section>
}
