import {useEffect,useMemo,useState} from 'react'
import {ArenaCanvas} from '../../ArenaCanvas'
import type {Frame,Match,ReplayEvent,Scene,Season} from '../../types'
import {api} from '../../api'
import {useI18n} from '../../shared/i18n'
import {useReplay} from './useReplay'
import {selectReplayFrames} from './replayFrames'
import {BrainTheater} from './MatchObservations'
import {thoraxTilt} from './behaviorSummary'
import {replayComparisonContext,type ReplayReceipt} from './replayComparisonContext'

export function comparisonWindow(left:Frame[],right:Frame[]){
 if(!left.length||!right.length)return null
 const start=Math.max(left[0].time,right[0].time),end=Math.min(left.at(-1)!.time,right.at(-1)!.time)
 return Number.isFinite(start)&&Number.isFinite(end)&&end>start?{start,end}:null
}

export function comparisonActivityScales(groups:Frame[][]){
 let region=1,node=1
 for(const frames of groups)for(const f of frames){
  for(const trace of f.traces||[])for(const value of Object.values(trace))if(Number.isFinite(value))region=Math.max(region,value)
  for(const brain of f.brain||[]){
   for(const value of Object.values(brain.circuits||{}))if(Number.isFinite(value))region=Math.max(region,value)
   for(const p of brain.sampled_nodes||brain.top_nodes||[])if(Number.isFinite(p.activity))node=Math.max(node,p.activity)
  }
 }
 return {region,node}
}

