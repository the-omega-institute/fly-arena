import {useEffect,useMemo,useState} from 'react'
import {ArrowDownToLine,AudioLines,GitBranch} from 'lucide-react'
import {api} from '../../api'
import type {Fly,Frame,Match,ReplayEvent,Scene,Season} from '../../types'
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

function deriveEvents(frames:Frame[],slot:number):ReplayEvent[] {
  const result:ReplayEvent[]=[]; let prior={odor:false,visual:false,touch:false,score:0}
  for(const frame of frames){
    const sense=frame.senses?.[slot]; const odor=!!sense&&sense.odor.reduce((a,b)=>a+b,0)>.04
    const visual=!!sense&&Math.max(...sense.visual)>.05; const touch=!!sense&&sense.touch>0
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

type Graph={neurons:{id:string;type:string;side?:string|null;class?:string;nt?:string|null}[];edges:{pre:string;post:string;count:number;edge:number}[]}
type BrainView='region'|'class'|'local'

function BrainTheater({frame,season,fly,slot,events,onSeek}:{frame?:Frame;season:Season|null;fly?:Fly;slot:number;events:ReplayEvent[];onSeek:(time:number)=>void}) {
  const {t}=useI18n(); const [circuit,setCircuit]=useState('olfactory'); const [graph,setGraph]=useState<Graph|null>(null); const [view,setView]=useState<BrainView>('region'); const [selectedClass,setSelectedClass]=useState<string|null>(null)
  const circuits=season?.connectome.circuits||[]; const sample=frame?.brain?.[slot];
  useEffect(()=>{let active=true;setSelectedClass(null);api<Graph>('/connectome/neurons?circuit='+encodeURIComponent(circuit)+'&limit=80').then(v=>{if(active)setGraph(v)}).catch(()=>{if(active)setGraph(null)});return()=>{active=false}},[circuit])
  const activity=useMemo(()=>new Map((sample?.sampled_nodes||sample?.top_nodes||[]).map(n=>[n.id,n.activity])),[sample])
  const max=Math.max(1,...activity.values()); const mutations=fly?.spec?.weight_mutations; const edited=Array.isArray(mutations)&&mutations.some(m=>m.selector===circuit)
  const nodes=graph?.neurons||[]; const classes=useMemo(()=>{const groups=new Map<string,{count:number;active:number;peak:number}>();for(const node of nodes){const key=node.class||node.type||'unannotated';const prior=groups.get(key)||{count:0,active:0,peak:0};const value=activity.get(node.id)||0;prior.count+=1;prior.active+=value>0?1:0;prior.peak=Math.max(prior.peak,value);groups.set(key,prior)}return [...groups.entries()].sort((a,b)=>b[1].peak-a[1].peak)},[nodes,activity]);
  const visibleNodes=selectedClass?nodes.filter(n=>(n.class||n.type||'unannotated')===selectedClass):nodes; const visibleIds=new Set(visibleNodes.map(n=>n.id)); const visibleEdges=(graph?.edges||[]).filter(e=>visibleIds.has(e.pre)&&visibleIds.has(e.post)); const point=(i:number)=>({x:20+(i%12)*42,y:30+Math.floor(i/12)*30})
  const eventRows=events.filter(e=>e.slot===undefined||e.slot===slot).slice(-12)
  const eventName=(e:ReplayEvent)=>({odor_detected:t('Odor detected'),visual_target_detected:t('Visual target detected'),food_contact:t('Food contact'),intake:t('Food intake'),exit:t('Boundary exit'),contact:t('Fly contact')}[e.type]||e.type)
  return <section className="brain-theater panel">
    <div className="panel-heading"><span><AudioLines size={16}/>{t('Neural theatre')}</span><small>{t('Recorded activity · selectable circuit')}</small></div>
    <div className="sensory-strip"><div><span>{t('Sensory profile')}</span><strong>{frame?.senses?.[slot]?.sensory_profile||'odor-only-v1'}</strong><small>{t('Versioned neural input')}</small></div><div><span>{t('Odor L / R')}</span><strong>{frame?.senses?.[slot]?.odor.map(v=>v.toFixed(2)).join(' / ')||'—'}</strong></div><div><span>{t('Visual L / R')}</span><strong>{frame?.senses?.[slot]?.visual.map(v=>v.toFixed(2)).join(' / ')||'—'}</strong><small>{frame?.senses?.[slot]?.visual_status?.includes('engineered')?t('geometric observation'):''}</small></div><div><span>{t('Touch')}</span><strong>{frame?.senses?.[slot]?.touch?'ON':'—'}</strong><small>{frame?.senses?.[slot]?.touch_status?.includes('mujoco')?t('MuJoCo contact observation'):''}</small></div><div><span>{t('Nearest food')}</span><strong>{frame?.senses?.[slot]?.nearest_food==null?'—':frame.senses[slot].nearest_food.toFixed(1)+' mm'}</strong></div></div>
    <div className="brain-circuit-tabs">{circuits.map(c=><button key={c.id} className={circuit===c.id?'active':''} onClick={()=>{setCircuit(c.id);setView('region')}} style={{color:c.color}}>{t(c.label)}{edited&&circuit===c.id?<small> · {t('edited')}</small>:null}</button>)}</div>
    <div className="brain-layer-tabs" role="tablist" aria-label={t('Brain view')}><button className={view==='region'?'active':''} onClick={()=>setView('region')}>{t('Functional region')}</button><button className={view==='class'?'active':''} onClick={()=>setView('class')}>{t('Neuron class')}</button><button className={view==='local'?'active':''} onClick={()=>setView('local')}>{t('Local graph')}</button></div>
    {view==='region'&&<div className="brain-region-summary"><div><strong>{t(circuits.find(c=>c.id===circuit)?.label||circuit)}</strong><span>{t('Recorded functional region')}</span></div><div><strong>{season?.connectome.circuits.find(c=>c.id===circuit)?.neuron_count?.toLocaleString()||'—'}</strong><span>{t('canonical neurons')}</span></div><div><strong>{nodes.filter(n=>activity.has(n.id)).length}</strong><span>{t('sampled in this frame')}</span></div><button onClick={()=>setView('class')}>{t('Open neuron classes')} →</button></div>}
    {view==='class'&&<div className="brain-class-list">{classes.length?classes.map(([name,summary])=><button key={name} className={selectedClass===name?'active':''} onClick={()=>{setSelectedClass(name);setView('local')}}><span><strong>{name}</strong><small>{summary.count} {t('display neurons')} · {summary.active} {t('active')}</small></span><b>{summary.peak.toFixed(2)}</b></button>):<p className="empty">{t('No annotated neuron classes in this sample.')}</p>}</div>}
    {view==='local'&&<div className="brain-local-heading"><span>{selectedClass||t('All displayed classes')} · {visibleNodes.length} {t('display neurons')}</span><button onClick={()=>setView('class')}>{t('Back to classes')}</button></div>}
    <div className="brain-graph-wrap">{graph?<svg className="brain-graph" viewBox="0 0 500 280" role="img" aria-label={t('Recorded neural activity graph')}>
      {visibleEdges.slice(0,260).map((e,i)=>{const a=visibleNodes.findIndex(n=>n.id===e.pre),b=visibleNodes.findIndex(n=>n.id===e.post);if(a<0||b<0)return null;const pa=point(a),pb=point(b);return <line key={i} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} stroke="#8b9b8a" strokeOpacity=".16" strokeWidth={Math.min(2,Math.max(.35,e.count/30))}/>})}
      {visibleNodes.map((n,i)=>{const p=point(i),value=activity.get(n.id)||0;return <g key={n.id}><circle cx={p.x} cy={p.y} r={value?4.5:2.7} fill={value?`hsl(${145-(value/max)*115} 75% 57%)`:'#7e8e80'} opacity={value?.9:.52}/><title>{n.id} · {n.class||n.type} · {value.toFixed(2)} Hz</title></g>})}
    </svg>:<p className="empty">{t('Loading canonical neuron sample…')}</p>}<div className="brain-legend"><span><i className="legend-dot quiet"/>{t('Recorded sample node')}</span><span><i className="legend-dot hot"/>{t('Active in this frame')}</span><span>{t('Edges are a display sample; simulation uses the full graph.')}</span></div></div>
    <div className="event-timeline"><strong>{t('Life events')}</strong>{eventRows.length?eventRows.map((e,i)=><button key={i} onClick={()=>onSeek(e.tick*.0001)}><span>{(e.tick*.0001).toFixed(2)}s</span>{eventName(e)}</button>):<small>{t('No threshold event was recorded in this replay window.')}</small>}</div>
  </section>
}

export function MatchObservations({scene,frame,frames,events=[],flies,selectedId,season,match,onSeek=()=>{}}:{scene:Scene;frame?:Frame;frames:Frame[];events?:ReplayEvent[];flies:Fly[];selectedId:string;season:Season|null;match?:Match;onSeek?:((time:number)=>void)}) {
  const {t,locale}=useI18n()
  const [slot,setSlot]=useState(()=>Math.max(0,scene.flies.findIndex(f=>f.id===selectedId)))
  const participant=scene.flies[slot],fly=flies.find(f=>f.id===participant?.id)
  const parent=flies.find(f=>f.id===fly?.spec.parent_id)
  const circuits=season?.connectome.circuits||[]
  const visibleEvents=events.length?events:deriveEvents(frames,slot)
  const circuitPeak=(id:string)=>Math.max(1,...frames.map(f=>f.traces?.[slot]?.[id]??0))
  const scorePeak=Math.max(1,...frames.map(f=>f.scores?.[slot]??0))
  const color=colors[participant?.color]||colors.mint
  function download(){
    const payload={schema_version:'match-observations/v2',match_id:match?.id,request:match?.request,result:match?.result,
      receipt_sha256:match?.result?.receipt_sha256||null,events:visibleEvents,
      units:{time:'seconds',position:'mm',circuit_activity:'Hz',neuron_activity:'model-native activity',energy:'game reserve units',score:'food units',touch:'MuJoCo contact boolean'},
      scope:'Recorded circuit averages, fixed canonical neuron samples, sensor provenance and body observations. This export does not contain all 165,122 neuron traces; the immutable run assets remain the research source.',
      participants:scene.flies.map((entry,slot)=>({slot,...entry,spec:flies.find(f=>f.id===entry.id)?.spec||null})),
      samples:frames.map(({time,tick,positions,scores,energy,food,drives,traces,brain,senses})=>({time,tick,positions,scores,energy,food,drives,traces,brain,senses}))}
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}))
    const link=document.createElement('a');link.href=url;link.download=`fly-arena-${match?.id||'match'}-observations.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <section className="trace-panel panel observations">
    <div className="panel-heading"><span><AudioLines size={16}/>{t('Neural & behavior records')}</span><button className="text-link" onClick={download}><ArrowDownToLine size={14}/>{t('Export records')}</button></div>
    <div className="observation-subjects" role="group" aria-label={t('Observed fly')}>{scene.flies.map((entry,i)=><button key={i} className={slot===i?'active':''} aria-pressed={slot===i} onClick={()=>setSlot(i)}><i style={{background:colors[entry.color]}}/>{t('Slot')} {i+1} · {entry.name}<small>{entry.id.slice(0,8)}</small></button>)}</div>
    <div className="observation-metrics"><div><span>{t('Food collected')}</span><strong>{shown(frame?.scores?.[slot],2)}</strong><svg viewBox="0 0 240 52" role="img" aria-label={t('Food score over time')}><path d={tracePath(frames,f=>f.scores?.[slot],scorePeak)} fill="none" stroke={color} strokeWidth="2"/></svg></div><div><span>{t('Energy reserve')}</span><strong>{shown(frame?.energy?.[slot])}</strong><svg viewBox="0 0 240 52" role="img" aria-label={t('Energy over time')}><path d={tracePath(frames,f=>f.energy?.[slot],Math.max(100,...frames.map(f=>f.energy?.[slot]??0)))} fill="none" stroke={color} strokeWidth="2"/></svg></div><div><span>{t('Left / right motor drive')}</span><strong>{shown(frame?.drives?.[slot]?.[0],2)} / {shown(frame?.drives?.[slot]?.[1],2)}</strong><small>{t('Recorded at')} {shown(frame?.time,2)} s</small></div></div>
    {scene.habitat==='forest-floor'&&<div className="observation-metrics"><div><span>{locale==='zh-CN'?'胸部高度 · mm':'Thorax height · mm'}</span><strong>{shown(frame?.positions?.[slot]?.[2],2)}</strong><svg viewBox="0 0 240 52" role="img" aria-label={locale==='zh-CN'?'记录到的身体高度':'Recorded body height'}><path d={tracePath(frames,f=>f.positions?.[slot]?.[2],Math.max(1,...frames.map(f=>f.positions?.[slot]?.[2]??0)))} fill="none" stroke={color} strokeWidth="2"/></svg><small>{locale==='zh-CN'?'世界坐标 Z；高度变化也可能来自姿态变化或翻倒。':'World Z; height changes may also reflect posture or a fall.'}</small></div></div>}
    <div className="trace-circuits">{circuits.map(c=><div key={c.id}><span style={{color:c.color}}>{t(c.label)}</span><strong>{shown(frame?.traces?.[slot]?.[c.id])}<small> Hz</small></strong><svg viewBox="0 0 240 52" role="img" aria-label={`${t(c.label)} · Hz`}><path fill="none" stroke={c.color} strokeWidth="1.8" d={tracePath(frames,f=>f.traces?.[slot]?.[c.id],circuitPeak(c.id))}/></svg><small>0–{circuitPeak(c.id).toFixed(1)} Hz</small></div>)}</div>
    <BrainTheater frame={frame} season={season} fly={fly} slot={slot} events={visibleEvents} onSeek={onSeek}/>
    <div className="observation-lineage"><GitBranch size={16}/><span>{t('Parent design')}: <strong>{fly?.spec.parent_id?`${parent?.name||t('Unavailable')} · ${fly.spec.parent_id.slice(0,8)}`:fly?t('Founder / no parent'):t('Not recorded')}</strong></span><span>{t('Mutation budget')}: {shown(fly?.report.budget_used)} / {fly?.report.budget_limit??'—'}</span></div>
    <p className="observation-note">{frames.length} {t('recorded samples')} · {frames[0]?.time.toFixed(2)}–{frames.at(-1)?.time.toFixed(2)} s · {t('Circuit averages; each chart uses its own scale. Energy is a game reserve, not metabolic measurement.')}</p>
  </section>
}
