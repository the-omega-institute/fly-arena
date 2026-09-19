import {BehaviorFitness} from '../training/BehaviorFitness'
import {ReplayDesignActions} from './ReplayDesignActions'
import type {ReplayDesignOrigin} from './replayDesign'
import {FeedingHistory} from './FeedingHistory'
import {useEffect,useMemo,useState} from 'react'
import {ArrowDownToLine,AudioLines,GitBranch} from 'lucide-react'
import {api} from '../../api'
import type {Fly,Frame,Match,ReplayEvent,ReplayParticipant,Scene,Season,NeuralGraph,BrainDesignGraph,Spec} from '../../types'
import {colors} from '../../types'
import {useI18n} from '../../shared/i18n'
import {BrainActivityOverview} from './BrainActivityOverview'
import {LifeEventTimeline} from './LifeEventTimeline'
import {eventSampleWindow} from './lifeEvents'
import {BehaviorChapters} from './BehaviorChapters'
import {ResponseStory} from './ResponseStory'
import {LocalBrainGraph} from './LocalBrainGraph'
import {SharedResources} from './SharedResources'

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

function deriveEvents(frames:Frame[],slot:number):ReplayEvent[] {
  const result:ReplayEvent[]=[]; let prior={odor:false,visual:false,touch:false,score:0}
  for(const frame of frames){
    const sense=frame.senses?.[slot]; const odor=!!sense&&sense.odor.reduce((a,b)=>a+b,0)>.04
    const visual=!!sense&&Math.max(...sense.visual)>.05; const touch=!!sense&&(sense.contact_food!==undefined?sense.contact_food.length>0:sense.touch>0)
    const tick=frame.tick??Math.round(frame.time/.0001)
    if(odor&&!prior.odor)result.push({type:'odor_detected',tick,slot,values:sense?.odor})
    if(visual&&!prior.visual)result.push({type:'visual_target_detected',tick,slot,values:sense?.visual})
    if(touch&&!prior.touch)result.push({type:'food_contact',tick,slot,mouth_distance:sense?.mouth_distance??undefined})
    const score=frame.scores?.[slot]||0
    if(score>prior.score+.00001)result.push({type:'intake',tick,slot,amount:score-prior.score})
    prior={odor,visual,touch,score}
  }
  return result
}

type Graph=NeuralGraph
type ReplayReceipt={replay_policy?:{event_ticks?:number};schema?:string;sha256?:string;connectome_sha256?:string;neuron_count?:number;edge_count?:number;request?:{bridge_profile?:string;sensory_profile?:string};runtime?:{rules?:{id?:string;feeding_contact?:string;physics_dt?:number;sense_ticks?:number};machine?:string;python?:string;mujoco?:string;bridge_profile?:string;readout_weights_sha256?:string;model?:{id?:string};sensory_profile?:{id?:string}}}
type BrainView='region'|'class'|'local'

