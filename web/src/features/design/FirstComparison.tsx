import {useEffect,useRef,useState} from 'react'
import {api,newRequestKey} from '../../api'
import type {ArenaMap,Fly,Identity,Season} from '../../types'
import {useI18n} from '../../shared/i18n'
import {matchingWildType} from '../arena/wildtype'
import {buildExperimentPlan,type ExperimentPlan} from '../arena/experimentSetup'
import {ObservationDuration} from '../arena/ObservationDuration'
import type {Series} from '../arena/ExperimentSeries'
import {comparisonResult,publicComparisonFlies} from './comparisonSummary'
import './firstComparison.css'

type Request=Extract<ExperimentPlan['submissions'][number],{endpoint:'/tournaments'}>['body']
type Entry={key:string;request:Request;referenceName:string;kind:'wt'|'public';id?:string}
type Attempt={entries:Entry[]}
type Props={subject:Fly;flies:Fly[];maps:ArenaMap[];season:Season|null;identity:Identity;onArena:(series:string,match:string)=>void}

function restore(key:string,subject:Fly):Attempt|null{
 try{
  const value=JSON.parse(localStorage.getItem(key)||'null') as Attempt|null
  if(value&&Array.isArray(value.entries)&&value.entries.length>0&&value.entries.length<=2&&value.entries.every(e=>
   typeof e.key==='string'&&typeof e.referenceName==='string'&&['wt','public'].includes(e.kind)&&
   (e.id===undefined||typeof e.id==='string')&&e.request?.sandbox===true&&e.request.mode==='contest'&&
   e.request.map_id==='orchard'&&e.request.bridge_profile==='legacy-v1'&&e.request.sensory_profile==='odor-only-v1'&&
   Number.isInteger(e.request.duration_seconds)&&e.request.duration_seconds>=1&&e.request.duration_seconds<=180&&
   e.request.fly_ids?.length===2&&e.request.fly_ids[0]===subject.id&&e.request.fly_ids[1]!==subject.id&&
   e.request.seeds?.length===1&&e.request.seeds[0]===42))return value
 }catch{/* A missing or obsolete local draft cannot submit work. */}
 return null
}