export function ReplayComparison({match,scene,frames,events,matches,season,selectedId}:{
 match:Match;scene:Scene;frames:Frame[];events:ReplayEvent[];matches:Match[];season:Season|null;selectedId:string;
}){
 const {locale,t}=useI18n(),zh=locale==='zh-CN'
 const choices=matches.filter(m=>m.status==='verified'&&m.id!==match.id)
 const preferred=match.source?.comparison_links?.find(l=>choices.some(m=>m.id===l.match_id))?.match_id||match.source?.comparison_match
 const [otherId,setOtherId]=useState(preferred||choices[0]?.id||'')
 const other=choices.find(m=>m.id===otherId)||choices[0]
 const replay=useReplay(other?.id||'',other?.status)
 const [receipts,setReceipts]=useState<{left:ReplayReceipt|null;right:ReplayReceipt|null}>({left:null,right:null})
 useEffect(()=>{
  let active=true;setReceipts({left:null,right:null})
  if(!other?.id)return()=>{active=false}
  Promise.allSettled([api<ReplayReceipt>('/matches/'+encodeURIComponent(match.id)+'/receipt'),api<ReplayReceipt>('/matches/'+encodeURIComponent(other.id)+'/receipt')]).then(results=>{
   if(!active)return
   setReceipts({left:results[0].status==='fulfilled'?results[0].value:null,right:results[1].status==='fulfilled'?results[1].value:null})
  })
  return()=>{active=false}
 },[match.id,other?.id])
 const [leftId,setLeftId]=useState(selectedId),[rightId,setRightId]=useState('')
 const [time,setTime]=useState(0),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(.5)
 const [follow,setFollow]=useState(true)
 const range=useMemo(()=>comparisonWindow(frames,replay.frames),[frames,replay.frames])
 const scales=useMemo(()=>comparisonActivityScales([frames,replay.frames]),[frames,replay.frames])
 const start=range?.start??0,end=range?.end??0,ready=replay.status==='ready'&&!!range
 const shownTime=Math.max(start,Math.min(end,time))
 const context=useMemo(()=>replayComparisonContext({match,receipt:receipts.left,participant:scene.flies.find(f=>f.id===leftId)||scene.flies[0]},{match:other,receipt:receipts.right,participant:replay.scene?.flies.find(f=>f.id===rightId)||replay.scene?.flies[0]}),[match,other,receipts,scene,replay.scene,leftId,rightId])
 useEffect(()=>{
  if(!playing||!ready)return
  let handle=0;const initial=shownTime,started=performance.now()
  const step=(now:number)=>{
   const next=Math.min(end,initial+(now-started)/1000*speed);setTime(next)
   if(next>=end)setPlaying(false);else handle=requestAnimationFrame(step)
  }
  handle=requestAnimationFrame(step);return()=>cancelAnimationFrame(handle)
  // Time is sampled once when playback starts; each tick must not restart it.
 },[playing,ready,start,end,speed])
 const seek=(value:number)=>{setPlaying(false);setTime(Math.max(start,Math.min(end,value)))}
 const name=(m:Match)=>`${m.participants?.map(p=>p.name).join(' / ')||m.request.fly_ids.map(id=>id.slice(0,8)).join(' / ')} · ${m.request.map_id} · seed ${m.request.seed} · ${m.id.slice(0,8)}`
 function pane(record:Match,world:Scene,samples:Frame[],ledger:ReplayEvent[],chosen:string,setChosen:(id:string)=>void,side:string){
  const slot=Math.max(0,world.flies.findIndex(f=>f.id===chosen)),body=world.flies[slot]
  const selection=selectReplayFrames(samples,shownTime),frame=selection.frame
  const fly=record.participants?.find(p=>p.id===body?.id)
  const tilt=thoraxTilt(world,samples[0],frame,slot)
  return <article className="replay-comparison-pane" aria-label={side}>
   <header><strong>{side}</strong><small>{record.request.map_id} · seed {record.request.seed} · {record.request.duration_seconds}s</small></header>
   <label>{zh?'观察果蝇':'Observed individual'}<select aria-label={`${side} · ${zh?'观察果蝇':'Observed individual'}`} value={body?.id||''} onChange={e=>setChosen(e.target.value)}>{world.flies.map(f=><option key={f.id} value={f.id}>{f.name} · {f.id.slice(0,8)}</option>)}</select></label>
   <div className="replay-comparison-canvas"><ArenaCanvas scene={world} frames={samples} {...selection} selectedId={body?.id} followSelected={follow}/></div>
   <div className="replay-comparison-metrics"><span>{zh?'记录时刻':'Recorded sample'}<b>{frame?.time.toFixed(2)??'—'}s</b></span><span>{zh?'已摄取':'Consumed'}<b>{frame?.scores?.[slot]?.toFixed(3)??'—'}</b></span><span>{zh?'身体倾角':'Body tilt'}<b>{tilt===null?'—':`${tilt.toFixed(1)}°`}{tilt!==null&&tilt>90?(zh?' · 倒置':' · inverted'):''}</b></span></div>
   <small className="replay-comparison-context">{fly?.spec.model_profile||'—'} · {record.request.sensory_profile||'odor-only-v1'} · {record.request.bridge_profile||'legacy-v1'}</small>
   <BrainTheater playback={{playing,onToggle:()=>{if(shownTime>=end)setTime(start);setPlaying(!playing)}}} matchId={record.id} key={`${record.id}:${body?.id}`} frame={frame} frames={samples} season={season} fly={fly} slot={slot} events={ledger} onSeek={seek} activityScale={scales.region} nodeScale={scales.node}/>
  </article>
 }
 const contextLabels:Record<string,string>={mode:'Match mode',participant:'Participant identity',opponents:'Opponent identities',map:'Map',seed:'Seed',horizon:'Horizon',bridgeReadout:'Bridge / readout',sensoryProfile:'Sensory profile',motorProfile:'Motor profile',runtimeSource:'Runtime / source identity',recordingPolicy:'Recording policy'}
 const contextStatement=context.hasDifferences?'Comparison receipts differ; this supports descriptive observations only and cannot attribute an observed difference to the design.':context.hasUnavailable?'Some receipt conditions are unavailable, so this comparison cannot establish an effect; keep the interpretation descriptive.':'The recorded conditions agree, supporting a descriptive comparison under this protocol. The receipts do not by themselves establish causality, generalization, or biological validity.'
 function conditionTable(){return <section className="replay-comparison-conditions" aria-label={t('Comparison conditions')}><h3>{t('Comparison conditions')}</h3><table><thead><tr><th>{t('Condition')}</th><th>{t('Current replay')}</th><th>{t('Comparison replay')}</th><th>{t('Status')}</th></tr></thead><tbody>{context.conditions.map(condition=><tr key={condition.id} className={'condition-'+condition.status}><th scope="row">{t(contextLabels[condition.id])}</th><td><code>{condition.left??t('Unavailable')}</code></td><td><code>{condition.right??t('Unavailable')}</code></td><td><span className={'condition-status '+condition.status}>{t(condition.status==='agree'?'Agree':condition.status==='differ'?'Differ':'Unavailable')}</span></td></tr>)}</tbody></table><p className="training-hint">{t(contextStatement)}</p></section>}
 return <section className="replay-comparison panel" aria-label={zh?'同步生命回放对照':'Synchronized life replays'}>
  <h2>{zh?'同一时刻，两份生命记录':'One moment, two life records'}</h2>
  <p>{zh?'一起观察身体、感觉和脑活动。点击任一侧的事件，两侧都会跳到同一仿真时刻。':'Watch bodies, senses and brain activity together. Select an event on either side to seek both recordings to the same simulation time.'}</p>
  <label className="replay-comparison-picker">{zh?'选择另一份回放':'Choose the other replay'}<select value={other?.id||''} onChange={e=>{setPlaying(false);setTime(0);setOtherId(e.target.value);setRightId('')}} disabled={!choices.length}>{choices.map(m=><option key={m.id} value={m.id}>{name(m)}</option>)}</select></label>
  {!choices.length?<p>{zh?'还没有另一份已完成回放。':'No other completed replay is available.'}</p>:!ready?<p role={replay.status==='error'?'alert':'status'}>{replay.status==='error'?replay.error:replay.status==='ready'?(zh?'两份记录没有共同的时间范围。':'These records have no overlapping time range.'):(zh?'正在载入另一份身体与神经记录…':'Loading the other body and neural record…')}</p>:<>
   {conditionTable()}
   <div className="replay-comparison-controls"><button onClick={()=>{if(shownTime>=end)setTime(start);setPlaying(!playing)}}>{playing?(zh?'暂停同步回放':'Pause both replays'):(zh?'播放同步回放':'Play both replays')}</button><output>{shownTime.toFixed(2)} s</output>
    <input aria-label={zh?'同步回放时间':'Shared replay time'} type="range" min={start} max={end} step=".01" value={shownTime} onChange={e=>seek(Number(e.target.value))}/><span>{end.toFixed(2)} s</span>
    <select aria-label={zh?'同步播放速度':'Shared playback speed'} value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.25,.5,1,2].map(s=><option key={s} value={s}>{s}×</option>)}</select>
    <button aria-pressed={follow} onClick={()=>setFollow(!follow)}>{follow?(zh?'跟随身体':'Following bodies'):(zh?'场景全景':'Arena overview')}</button>
   </div>
   <p className="training-hint">{zh?'这是两次独立实验，时间按仿真起点对齐；不同种子或配置仍显示在各自标题中，不能视为完全相同条件。亮度采用两份记录共同的固定色标；身体在采样之间插值，神经数值保持实际采样。':'These are separate experiments aligned by simulation time. Seeds and configurations remain visible; this does not imply identical conditions. Both brains use a shared fixed activity scale. Bodies interpolate between poses; neural values remain recorded samples.'} {zh?'共同记录区间':'Shared recorded interval'}: {start.toFixed(2)}–{end.toFixed(2)} s.</p>
   <div className="replay-comparison-grid">
    {pane(match,scene,frames,events,leftId,setLeftId,zh?'当前生命记录':'Current life record')}
    {other&&replay.scene&&pane(other,replay.scene,replay.frames,replay.events,rightId,setRightId,zh?'对照生命记录':'Comparison life record')}
   </div>
  </>}
 </section>
}