export function BrainTheater({frame,frames,season,fly,slot,events,onSeek,activityScale,nodeScale,matchId}:{matchId?:string;frame?:Frame;frames:Frame[];season:Season|null;fly?:ReplayParticipant;slot:number;events:ReplayEvent[];activityScale:number;nodeScale:number;onSeek:(time:number)=>void}) {
  const {t,locale}=useI18n(); const [circuit,setCircuit]=useState('olfactory'); const [graph,setGraph]=useState<Graph|null>(null); const [designWeights,setDesignWeights]=useState(false); const [view,setView]=useState<BrainView>('region'); const [selectedClass,setSelectedClass]=useState<string|null>(null); const [selectedEvent,setSelectedEvent]=useState<ReplayEvent|null>(null); const [responseMs,setResponseMs]=useState(100)
  const circuits=season?.connectome.circuits||[]; const sample=frame?.brain?.[slot];
  const sampleIds=useMemo(()=>{
    const ids=(sample?.sampled_nodes||sample?.top_nodes||[]).map(node=>node.id).filter(Boolean)
    return [...new Set(ids)].join(',')
  },[sample?.sampled_nodes,sample?.top_nodes])
  const snapshot=fly?.brain_graph
  const frozenGraph=snapshot?.schema==='brain-neighborhood/v1'&&snapshot.artifact_id===fly?.artifact_id&&snapshot.connectome_sha256===fly?.spec.connectome_sha256?snapshot.circuits[circuit]:undefined
  // Match-list polling creates fresh objects. Equal recorded graph content
  // must not clear the neuron/class the user is inspecting every 2.5 seconds.
  const frozenGraphContent=useMemo(()=>JSON.stringify(frozenGraph??null),[frozenGraph])
  useEffect(()=>{
    let active=true;const controller=new AbortController();setGraph(null);setSelectedClass(null);setDesignWeights(false)
    if(frozenGraphContent!=='null'){setGraph(JSON.parse(frozenGraphContent) as Graph);setDesignWeights(true);return()=>{active=false;controller.abort()}}
    const query='/connectome/neurons?circuit='+encodeURIComponent(circuit)+(sampleIds?'&ids='+encodeURIComponent(sampleIds)+'&limit=80':'&limit=80')
    async function load(){
      if(matchId&&fly&&sampleIds){
        try{
          const snapshot=await api<BrainDesignGraph>('/matches/'+encodeURIComponent(matchId)+'/brain/'+slot+'?ids='+encodeURIComponent(sampleIds),{signal:controller.signal})
          if(snapshot.artifact_id!==fly.artifact_id||snapshot.connectome_sha256!==fly.spec.connectome_sha256)throw new Error('Replay brain identity mismatch')
          if(!snapshot.circuits[circuit])throw new Error('Replay circuit unavailable')
          if(active){setGraph(snapshot.circuits[circuit]);setDesignWeights(true)}
          return
        }catch{if(!active)return}
      }
      try{const value=await api<Graph>(query,{signal:controller.signal});if(active)setGraph(value)}catch{if(active)setGraph(null)}
    }
    void load();return()=>{active=false;controller.abort()}
  },[circuit,sampleIds,frozenGraphContent,matchId,slot,fly?.artifact_id,fly?.spec.connectome_sha256])

  const activity=useMemo(()=>new Map((sample?.sampled_nodes||sample?.top_nodes||[]).map(n=>[n.id,n.activity])),[sample])
  const mutations=fly?.spec?.weight_mutations; const edited=Array.isArray(mutations)&&mutations.some(m=>m.selector===circuit)
  const nodes=graph?.neurons||[]; const classes=useMemo(()=>{const groups=new Map<string,{count:number;recorded:number;active:number;peak:number|null}>();for(const node of nodes){const key=node.class||node.type||'unannotated';const prior=groups.get(key)||{count:0,recorded:0,active:0,peak:null};const value=activity.get(node.id);prior.count+=1;if(value!==undefined&&Number.isFinite(value)){prior.recorded+=1;prior.active+=value>0?1:0;prior.peak=Math.max(prior.peak??0,value)}groups.set(key,prior)}return [...groups.entries()].sort((a,b)=>(b[1].peak??-1)-(a[1].peak??-1))},[nodes,activity]);

  const eventName=(e:ReplayEvent)=>({odor_detected:t('Odor detected'),visual_target_detected:t('Visual target detected'),food_contact:t('Food contact'),environment_contact:t('Environment contact'),intake:t('Food intake'),exit:t('Boundary exit'),contact:t('Fly contact')}[e.type]||e.type)
  useEffect(()=>setSelectedEvent(null),[slot,frames])
  return <section className="brain-theater panel">
    <div className="panel-heading"><span><AudioLines size={16}/>{t('Neural theatre')}</span><small>{t('Recorded activity · selectable circuit')}</small></div>
    <div className="brain-circuit-tabs">{circuits.map(c=><button key={c.id} className={circuit===c.id?'active':''} onClick={()=>{setCircuit(c.id);setView('region')}} style={{color:c.color}}>{t(c.label)}{edited&&circuit===c.id?<small> · {t('edited')}</small>:null}</button>)}</div>
    <div className="brain-layer-tabs" role="tablist" aria-label={t('Brain view')}><button className={view==='region'?'active':''} onClick={()=>setView('region')}>{t('Functional region')}</button><button className={view==='class'?'active':''} onClick={()=>setView('class')}>{t('Neuron class')}</button><button className={view==='local'?'active':''} onClick={()=>setView('local')}>{t('Local graph')}</button></div>
    {view==='region'&&<BrainActivityOverview circuits={circuits} activity={sample?.circuits||frame?.traces?.[slot]||{}} scale={activityScale} mutations={Array.isArray(mutations)?mutations:[]} time={frame?.time} onOpen={id=>{setCircuit(id);setSelectedClass(null);setView('class')}}/>}
    {view==='region'&&<div className="brain-region-summary"><div><strong>{t(circuits.find(c=>c.id===circuit)?.label||circuit)}</strong><span>{t('Recorded functional region')}</span></div><div><strong>{season?.connectome.circuits.find(c=>c.id===circuit)?.neuron_count?.toLocaleString()||'—'}</strong><span>{t('canonical neurons')}</span></div><div><strong>{nodes.filter(n=>activity.has(n.id)).length}</strong><span>{t('sampled in this frame')}</span></div><button onClick={()=>setView('class')}>{t('Open neuron classes')} →</button></div>}
    {view==='class'&&<div className="brain-class-list">{classes.length?classes.map(([name,summary])=><button key={name} className={selectedClass===name?'active':''} onClick={()=>{setSelectedClass(name);setView('local')}}><span><strong>{name}</strong><small>{summary.recorded}/{summary.count} {locale==='zh-CN'?'已记录':'recorded'} · {summary.active} {t('active')}</small></span><b>{summary.peak===null?'—':summary.peak.toFixed(2)}</b></button>):<p className="empty">{t('No annotated neuron classes in this sample.')}</p>}</div>}
    {view==='local'&&<div className="brain-local-heading"><span>{selectedClass||t('All displayed classes')}</span><button onClick={()=>setView('class')}>{t('Back to classes')}</button></div>}
    {view==='local'&&graph&&!designWeights&&<p className="training-hint">{locale==='zh-CN'?'当前显示基础连接结构；这份回放的设计权重尚未载入。活动仍来自实际回放记录。':'Showing canonical connection structure; this replay’s design weights are unavailable. Activity still comes from the recorded replay.'}</p>}
    {view==='local'&&(graph?<LocalBrainGraph graph={graph} activity={activity} scale={nodeScale} selectedClass={selectedClass}/>:<p className="empty">{t('Loading canonical neuron sample…')}</p>)}
    <div className="sensory-strip"><div><span>{t('Sensory profile')}</span><strong>{frame?.senses?.[slot]?.sensory_profile||'odor-only-v1'}</strong><small>{t('Versioned neural input')}</small></div><div><span>{t('Odor L / R')}</span><strong>{frame?.senses?.[slot]?.odor.map(v=>v.toFixed(2)).join(' / ')||'—'}</strong></div><div><span>{t('Visual L / R')}</span><strong>{frame?.senses?.[slot]?.visual.map(v=>v.toFixed(2)).join(' / ')||'—'}</strong><small>{frame?.senses?.[slot]?.visual_status?.includes('engineered')?t('geometric observation'):''}</small></div><div><span>{t('Touch')}</span><strong>{frame?.senses?.[slot]?.touch?'ON':'—'}</strong><small>{frame?.senses?.[slot]?.touch_status?.includes('mujoco')?t('MuJoCo contact observation'):''}</small></div><div><span>{t('Nearest food')}</span><strong>{frame?.senses?.[slot]?.nearest_food==null?'—':frame.senses[slot].nearest_food.toFixed(1)+' mm'}</strong></div></div>
    {frame?.senses?.[slot]?.contact_environment!==undefined&&<div className="sensory-strip"><div><span>{t('Contacted environment')}</span><strong>{frame.senses[slot].contact_environment?.join(' · ')||t('No contact')}</strong><small>{t('Ground support excluded')}</small></div><div><span>{t('Tactile population activity')}</span><strong>{frame.senses[slot].tactile_activity==null?'—':frame.senses[slot].tactile_activity.toFixed(3)}</strong><small>{t('Recorded population mean · model activity')}</small></div></div>}
    {frame?.senses?.[slot]?.contact_support!==undefined&&<div className="sensory-strip support-contact" aria-label={locale==='zh-CN'?'支撑与侧向接触':'Support and lateral contact'}><div><span>{locale==='zh-CN'?'足部向上支撑':'Upward foot support'}</span><strong>{frame.senses[slot].contact_support?.join(' · ')||t('No contact')}</strong><small>{locale==='zh-CN'?'实际地形接触；这一模式不把支撑送入左右避障触觉。':'Actual terrain contact; this profile excludes support from lateral avoidance input.'}</small></div><div><span>{locale==='zh-CN'?'送入左右触觉的接触':'Contacts sent to lateral touch'}</span><strong>{[...new Set(Object.values(frame.senses[slot].contact_environment_sides||{}).flat())].join(' · ')||t('No contact')}</strong><small>{locale==='zh-CN'?'侧撞、下表面卡住、身体与对手接触仍保留。':'Side, underside, non-foot and opponent contact remain.'}</small></div></div>}
    {frame?.senses?.[slot]?.contact_activity&&<div className="sensory-strip contact-context" aria-label={t('Separate contact responses')}>{(['taste','touch_left','touch_right'] as const).map(key=>{const sense=frame.senses![slot],value=sense.contact_activity?.[key];return <div key={key}><span>{t({taste:'Food taste',touch_left:'Left environmental touch',touch_right:'Right environmental touch'}[key])}</span><strong>{value==null?'—':value.toFixed(3)}</strong><small>{t('Recorded population mean · model activity')} · {t('Input')} {sense[key]===undefined?'—':sense[key].toFixed(0)}</small></div>})}</div>}
    {selectedEvent&&(()=>{const window=eventSampleWindow(frames,selectedEvent,responseMs);if(!window)return null;const before=window.before,after=window.after;const changes=circuits.map(c=>({id:c.id,label:c.label,color:c.color,before:before.traces?.[slot]?.[c.id],after:after.traces?.[slot]?.[c.id]})).filter(c=>c.before!==undefined||c.after!==undefined);const beforeSense=before.senses?.[slot],afterSense=after.senses?.[slot];const delta=(a:number|undefined,b:number|undefined)=>a===undefined||b===undefined?'—':`${b-a>=0?'+':''}${(b-a).toFixed(2)}`;const eventName=(e:ReplayEvent)=>({odor_detected:t('Odor detected'),visual_target_detected:t('Visual target detected'),food_contact:t('Food contact'),environment_contact:t('Environment contact'),intake:t('Food intake'),exit:t('Boundary exit'),contact:t('Fly contact')}[e.type]||e.type);return <div className="event-response"><div className="event-response-heading"><span><strong>{eventName(selectedEvent)}</strong><small>{locale==='zh-CN'?'记录响应窗口':'Recorded response window'} · {(selectedEvent.tick*.0001).toFixed(2)}s</small></span><button onClick={()=>setSelectedEvent(null)}>×</button></div><label className="event-response-window"><span>{locale==='zh-CN'?'响应观察窗口':'Response observation window'}</span><select aria-label={locale==='zh-CN'?'响应观察窗口':'Response observation window'} value={responseMs} onChange={e=>{const delay=Number(e.target.value);setResponseMs(delay);const range=eventSampleWindow(frames,selectedEvent,delay);if(range)onSeek(range.after.time)}}>{[0,100,500].map(ms=><option key={ms} value={ms}>{ms===0?(locale==='zh-CN'?'事件后首次采样':'First post-event sample'):`${ms} ms`}</option>)}</select></label><div className="event-response-times"><span>{locale==='zh-CN'?'事件前':'Before'} <b>{before.time.toFixed(2)}s</b></span><span>{locale==='zh-CN'?'事件后':'After'} <b>{after.time.toFixed(2)}s</b></span></div><div className="event-response-grid">{changes.slice(0,8).map(c=><div key={c.id}><span style={{color:c.color}}>{t(c.label)}</span><b>{shown(c.before,2)} → {shown(c.after,2)}</b><small>Δ {delta(c.before,c.after)} Hz</small></div>)}</div>{(beforeSense||afterSense)&&<div className="event-sensor-delta"><span>{t('Odor L / R')} <b>{beforeSense?.odor.map(v=>v.toFixed(2)).join(' / ')||'—'} → {afterSense?.odor.map(v=>v.toFixed(2)).join(' / ')||'—'}</b></span><span>{t('Visual L / R')} <b>{beforeSense?.visual.map(v=>v.toFixed(2)).join(' / ')||'—'} → {afterSense?.visual.map(v=>v.toFixed(2)).join(' / ')||'—'}</b></span><span>{t('Touch')} <b>{beforeSense?.touch?'ON':'—'} → {afterSense?.touch?'ON':'—'}</b></span><span>{t('Tactile population activity')} <b>{shown(beforeSense?.tactile_activity??undefined,3)} → {shown(afterSense?.tactile_activity??undefined,3)}</b></span>{(beforeSense?.contact_activity||afterSense?.contact_activity)&&(['taste','touch_left','touch_right'] as const).map(key=><span key={key}>{t({taste:'Food taste',touch_left:'Left environmental touch',touch_right:'Right environmental touch'}[key])} <b>{shown(beforeSense?.contact_activity?.[key]??undefined,3)} → {shown(afterSense?.contact_activity?.[key]??undefined,3)}</b></span>)}<span>{t('Left / right motor drive')} <b>{before.drives?.[slot]?.map(v=>v.toFixed(3)).join(' / ')||'—'} → {after.drives?.[slot]?.map(v=>v.toFixed(3)).join(' / ')||'—'}</b></span></div>}<small className="event-response-note">{locale==='zh-CN'?'这些数值来自事件前及所选响应窗口的实际采样；它们描述时间上的观测变化，不自动宣称因果。':'Values are the actual samples in the selected response window; they describe an observed temporal change and do not by themselves claim causality.'}</small></div>})()}
    <LifeEventTimeline events={events} slot={slot} time={frame?.time??0} label={eventName} onSelect={event=>{
      setSelectedEvent(event)
      const window=eventSampleWindow(frames,event,responseMs)
      if(window)onSeek(window.after.time)
    }}/>

  </section>
}