export function FirstComparison({subject,flies,maps,season,identity,onArena}:Props){
 const {locale,t}=useI18n(),zh=locale==='zh-CN'
 const storageKey=`flyarena.first-comparison.${identity.id}.${subject.id}`
 const wt=matchingWildType(flies,subject),others=publicComparisonFlies(flies,subject)
 const [useWT,setUseWT]=useState(true),[usePublic,setUsePublic]=useState(true)
 const [publicId,setPublicId]=useState(''),[duration,setDuration]=useState(10)
 const [attempt,setAttempt]=useState<Attempt|null>(()=>restore(storageKey,subject))
 const attemptRef=useRef(attempt),submitting=useRef(false)
 const [busy,setBusy]=useState(false),[error,setError]=useState('')
 const [reports,setReports]=useState<Record<string,Series>>({})
 const publicFly=others.find(f=>f.id===(publicId||others[0]?.id))
 const targets=[...(useWT&&wt&&wt.id!==subject.id?[{fly:wt,kind:'wt' as const}]:[]),...(usePublic&&publicFly?[{fly:publicFly,kind:'public' as const}]:[])]
 const planned=targets.map(({fly,kind})=>({fly,kind,...buildExperimentPlan({selected:subject.id,opponent:fly.id,mapId:'orchard',mode:'contest',seedText:'42',duration,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'},flies,maps,season)}))
 const errors=[...new Set(planned.flatMap(p=>p.errors))]
 const allComplete=!!attempt&&attempt.entries.every(e=>e.id&&reports[e.id]&&comparisonResult(reports[e.id],subject.id))
 const allTerminal=!!attempt&&attempt.entries.every(e=>e.id&&reports[e.id]&&reports[e.id].status!=='running'&&!reports[e.id].schedule.some(leg=>['queued','running'].includes(leg.status)))
 function remember(value:Attempt|null){
  attemptRef.current=value;setAttempt(value)
  try{if(value)localStorage.setItem(storageKey,JSON.stringify(value));else localStorage.removeItem(storageKey)}catch{/* Submitted series remain in the server's series list. */}
 }
 async function start(){
  if(submitting.current)return
  let work:Attempt|null=attemptRef.current
  if(!work){
   if(!planned.length||errors.length)return
   work={entries:planned.map(({plan,fly,kind})=>({key:newRequestKey(),request:plan!.submissions[0].body as Request,referenceName:fly.name,kind}))}
   remember(work)
  }
  submitting.current=true;setBusy(true);setError('')
  try{
   for(let index=0;index<work.entries.length;index++){
    const entry:Entry=work.entries[index];if(entry.id)continue
    const result:Series=await api<Series>('/tournaments',{method:'POST',headers:{'Idempotency-Key':entry.key},body:JSON.stringify(entry.request)},identity)
    if(!result.id)throw Error(zh?'服务器未返回对比记录，请重试原方案。':'No comparison record returned. Retry the same plan.')
    work={entries:work.entries.map((e,i):Entry=>i===index?{...e,id:result.id}:e)}
    remember(work)
   }
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{submitting.current=false;setBusy(false)}
 }
 const reportReceived=(report:Series)=>setReports(old=>({...old,[report.id]:report}))
 return <section className="first-comparison panel" aria-label={zh?'保存后的首次对比':'Compare your saved design'}>
  <header><span className="eyebrow">{zh?'设计已保存 · 下一步':'DESIGN SAVED · NEXT STEP'}</span><h2>{zh?'先看看它与其他果蝇有什么不同':'See how your fly compares'}</h2><p><strong>{subject.name}</strong> · {zh?'这里比较已保存的版本；下方尚未保存的修改不会加入本次对比。':'This compares the saved version. Unsaved edits below are not included.'}</p></header>
  <ol className="first-comparison-steps"><li>{zh?'1 选择对照与时间':'1 Choose references and time'}</li><li>{zh?'2 在这里查看结果':'2 Read results here'}</li><li>{zh?'3 去竞技场继续探索':'3 Explore further in Arena'}</li></ol>
  {!attempt?<>
   <div className="first-comparison-targets">
    <label className="first-comparison-choice"><span><input type="checkbox" checked={useWT&&!!wt&&wt.id!==subject.id} disabled={!wt||wt.id===subject.id} onChange={e=>setUseWT(e.target.checked)}/><strong>{zh?'与 WT 基线相比':'Compare with WT'}</strong></span><p>{zh?'WT 是未修改的模拟参考。看看你的改动是否带来了不同的摄取结果。':'WT is the unmodified simulated reference. Check whether your changes produce different food intake.'}</p><small>{wt&&wt.id!==subject.id?wt.name:zh?'暂无兼容 WT；可以先与其他人的设计比较。':'No compatible WT is available; you can compare with another designer.'}</small></label>
    <div className="first-comparison-choice"><label><input type="checkbox" checked={usePublic&&!!others.length} disabled={!others.length} onChange={e=>setUsePublic(e.target.checked)}/><strong>{zh?'与其他人的果蝇相比':'Compare with another designer'}</strong></label><p>{zh?'选择目前公开、且图谱与神经模型兼容的设计，在相同条件下比较。':'Choose a current public design with the same graph and neural model, then compare under matching conditions.'}</p>{others.length?<select aria-label={zh?'其他人的果蝇':'Another designer’s fly'} value={publicFly?.id||''} disabled={!usePublic} onChange={e=>setPublicId(e.target.value)}>{others.map(f=><option key={f.id} value={f.id}>{f.name} · {f.designer||f.owner.slice(0,8)} · {f.id.slice(0,8)}</option>)}</select>:<p role="status">{zh?'目前没有其他人的兼容公开设计；不会用你自己的果蝇冒充对手。':'No compatible public design from another owner is available yet.'}</p>}</div>
   </div>
   <ObservationDuration value={duration} onChange={setDuration}/>
   <div className="first-comparison-plan"><h3>{zh?'这次会怎样比较':'What this comparison will do'}</h3><p>{zh?'果园 · 食物竞争 · 相同种子 42 · 相同嗅觉输入与运动方案。每个对照交换一次出生位置，减少位置造成的偏差。':'Orchard food competition · seed 42 · identical odor input and motor profile. Each reference is tested in both starting positions to reduce position bias.'}</p><p><strong>{planned.length*2} {zh?'场':'matches'} × {duration} {zh?'模拟秒':'simulated seconds'} = {planned.length*2*duration} {zh?'模拟秒合计':'simulated seconds total'}</strong></p><p>{zh?'先比较两场的平均摄取量，再去回放看发生了什么。这些结果只描述当前条件，不计入公开排行榜。':'Compare mean food intake across both positions, then inspect what happened in the replay. Results describe these conditions and stay outside the public leaderboard.'}</p>{errors.map(e=><p role="status" key={e}>{t(e)}</p>)}{!planned.length&&<p role="status">{zh?'请至少选择一个可用对照。':'Choose at least one available reference.'}</p>}</div>
   <button className="primary" disabled={busy||!planned.length||!!errors.length} onClick={()=>void start()}>{zh?'开始对比，结果显示在这里':'Start comparison · results stay here'}</button>
  </>:<>
   <p>{zh?'对比已准备。每个对照各两场，交换出生位置；关闭或刷新页面不会取消已提交的计算。':'Comparison prepared: two swapped matches per reference. Closing or refreshing this page does not cancel submitted work.'}</p>
   <div className="first-comparison-results">{attempt.entries.map(entry=><ComparisonReport key={entry.key} entry={entry} subject={subject} onReport={reportReceived} onArena={onArena}/>)}</div>
   {attempt.entries.some(e=>!e.id)&&<button className="primary" disabled={busy} onClick={()=>void start()}>{busy?(zh?'正在提交对比…':'Submitting comparison…'):(zh?'重试未确认的提交':'Retry unconfirmed submissions')}</button>}
   {error&&<p role="alert">{error} {zh?'已接受的任务会保留；重试会沿用原请求，不会重复提交已确认的对比。':'Accepted work is retained. Retry reuses the original requests.'}</p>}
   {allComplete&&<div className="first-comparison-next"><h3>{zh?'对比结果出来了，接下来看看原因':'The comparison is ready. Explore what happened.'}</h3><p>{zh?'去竞技场查看这次对比的身体与脑活动回放，再选择更长时间、其他环境或其他对手。单个种子的结果还不足以说明普遍优势。':'Open Arena to inspect body and brain replays, then choose longer runs, other environments or opponents. One seed does not establish a general advantage.'}</p><button className="primary" onClick={()=>{const entry=attempt.entries[0];onArena(entry.id!,reports[entry.id!].matches.find(m=>m.status==='verified')?.id||'')}}>{zh?'去竞技场查看回放与继续探索':'Open Arena · replay and explore'}</button></div>}
   {allTerminal&&<button className="secondary" onClick={()=>{remember(null);setReports({});setError('')}}>{zh?'选择新的对照或时长':'Choose new references or duration'}</button>}
  </>}
 </section>
}

function ComparisonReport({entry,subject,onReport,onArena}:{entry:Entry;subject:Fly;onReport:(report:Series)=>void;onArena:Props['onArena']}){
 const {locale,t}=useI18n(),zh=locale==='zh-CN'
 const [report,setReport]=useState<Series|null>(null),[error,setError]=useState('')
 const callback=useRef(onReport);callback.current=onReport
 useEffect(()=>{
  if(!entry.id)return
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
  async function load(){
   try{
    const value=await api<Series>('/tournaments/'+entry.id,{signal:controller.signal})
    if(controller.signal.aborted)return
    if(value.id!==entry.id||value.spec.fly_ids.join(',')!==entry.request.fly_ids.join(',')||value.spec.duration_seconds!==entry.request.duration_seconds||value.spec.map_id!==entry.request.map_id||value.spec.mode!==entry.request.mode||value.spec.bridge_profile!==entry.request.bridge_profile||value.spec.sensory_profile!==entry.request.sensory_profile||value.spec.seeds.join(',')!==entry.request.seeds.join(',')||value.owner!==subject.owner||!Array.isArray(value.schedule))throw Error('series.invalidReport')
    setReport(value);setError('');callback.current(value)
    if(value.status==='running'||value.schedule.some(leg=>['queued','running'].includes(leg.status)))timer=setTimeout(load,2500)
   }catch(e){if(!controller.signal.aborted){setError(e instanceof Error?e.message:String(e));timer=setTimeout(load,5000)}}
  }
  void load();return()=>{controller.abort();clearTimeout(timer)}
 },[entry.id])
 const result=report?comparisonResult(report,subject.id):null
 return <article className="first-comparison-result"><h3>{subject.name} <span>vs</span> {entry.referenceName}</h3><p>{entry.kind==='wt'?(zh?'WT 基线对照':'WT reference'):(zh?'其他设计师对照':'Another designer’s reference')} · 2 × {entry.request.duration_seconds} {zh?'模拟秒':'simulated seconds'}</p>
  {error&&<p role="alert">{t(error)} · {zh?'正在重新读取记录，不会重新计算。':'Retrying the record, without starting new computation.'}</p>}
  {!entry.id?<p role="status">{zh?'等待提交确认':'Awaiting submission confirmation'}</p>:!report?<p role="status">{zh?'正在读取对比记录…':'Loading comparison record…'}</p>:<>
   <p role="status">{t('series.status.'+report.status)} · {report.verified_matches}/{report.expected_matches} {zh?'场已验证':'matches verified'}</p>
   {result?<><p className="comparison-verdict"><strong>{result.own===result.rival?(zh?'在这两场换位对比中，双方平均摄取量相同。':'Mean food intake is equal across these two swapped matches.'):result.own>result.rival?(zh?'在这两场换位对比中，你的平均摄取量更高。':'Your mean food intake is higher across these two swapped matches.'):(zh?'在这两场换位对比中，你的平均摄取量更低。':'Your mean food intake is lower across these two swapped matches.')}</strong></p><div className="first-comparison-scores"><div><span>{zh?'你的平均摄取量':'Your mean food intake'}</span><strong>{result.own.toFixed(4)}</strong></div><div><span>{zh?'对照平均摄取量':'Reference mean food intake'}</span><strong>{result.rival.toFixed(4)}</strong></div></div><p>{zh?`两场结果：${result.wins} 胜、${result.draws} 平、${2-result.wins-result.draws} 负。`:`Two matches: ${result.wins} wins, ${result.draws} draws, ${2-result.wins-result.draws} losses.`}</p><p>{result.own===0&&result.rival===0?(zh?'双方在这两场中均未记录到摄取；这不代表没有活动或没有能力。':'Neither fly recorded food intake in these matches; this does not mean no activity or ability.'):(zh?'这是交换位置后的两场平均值，不是学习程度或全局排名。':'These are averages across swapped positions, not a learning measure or global ranking.')}</p><button className="text-link" onClick={()=>onArena(report.id,report.matches.find(m=>m.status==='verified')?.id||'')}>{zh?'去竞技场检查这组回放':'Inspect this pair in Arena'}</button></>:<p>{zh?'等两场记录都完整后才汇总，单场、失败或缺失结果不会当作完整对比。':'A summary requires both complete records; one match, failed or missing results cannot establish the comparison.'}</p>}
   <details><summary>{zh?'查看每场进度与记录':'Inspect each match and record'}</summary>{report.schedule.map((leg,index)=><div key={index}><p>{zh?'场次':'Match'} {index+1} · {t('series.slots')}: {leg.fly_ids.map(id=>id===subject.id?subject.name:entry.referenceName).join(' → ')} · {t('series.status.'+leg.status)}</p>{leg.errors.map((message,i)=><p role="alert" key={i}>{message}</p>)}{leg.issues.map(issue=><p key={issue}>{t('series.issue.'+issue)}</p>)}</div>)}{report.issues.map(issue=><p key={issue}>{t('series.issue.'+issue)}</p>)}</details>
   {report.status==='incomplete'&&<button className="text-link" onClick={()=>onArena(report.id,'')}>{zh?'检查未完成的记录':'Inspect incomplete records'}</button>}
  </>}
 </article>
}