export function MatchObservations({scene,frame,frames,events=[],flies,selectedId,season,match,onSeek=()=>{},onObserveFly,onDesignReplay}:{scene:Scene;frame?:Frame;frames:Frame[];events?:ReplayEvent[];flies:Fly[];selectedId:string;season:Season|null;match?:Match;onSeek?:((time:number)=>void);onObserveFly?:((id:string)=>void);onDesignReplay?:(draft:Spec,origin:ReplayDesignOrigin)=>void}) {
  const {t,locale}=useI18n()
  const [slot,setSlot]=useState(()=>Math.max(0,scene.flies.findIndex(f=>f.id===selectedId)))
  useEffect(()=>setSlot(Math.max(0,scene.flies.findIndex(f=>f.id===selectedId))),[selectedId,scene.flies])
  const [compare,setCompare]=useState(false)
  const [receipt,setReceipt]=useState<ReplayReceipt|null>(null)
  useEffect(()=>{
    if(!match?.id){setReceipt(null);return}
    const controller=new AbortController();let active=true
    api<ReplayReceipt>('/matches/'+encodeURIComponent(match.id)+'/receipt',{signal:controller.signal}).then(value=>{if(active)setReceipt(value)}).catch(()=>{if(active)setReceipt(null)})
    return()=>{active=false;controller.abort()}
  },[match?.id])
  // Exported designs belong to this run; they take precedence over the live library.
  const recordedFlies:ReplayParticipant[]=[...(match?.participants||[]),...flies]
  const participant=scene.flies[slot],fly=recordedFlies.find(f=>f.id===participant?.id)
  const parent=recordedFlies.find(f=>f.id===fly?.spec.parent_id)
  const circuits=season?.connectome.circuits||[]
  // Keep both flies on fixed scales while seeking. Group means and individual
  // neuron peaks have separate scales so a single spike cannot wash out the map.
  const activityScales=useMemo(()=>{
    let region=1,node=1
    for(const item of frames){
      for(const trace of item.traces||[])for(const value of Object.values(trace))if(Number.isFinite(value))region=Math.max(region,value)
      for(const sample of item.brain||[]){
        for(const value of Object.values(sample.circuits||{}))if(Number.isFinite(value))region=Math.max(region,value)
        for(const point of sample.sampled_nodes||sample.top_nodes||[])if(Number.isFinite(point.activity))node=Math.max(node,point.activity)
      }
    }
    return {region,node}
  },[frames])
  const visibleEvents=useMemo(()=>events.length?events:scene.flies.flatMap((_,index)=>deriveEvents(frames,index)),[events,frames,scene.flies])
  function download(){
    const payload={schema_version:'match-observations/v2',match_id:match?.id,request:match?.request,result:match?.result,
      receipt_sha256:match?.result?.receipt_sha256||null,events:visibleEvents,
      units:{time:'seconds',position:'mm',circuit_activity:'Hz',neuron_activity:'model-native activity',energy:'game reserve units',score:'food units',touch:'MuJoCo contact boolean'},
      scope:'Recorded circuit averages, fixed canonical neuron samples, sensor provenance and body observations. This export does not contain all 165,122 neuron traces; the immutable run assets remain the research source.',
      participants:scene.flies.map((entry,slot)=>({slot,...entry,spec:recordedFlies.find(f=>f.id===entry.id)?.spec||null})),
      samples:frames.map(({time,tick,positions,scores,energy,food,drives,traces,brain,senses})=>({time,tick,positions,scores,energy,food,drives,traces,brain,senses}))}
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}))
      const link=document.createElement('a');link.href=url;link.download=`fly-arena-${match?.id||'match'}-observations.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  function participantCard(index:number){
    const entry=scene.flies[index]
    const subjectFly=recordedFlies.find(f=>f.id===entry?.id)
    const color=colors[entry?.color]||colors.mint
    const circuitPeak=(id:string)=>Math.max(1,...frames.map(f=>f.traces?.[index]?.[id]??0))
    const scorePeak=Math.max(1,...frames.map(f=>f.scores?.[index]??0))
    return <div className="observation-participant" key={entry?.id||index}>
      <div className="observation-participant-heading"><span><i style={{background:color}}/>{t('Slot')} {index+1} · {entry?.name}</span><small>{entry?.id.slice(0,8)}</small></div>
      {match&&<ReplayDesignActions participant={match.participants?.find(f=>f.id===entry.id)} matchId={match.id} onDesign={onDesignReplay}/>}
      <BrainTheater matchId={match?.id} frame={frame} frames={frames} season={season} fly={subjectFly} slot={index} events={visibleEvents} onSeek={onSeek} activityScale={activityScales.region} nodeScale={activityScales.node}/>
      <FeedingHistory events={events} scene={scene} slot={index} endTime={frames.at(-1)?.time??0} time={frame?.time??0} physicsDt={receipt?.runtime?.rules?.physics_dt??null} accountingTicks={receipt?.replay_policy?.event_ticks??null} onSeek={onSeek}/>
      <BehaviorFitness metric={match?.result?.behavior?.[index]}/>
      <BehaviorChapters scene={scene} frame={frame} frames={frames} events={visibleEvents} slot={index} time={frame?.time??0} onSeek={onSeek}/>
      <ResponseStory frames={frames} events={visibleEvents} slot={index} time={frame?.time??0} onSeek={onSeek}
        physicsDt={receipt?.runtime?.rules?.physics_dt??null}
        inputInterval={receipt?.runtime?.rules?.physics_dt&&receipt?.runtime?.rules?.sense_ticks?receipt.runtime.rules.physics_dt*receipt.runtime.rules.sense_ticks:null}/>
      <div className="observation-metrics"><div><span>{t('Food collected')}</span><strong>{shown(frame?.scores?.[index],2)}</strong><svg viewBox="0 0 240 52" role="img" aria-label={t('Food score over time')}><path d={tracePath(frames,f=>f.scores?.[index],scorePeak)} fill="none" stroke={color} strokeWidth="2"/></svg></div><div><span>{t('Energy reserve')}</span><strong>{shown(frame?.energy?.[index])}</strong><svg viewBox="0 0 240 52" role="img" aria-label={t('Energy over time')}><path d={tracePath(frames,f=>f.energy?.[index],Math.max(100,...frames.map(f=>f.energy?.[index]??0)))} fill="none" stroke={color} strokeWidth="2"/></svg></div><div><span>{t('Left / right motor drive')}</span><strong>{shown(frame?.drives?.[index]?.[0],2)} / {shown(frame?.drives?.[index]?.[1],2)}</strong><small>{t('Recorded at')} {shown(frame?.time,2)} s</small></div></div>
      {scene.habitat==='forest-floor'&&<div className="observation-metrics"><div><span>{locale==='zh-CN'?'胸部高度 · mm':'Thorax height · mm'}</span><strong>{shown(frame?.positions?.[index]?.[2],2)}</strong><svg viewBox="0 0 240 52" role="img" aria-label={locale==='zh-CN'?'记录到的身体高度':'Recorded body height'}><path d={tracePath(frames,f=>f.positions?.[index]?.[2],Math.max(1,...frames.map(f=>f.positions?.[index]?.[2]??0)))} fill="none" stroke={color} strokeWidth="2"/></svg><small>{locale==='zh-CN'?'世界坐标 Z；高度变化也可能来自姿态变化或翻倒。':'World Z; height changes may also reflect posture or a fall.'}</small></div></div>}
      <div className="trace-circuits">{circuits.map(c=><div key={c.id}><span style={{color:c.color}}>{t(c.label)}</span><strong>{shown(frame?.traces?.[index]?.[c.id])}<small> Hz</small></strong><svg viewBox="0 0 240 52" role="img" aria-label={`${t(c.label)} · Hz`}><path fill="none" stroke={c.color} strokeWidth="1.8" d={tracePath(frames,f=>f.traces?.[index]?.[c.id],circuitPeak(c.id))}/></svg><small>0–{circuitPeak(c.id).toFixed(1)} Hz</small></div>)}</div>
    </div>
  }
  const connectomeIds=[...new Set(scene.flies.map(entry=>recordedFlies.find(f=>f.id===entry.id)?.spec.connectome_sha256).filter(Boolean))]
  const modelIds=[...new Set(scene.flies.map(entry=>recordedFlies.find(f=>f.id===entry.id)?.spec.model_profile).filter(Boolean))]
  const mutationSummary=scene.flies.map((entry,index)=>{
    const subject=recordedFlies.find(f=>f.id===entry.id)
    const spec=subject?.spec
    if(!spec)return `${t('Slot')} ${index+1}: ${t('No saved FlySpec')}`
    const mutations=Array.isArray(spec.weight_mutations)?spec.weight_mutations:[]
    const edgeDeltas=Array.isArray(spec.edge_deltas)?spec.edge_deltas:[]
    const parameters=spec.neuron_parameters||{tau_scale:1,threshold_shift_mv:0}
    const circuits=mutations.length?mutations.map(item=>`${item.selector} ×${item.scale.toFixed(3)}`).join(' · '):t('canonical')
    const edges=edgeDeltas.length?`${edgeDeltas.length} ${t('edge deltas')}`:''
    const intrinsic=`τ ×${parameters.tau_scale.toFixed(3)} · Δthreshold ${parameters.threshold_shift_mv.toFixed(3)} mV`
    return `${t('Slot')} ${index+1} ${entry.name}: ${circuits}${edges?' · '+edges:''} · ${intrinsic}`
  })
  const request=match?.request
  const runtime=receipt?.runtime
  return <section className="trace-panel panel observations">
    {match?.source?.description?.[locale]&&<details className="replay-story"><summary>{locale==='zh-CN'?'回放说明与对照':'Replay explanation and comparisons'}</summary><p>{match.source.description[locale]}</p>{match.source.comparison_match&&<a href={'#tab=arena&match='+encodeURIComponent(match.source.comparison_match)}>{locale==='zh-CN'?'打开同条件对照回放':'Open the matched comparison replay'} →</a>}{match.source.comparison_links?.map(link=><a key={link.match_id} href={'#tab=arena&match='+encodeURIComponent(link.match_id)}>{link.label[locale]} →</a>)}</details>}
    <div className="panel-heading"><span><AudioLines size={16}/>{t('Neural & behavior records')}</span><button className="text-link" onClick={download}><ArrowDownToLine size={14}/>{t('Export records')}</button></div>
    <div className="observation-subjects" role="group" aria-label={t('Observed fly')}>{scene.flies.map((entry,i)=><button key={i} className={!compare&&slot===i?'active':''} aria-pressed={!compare&&slot===i} onClick={()=>{setCompare(false);setSlot(i);onObserveFly?.(entry.id)}}><i style={{background:colors[entry.color]}}/>{t('Slot')} {i+1} · {entry.name}<small>{entry.id.slice(0,8)}</small></button>)}{scene.flies.length>1&&<button className={'comparison-toggle '+(compare?'active':'')} aria-pressed={compare} onClick={()=>setCompare(value=>!value)}>{compare?t('Focus one fly'):t('Compare participants')}</button>}</div>
    {compare?<div className="observation-comparison">{scene.flies.map((_,index)=>participantCard(index))}</div>:participantCard(slot)}
    {request?.mode!=='sumo'&&<details className="replay-analysis"><summary>{locale==='zh-CN'?'共享食物与资源变化':'Shared food and resource history'}</summary><SharedResources scene={scene} frame={frame} frames={frames} onSeek={onSeek}/></details>}
    <details className="replay-provenance"><summary>{t('Replay provenance')} <small>{receipt?t('Receipt loaded'):t('Receipt unavailable')}</small></summary><div className="provenance-grid"><div><span>{t('Map / mode / seed')}</span><strong>{request?`${request.map_id} · ${request.mode} · ${request.seed}`:t('Unavailable')}</strong></div><div><span>{t('Duration')}</span><strong>{request?`${request.duration_seconds} s`:t('Unavailable')}</strong></div><div><span>{t('Connectome')}</span><strong title={connectomeIds[0]||''}>{connectomeIds.length===1?connectomeIds[0]?.slice(0,16):connectomeIds.length?`${connectomeIds.length} ${t('variants')}`:t('Unavailable')}</strong></div><div><span>{t('Model')}</span><strong>{modelIds.length===1?modelIds[0]:modelIds.length?`${modelIds.length} ${t('variants')}`:runtime?.model?.id||t('Unavailable')}</strong></div><div><span>{t('Sensory profile')}</span><strong>{request?.sensory_profile||runtime?.sensory_profile?.id||t('Unavailable')}</strong></div><div><span>{t('Runtime')}</span><strong>{runtime?.mujoco||t('Unavailable')} · {runtime?.machine||'—'}</strong></div><div><span>{t('Feeding rule')}</span><strong>{runtime?.rules?.feeding_contact==='mujoco-mouth-probe-required-v1'?t('Physical food contact required'):runtime?.rules?.id==='arena-ground-v1'?t('Legacy distance and height'):t('Unavailable')}</strong></div><div><span>{t('Decoder')}</span><strong>{runtime?.readout_weights_sha256?runtime.readout_weights_sha256.slice(0,16):t('Unavailable')}</strong></div><div><span>{t('Receipt')}</span><strong title={receipt?.sha256||match?.result?.receipt_sha256||''}>{(receipt?.sha256||match?.result?.receipt_sha256||'').slice(0,16)||t('Unavailable')}</strong></div><div className="provenance-wide"><span>{t('Design mutations')}</span>{mutationSummary.map((summary,index)=><strong key={index}>{summary}</strong>)}</div></div><small className="provenance-note">{t('Values come from the match request, saved FlySpec and immutable receipt. Missing runtime fields stay unavailable.')}</small></details>
    <div className="observation-lineage"><GitBranch size={16}/><span>{t('Parent design')}: <strong>{fly?.spec.parent_id?`${parent?.name||t('Unavailable')} · ${fly.spec.parent_id.slice(0,8)}`:fly?t('Founder / no parent'):t('Not recorded')}</strong></span><span>{t('Mutation budget')}: {shown(fly?.report?.budget_used)} / {fly?.report?.budget_limit??'—'}</span></div>
    <p className="observation-note">{frames.length} {t('recorded samples')} · {frames[0]?.time.toFixed(2)}–{frames.at(-1)?.time.toFixed(2)} s · {t('Circuit averages; each chart uses its own scale. Energy is a game reserve, not metabolic measurement.')}</p>
  </section>
}
