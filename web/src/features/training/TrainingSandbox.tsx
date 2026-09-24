import {eligibleTrainingMaps,trainingEligibilityProblem} from './trainingEligibility'
import {lifeHash,continuationFocus} from '../life/navigation'
import {useEffect,useRef,useState} from 'react'
import {ArrowRight,Check,Dna,Download,GitBranch,Loader2,Pause,Play,Save,Square,TrendingUp} from 'lucide-react'
import {api,newRequestKey} from '../../api'
import type {ArenaMap,Fly,Identity,Match,Season,TrainingBridge} from '../../types'
import {useI18n} from '../../shared/i18n'
import {MapPreview} from '../arena/MapPreview'
import {AlgorithmPicker} from './AlgorithmPicker'
import {TrainingShowcase} from './TrainingShowcase'
import {algorithmName} from './algorithms'
import type {Strategy} from './algorithms'
import {TrainingComparison} from './TrainingComparison'
import {TrainingWorkload} from './TrainingWorkload'
import {ConditionResults} from './ConditionResults'
import type {ConditionResult} from './ConditionResults'
import {evaluationConditions,type ComparableRun} from './comparison'
import type {EvaluationCondition} from './comparison'
import {continuationPlan,type ContinuationRecord,evaluationCount,planProblem,memberRole,trainingFocus,trainingHash,competitionSetup} from './plan'

type Plan={evaluation_conditions?:EvaluationCondition[]|null;name:string;founder_id:string;opponent_id:string|null;strategy:Strategy;optimizer_name?:string;circuits:string[];mutation_strength:number;population:number;generations:number;max_evaluations:number;map_id:string;mode:'forage'|'contest';duration_seconds:number;seed:number;bridge_profile:string;sensory_profile?:string;fitness_objective?:string}
type Member={condition_results?:ConditionResult[];generation:number;slot:number;fly_id:string;saved:number;fitness:number|null;fly:Fly;matches:Match[]}
type Training={id:string;evaluation_context?:string;spec:Plan;status:string;control:string;error:string|null;members:Member[];evaluations_total:number;evaluations_started:number;evaluations_completed:number;progress:number;best_fly_id:string|null;baseline_fitness:number|null;proposal_generation:number|null;open_slots:number[]}
type CompetitionSetup={map_id:string;seed:number;duration_seconds:number;opponent_id?:string|null;bridge_profile:string;sensory_profile:string}
type Props={flies:Fly[];identity:Identity|null;selected:string;season:Season|null;maps:ArenaMap[];onLogin:()=>void;onSaved:(fly:Fly)=>Promise<void>;onCompete:(fly:Fly,setup?:CompetitionSetup,reference?:Fly)=>void;onReplay:(match:Match)=>void}
const terminal=(status:string)=>['complete','failed','stopped'].includes(status)
const statusKey:Record<string,string>={awaiting_candidates:'Waiting for your optimizer',queued:'Queued',running:'Training',paused:'Paused',pausing:'Pausing after evaluation',stopping:'Stopping after evaluation',stopped:'Stopped',complete:'Complete',failed:'Failed'}

export function TrainingSandbox({flies,identity,selected,season,maps,onLogin,onSaved,onCompete,onReplay}:Props){
  const {t,locale}=useI18n()
  const [continuationId,setContinuationId]=useState(()=>continuationFocus(location.hash))
  const [continuation,setContinuation]=useState<ReturnType<typeof continuationPlan>|null>(null)
  const [continuationFlies,setContinuationFlies]=useState<Fly[]>([])
  const [continuationLoaded,setContinuationLoaded]=useState(false)
  const [requiresCopy,setRequiresCopy]=useState(false)
  const preparedContinuation=useRef('')
  const [founder,setFounder]=useState(selected||flies[0]?.id||'')
  const [opponent,setOpponent]=useState(flies.find(f=>f.id!==founder)?.id||'')
  const [name,setName]=useState('Evolution 01')
  const [map,setMap]=useState('orchard')
  const [bridgeProfile,setBridgeProfile]=useState('legacy-v1')
  const bridgeOptions:TrainingBridge[]=season?.training_bridge_profiles??(season?.match_profiles||[]).filter(p=>p.id==='legacy-v1')
  const chosenBridge=bridgeOptions.find(p=>p.id===bridgeProfile)
  const bridgeLabel=(id:string)=>id==='legacy-v1'?(locale==='zh-CN'?'线性读出 + 滤波驱动':'Linear readout + filtered drive'):id==='sensorimotor-research-v2'?(locale==='zh-CN'?'核函数读出 + 运动变换':'Kernel readout + motor transfer'):id
  const [sensoryProfile,setSensoryProfile]=useState('odor-only-v1')
  const sensoryOptions=season?.training_sensory_profiles??[{id:'odor-only-v1',name:'Bilateral odor only',ready:true}]
  const sensoryCompatible=(id:string)=>!chosenBridge?.sensory_profiles||chosenBridge.sensory_profiles.includes(id)
  const sensoryReady=sensoryOptions.some(p=>p.id===sensoryProfile&&p.ready)&&sensoryCompatible(sensoryProfile)
  const sensoryLabel=(id:string)=>id==='engineered-kernel-contact-v1'?(locale==='zh-CN'?'实验：核函数方案的视觉、味觉与左右触觉':'Experimental kernel vision + taste + lateral touch'):t(sensoryOptions.find(p=>p.id===id)?.name||id)
  const [fitnessObjective,setFitnessObjective]=useState('food')
  const fitnessOptions=season?.training_fitness_objectives??[{id:'food',name:'Food collected',ready:true}]
  const fitnessReady=fitnessOptions.some(p=>p.id===fitnessObjective&&p.ready)
  const objectiveName=(id:string)=>t(id==='sustained-foraging-v1'?'Sustained foraging':'Food collected')
  const [mode,setMode]=useState<'forage'|'contest'>('forage')
  const [strategy,setStrategy]=useState<Strategy>('evolution')
  const [optimizerName,setOptimizerName]=useState('My custom optimizer')
  const [proposal,setProposal]=useState('')
  const [showcaseRevision,setShowcaseRevision]=useState(0)
  const [exampleFounder,setExampleFounder]=useState<Fly|null>(null)
  const availableFlies=[...flies,...continuationFlies,...(exampleFounder?[exampleFounder]:[])].filter((fly,index,all)=>all.findIndex(f=>f.id===fly.id)===index)
  const [circuits,setCircuits]=useState(['olfactory','projection','descending'])
  const [strength,setStrength]=useState(.08)
  const [population,setPopulation]=useState(2)
  const [generations,setGenerations]=useState(2)
  const [duration,setDuration]=useState(5)
  const [seed,setSeed]=useState(42)
  const [budget,setBudget]=useState(4)
  const [extraConditions,setExtraConditions]=useState<EvaluationCondition[]>([])
  const conditions=[{map_id:map,seed},...extraConditions]
  const [runs,setRuns]=useState<Training[]>([])
  const [focus,setFocusState]=useState(()=>trainingFocus(location.hash))
  const setup=useRef<HTMLElement>(null)
  function setFocus(value:string){history.pushState(null,'',trainingHash(value));setFocusState(value);setContinuationId('')}
  useEffect(()=>{const sync=()=>{setFocusState(trainingFocus(location.hash));setContinuationId(continuationFocus(location.hash))};window.addEventListener('hashchange',sync);window.addEventListener('popstate',sync);return()=>{window.removeEventListener('hashchange',sync);window.removeEventListener('popstate',sync)}},[])
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const [loadedOwner,setLoadedOwner]=useState<string|null>(null)
  const revision=useRef(0)
  const [generation,setGeneration]=useState<number|null>(null)
  const continuationPending=!!continuationId&&(!continuationLoaded||requiresCopy)
  const profile=chosenBridge?.ready
  const selectedFly=availableFlies.find(f=>f.id===founder)
  const bridgeModelCompatible=(p:TrainingBridge)=>!p.models||[selectedFly,...(mode==='contest'?[availableFlies.find(f=>f.id===opponent)]:[])].every(f=>!!f&&p.models!.includes(f.spec.model_profile))
  const modelReady=!!chosenBridge&&bridgeModelCompatible(chosenBridge)
  const needed=evaluationCount({population,generations,mode,conditions})
  const eligibleMaps=eligibleTrainingMaps(maps,bridgeProfile,mode)
  const previewProblem=trainingEligibilityProblem(map,bridgeProfile,mode,maps.find(m=>m.id===map)?.metadata)
  const metadataProblem=conditions.map(c=>trainingEligibilityProblem(c.map_id,bridgeProfile,mode,maps.find(m=>m.id===c.map_id)?.metadata)).find(Boolean)
  const problem=previewProblem||metadataProblem||planProblem({population,generations,budget,duration,seed,circuits,name,mode,founder,opponent,strategy,conditions,map_id:map,bridge_profile:bridgeProfile})
  const visibleRuns=loadedOwner===identity?.id?runs:[]
  const current=visibleRuns.find(r=>r.id===focus)
  const shownGeneration=generation??Math.max(0,...(current?.members.map(m=>m.generation)||[]))
  const members=current?.members.filter(m=>m.generation===shownGeneration)||[]
  useEffect(()=>{setContinuationFlies([]);setExampleFounder(null)},[identity?.id])
  useEffect(()=>{if(!continuationId&&!founder&&flies.length)setFounder(selected||flies[0].id)},[flies,selected,founder])
  useEffect(()=>{
    const key=JSON.stringify([continuationId,identity?.id,identity?.token])
    if(continuationId&&preparedContinuation.current===key)return
    preparedContinuation.current='';setContinuation(null);setContinuationLoaded(false);setRequiresCopy(false)
    if(!continuationId)return
    setContinuationFlies([])
    setFounder('');setFocusState('');setError('')
    if(!season||!maps.length)return
    const ctrl=new AbortController()
    async function prepare(){
      try{
        const record=await api<ContinuationRecord>('/lives/'+continuationId,{signal:ctrl.signal},identity)
        const opponentIds=[...new Set((record.continuation?.conditions??[]).flatMap(c=>c.opponent_id?[c.opponent_id]:[]))]
        const rivals=await Promise.all(opponentIds.map(async id=>{try{return (await api<ContinuationRecord>('/lives/'+id,{signal:ctrl.signal},identity)).fly}catch{return null}}))
        if(ctrl.signal.aborted)return
        const available=[record.fly,...rivals.filter((f):f is Fly=>!!f)]
        const plan=continuationPlan(record,season!,maps,available)
        setContinuationFlies(available);setFounder(record.fly.id);setContinuation(plan);setRequiresCopy(!!record.continuation?.requires_copy)
        setName((record.fly.name.slice(0,44)+' · '+t('New branch')).slice(0,64))
        const environment=plan.environment
        setBridgeProfile(environment?.bridge_profile||'');setSensoryProfile(environment?.sensory_profile||'');setFitnessObjective(environment?.fitness_objective||'')
        setMap(plan.conditions[0]?.map_id||'');setSeed(plan.conditions[0]?.seed??42);setExtraConditions(plan.conditions.slice(1))
        setDuration(environment?.duration_seconds??5);setMode(environment?.mode==='contest'?'contest':'forage');setOpponent(environment?.opponent_id||'')
        setPopulation(2);setGenerations(1);setBudget(Math.max(2,2*plan.conditions.length*(environment?.mode==='contest'?2:1)))
        preparedContinuation.current=key;setContinuationLoaded(true)
      }catch(e){if(!ctrl.signal.aborted)setError(String(e))}
    }
    void prepare();return()=>ctrl.abort()
  },[continuationId,identity?.id,identity?.token,season,maps])
  useEffect(()=>{
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
    async function poll(){
      if(!identity){setRuns([]);setLoadedOwner(null);return}
      try{
        const observedRevision=revision.current
        const next=await api<Training[]>('/training',{signal:controller.signal},identity)
        if(focus&&!next.some(run=>run.id===focus)){
          try{next.push(await api<Training>('/training/'+focus,{signal:controller.signal},identity))}
          catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:String(e))}
        }
        if(!controller.signal.aborted&&observedRevision===revision.current){setRuns(next);setLoadedOwner(identity.id)}
      }catch(e){if(!controller.signal.aborted)setError(String(e))}
      if(!controller.signal.aborted)timer=setTimeout(poll,3000)
    }
    void poll()
    return()=>{controller.abort();clearTimeout(timer)}
  },[identity?.id,identity?.token,focus])
  async function act(key:string,fn:()=>Promise<void>){setBusy(key);setError('');setMessage('');try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}}
  function accept(run:Training){revision.current++;setRuns(old=>[run,...old.filter(r=>r.id!==run.id)]);setLoadedOwner(identity?.id||null);if(focus!==run.id)setFocus(run.id)}
  async function start(){
    if(continuationPending)return
    if(problem){setError(t(problem));return}
    if(!profile||!modelReady){setError(locale==='zh-CN'?'请选择可运行且兼容大脑模型的感觉—运动方案。':'Choose an available sensorimotor setup compatible with the selected brains.');return}
    if(!fitnessReady){setError(t('Selected objective is unavailable on this server.'));return}
    if(!sensoryReady){setError(t('Selected sensory input is unavailable for training.'));return}
    if(!identity){onLogin();return}
    await act('create',async()=>{
      const run=await api<Training>('/training',{method:'POST',headers:{'Idempotency-Key':newRequestKey()},body:JSON.stringify({name,founder_id:founder,opponent_id:mode==='contest'?opponent:null,strategy,optimizer_name:strategy==='external'?optimizerName:'',circuits,mutation_strength:strength,population,generations,max_evaluations:budget,map_id:map,mode,duration_seconds:duration,seed,evaluation_conditions:extraConditions.length?conditions:null,bridge_profile:bridgeProfile,...(season?.training_fitness_objectives?{fitness_objective:fitnessObjective}:{}),...(season?.training_sensory_profiles?{sensory_profile:sensoryProfile}:{})})},identity)
      accept(run);setGeneration(null)
    })
  }
  async function control(action:string){if(current)await act(action,async()=>accept(await api<Training>(`/training/${current.id}/control`,{method:'POST',body:JSON.stringify({action})},identity)))}
  async function save(member:Member,next:'library'|'compete'|'parent'|'branch'='library'){if(current)await act(member.fly_id,async()=>{
    const fly=await api<Fly>(`/training/${current.id}/save`,{method:'POST',body:JSON.stringify({fly_id:member.fly_id})},identity)
    await onSaved(fly);accept(await api<Training>(`/training/${current.id}`,{},identity));setMessage(t('Individual saved to your library.'))
    if(next==='compete'||next==='parent')onCompete(fly,competitionSetup(current.spec),next==='parent'?current.members.find(parent=>parent.fly_id===member.fly.spec.parent_id)?.fly:undefined)
    if(next==='branch'){restoreEnvironment(current.spec);setFounder(fly.id);setName((fly.name.slice(0,44)+' · '+t('New branch')).slice(0,64));setFocus('');setGeneration(null);setMessage(t('Choose a strategy and budget for this descendant.'));requestAnimationFrame(()=>setup.current?.scrollIntoView({block:'start'}))}
  })}
  async function copyExample(sample:Fly,spec:ComparableRun['spec'],runId:string){
    if(!identity){onLogin();return}
    await act('copy:'+sample.id,async()=>{
      const fly=await api<Fly>(`/training-showcase/${runId}/flies/${sample.id}/copy`,{method:'POST'},identity)
      await onSaved(fly);restoreEnvironment(spec);setExampleFounder(fly);setFounder(fly.id)
      setName((fly.name.slice(0,44)+' · '+t('New branch')).slice(0,64));setFocus('');setGeneration(null)
      setMessage(t('Copy saved with its public parent. Choose a strategy and budget, then start training.'))
      requestAnimationFrame(()=>setup.current?.scrollIntoView({block:'start'}))
    })
  }
  async function copyContinuation(){
    if(!identity){onLogin();return}
    const sample=availableFlies.find(f=>f.id===continuationId)
    if(!sample?.source)return
    await act('copy:'+sample.id,async()=>{
      const fly=await api<Fly>(`/training-showcase/${sample.source!.run_id}/flies/${sample.id}/copy`,{method:'POST'},identity)
      await onSaved(fly);setExampleFounder(fly);setFounder(fly.id);setRequiresCopy(false)
    })
  }
  function restoreEnvironment(spec:{bridge_profile?:string;map_id:string;seed:number;duration_seconds:number;sensory_profile?:string;fitness_objective?:string;evaluation_conditions?:EvaluationCondition[]|null}){const conditions=evaluationConditions(spec);setBridgeProfile(spec.bridge_profile||'legacy-v1');setMap(conditions[0].map_id);setSeed(conditions[0].seed);setDuration(spec.duration_seconds);setSensoryProfile(spec.sensory_profile||'odor-only-v1');setFitnessObjective(spec.fitness_objective||'food');setExtraConditions(conditions.slice(1))}
  function exportRun(){if(!current)return;const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='training-'+current.id+'.json';link.click();URL.revokeObjectURL(url)}
  const generationsHistory=current?Array.from({length:current.spec.generations},(_,i)=>{
    const group=current.members.filter(m=>m.generation===i),scored=group.filter(m=>m.fitness!==null)
    return {generation:i,complete:scored.length===current.spec.population,best:scored.length?Math.max(...scored.map(m=>m.fitness!)):null,count:scored.length}
  }):[]
  const best=current?.members.find(m=>m.fly_id===current.best_fly_id)?.fitness
  return <div className={"training-layout "+(current?"has-session":"new-session")}>
    <aside ref={setup} className="panel training-setup">
      <div className="panel-heading"><span><Dna size={17}/>{t('Start a training session')}</span><span className="tiny-label">SANDBOX</span></div>
      {continuationId&&<section aria-label={t('Review lineage continuation')}><h3>{t('Review lineage continuation')}</h3><a href={lifeHash(continuationId)}>{continuationId}</a><p>{t('Only accessible recorded evaluations are reused. Missing fields need a new choice; editable budget and search settings are new, not inherited. No computation starts until Start training.')}</p>{!continuationLoaded&&!error&&<p role="status">{t('Loading recorded conditions…')}</p>}{continuation&&<><p>{t('Retained conditions')} · {continuation.conditions.length} / {continuation.reviews.length}</p>{!continuation.conditions.length&&<p>{t('No eligible recorded conditions. Choose a new setup before starting.')}</p>}{continuation.environment&&!continuation.environment.fitness_objective&&<p>{t('Selection objective was not recorded; choose a new objective.')}</p>}{continuation.environment&&!continuation.environment.sensory_profile&&<p>{t('Sensory input was not recorded; choose a new input.')}</p>}<details><summary>{t('Retained and dropped conditions')}</summary>{continuation.reviews.map((review,index)=><div key={index}><strong>{t(review.retained?'Retained':'Dropped')}</strong><p>{t(review.reason)}</p><code>{JSON.stringify(review.record)}</code></div>)}</details></>}{requiresCopy&&<><p>{t('This published snapshot needs a local copy linked to the recorded individual before training.')}</p><button className="secondary" disabled={!!busy||!season?.gallery_copy_available} onClick={copyContinuation}>{t('Save a copy and prepare training')}</button></>}</section>}
      <label>{t('Session name')}<input value={name} maxLength={64} onChange={e=>setName(e.target.value)}/></label>
      <label>{t('Starting fly')}<select value={founder} disabled={!!continuationId} onChange={e=>setFounder(e.target.value)}><option value="">{t('Choose a fly')}</option>{availableFlies.map(f=><option key={f.id} value={f.id}>{f.name} · {f.id.slice(0,8)}</option>)}</select></label>
      <label htmlFor="training-fitness-objective">{t('Selection objective')}<select id="training-fitness-objective" value={fitnessObjective} onChange={e=>setFitnessObjective(e.target.value)}>{!fitnessObjective&&<option value="" disabled>{t('Choose a selection objective')}</option>}{fitnessOptions.map(p=><option key={p.id} value={p.id} disabled={!p.ready}>{t(p.name)}</option>)}</select></label>
      <p className="training-hint">{t(fitnessObjective==='sustained-foraging-v1'?'Fitness = (total food + food in the second half) × fraction of time not inverted. This rewards later feeding and posture; it does not guarantee learned behavior.':'Select candidates by food collected; competitions use the margin over the opponent.')}</p>
      {!fitnessReady&&<p className="training-hint" role="status">{t('Selected objective is unavailable on this server.')}</p>}
      <AlgorithmPicker value={strategy} onChange={setStrategy} name={optimizerName} onName={setOptimizerName}/>
      <div className="training-pair"><label>{t('Environment')}<select value={map} onChange={e=>setMap(e.target.value)}>{!eligibleMaps.some(m=>m.id===map)&&<option value={map} disabled>{map} · {t('Selected map is not eligible')}</option>}{eligibleMaps.map(m=><option key={m.id} value={m.id}>{locale==='en'?m.english:m.name}</option>)}</select></label><label>{t('Objective')}<select value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="forage">{t('Collect food')}</option><option value="contest">{t('Compete for food')}</option></select></label></div>
      <p className="training-hint">{t(maps.find(m=>m.id===map)?.description||'')}</p>
      <label htmlFor="training-bridge-profile">{locale==='zh-CN'?'感觉—运动方案':'Sensorimotor setup'}<select id="training-bridge-profile" value={bridgeProfile} onChange={e=>{const id=e.target.value;setBridgeProfile(id);const option=bridgeOptions.find(p=>p.id===id);if(option?.sensory_profiles&&!option.sensory_profiles.includes(sensoryProfile))setSensoryProfile('odor-only-v1')}}>{!chosenBridge&&<option value={bridgeProfile} disabled>{bridgeLabel(bridgeProfile)} · {locale==='zh-CN'?'不可用':'Unavailable'}</option>}{bridgeOptions.map(p=><option key={p.id} value={p.id} disabled={!p.ready||!bridgeModelCompatible(p)}>{bridgeLabel(p.id)}{!p.ready?' · '+(locale==='zh-CN'?'不可用':'Unavailable'):!bridgeModelCompatible(p)?' · '+(locale==='zh-CN'?'大脑模型不兼容':'Incompatible brain model'):''}</option>)}</select></label>
      <p className="training-hint">{bridgeProfile==='sensorimotor-research-v2'?(locale==='zh-CN'?'实验方案：LIF 下行神经活动经过核函数解码和运动变换。嗅觉模式只将嗅觉送入大脑；可另选实验性的视觉、味觉与左右触觉输入。训练可运行不代表行为有效或已具备赛事资格。':'Experimental setup: LIF descending activity feeds a kernel decoder and motor transfer. Odor-only mode leaves vision and touch as observations; an experimental visual, taste and lateral touch profile can be selected when available. Availability does not establish effective behavior or competition qualification.'):(locale==='zh-CN'?'下行神经活动经过线性读出和滤波后驱动身体。可搭配嗅觉输入或实验性视觉、味觉与触觉输入。':'Descending activity drives the body through a linear readout and filter. Supports odor input and experimental visual, taste and touch inputs.')}</p>
      {!modelReady&&<p className="training-hint" role="status">{locale==='zh-CN'?'此方案与所选大脑模型不兼容；请选择兼容方案。':'This setup is incompatible with the selected brain models; choose a compatible setup.'}</p>}
      {chosenBridge?.reason&&<p className="training-hint" role="status">{chosenBridge.reason}</p>}
      <label htmlFor="training-sensory-profile">{t('Sensory input profile')}<select id="training-sensory-profile" value={sensoryProfile} onChange={e=>setSensoryProfile(e.target.value)}>{!sensoryProfile&&<option value="" disabled>{t('Choose sensory input')}</option>}{sensoryOptions.map(p=><option key={p.id} value={p.id} disabled={!p.ready||!sensoryCompatible(p.id)}>{sensoryLabel(p.id)}</option>)}</select></label>
      <p className="training-hint">{t('Every candidate uses these senses in evaluation and subsequent competition.')}</p>
      {!season?.training_sensory_profiles&&<p className="training-hint">{t('This server currently offers odor-only training.')}</p>}
      {mode==='contest'&&<label>{t('Fixed opponent')}<select value={opponent} onChange={e=>setOpponent(e.target.value)}><option value="">{t('Choose a fly')}</option>{availableFlies.map(f=><option key={f.id} value={f.id}>{f.name} · {f.id.slice(0,8)}</option>)}</select></label>}
      {strategy!=='external'&&<><fieldset className="training-circuits"><legend>{t('Allow mutations in')}</legend>{season?.connectome.circuits.map(c=><label key={c.id}><input type="checkbox" checked={circuits.includes(c.id)} onChange={e=>setCircuits(old=>e.target.checked?[...old,c.id]:old.filter(id=>id!==c.id))}/><span style={{color:c.color}}/> {t(c.label)}</label>)}</fieldset>
      <label>{t('Mutation strength')} <b>{(strength*100).toFixed(0)}%</b><input type="range" min=".01" max=".3" step=".01" value={strength} onChange={e=>setStrength(+e.target.value)}/></label></>}
      <p className="training-hint">{locale==='en'?'Brain model':'大脑模型'} · {selectedFly?.spec.model_profile||'—'}</p>
      {strategy==='external'&&selectedFly?.spec.model_profile==='malecns-rate-cpu-v1'&&<p className="training-hint">{locale==='en'?'Train neural responses with Adam on your device, then evaluate proposals here.':'可在自己的设备上用 Adam 训练神经响应，再把候选提交到这里评测。'} <a href="https://github.com/the-omega-institute/fly-arena/blob/main/docs/RATE_MODEL.md" target="_blank" rel="noreferrer">{locale==='en'?'Adam trainer setup':'Adam 训练器配置'}</a></p>}
      <div className="training-pair"><label>{t('Population')}<input type="number" min="2" max="6" value={population} onChange={e=>setPopulation(+e.target.value)}/></label><label>{t(strategy==='random_search'?'Search rounds':'Generations')}<input type="number" min="1" max="8" value={generations} onChange={e=>setGenerations(+e.target.value)}/></label></div>
      <div className="training-pair"><label>{t('Seconds per evaluation')}<select value={duration} onChange={e=>setDuration(+e.target.value)}>{Array.from({length:30},(_,i)=>i+1).map(n=><option key={n} value={n}>{n} s{n<=2?(locale==='zh-CN'?' · 流程试跑':' · Workflow trial'):n>=5?(locale==='zh-CN'?' · 行为观察':' · Behavior observation'):''}</option>)}</select></label><label>{t('Seed')}<input type="number" min="0" max="2147483647" value={seed} onChange={e=>setSeed(+e.target.value)}/></label></div>
      <fieldset className="training-environments"><legend>{t('Evaluation conditions')} · {conditions.length}/4</legend>
        <p className="training-hint">{t('The environment and seed above are condition 1. Add maps or seeds for the same candidate.')}</p>
        {extraConditions.map((condition,index)=><div key={index} className="extra-condition"><strong>{t('Condition')} {index+2}</strong><div className="training-pair">
          <label>{t('Environment')}<select value={condition.map_id} onChange={e=>setExtraConditions(old=>old.map((c,i)=>i===index?{...c,map_id:e.target.value}:c))}>{!eligibleMaps.some(m=>m.id===condition.map_id)&&<option value={condition.map_id} disabled>{condition.map_id} · {t('Selected map is not eligible')}</option>}{eligibleMaps.map(m=><option key={m.id} value={m.id}>{locale==='en'?m.english:m.name}</option>)}</select></label>
          <label>{t('Seed')}<input type="number" min="0" max="2147483647" value={condition.seed} onChange={e=>setExtraConditions(old=>old.map((c,i)=>i===index?{...c,seed:+e.target.value}:c))}/></label>
        </div><button className="text-link" onClick={()=>setExtraConditions(old=>old.filter((_,i)=>i!==index))}>{t('Remove condition')} {index+2}</button></div>)}
        <button className="secondary wide" disabled={conditions.length>=4} onClick={()=>setExtraConditions(old=>[...old,{map_id:map,seed:(seed+old.length+1)%2147483648}])}>{t('Add evaluation condition')}</button>
        <p className="training-hint">{t('All conditions count toward the budget. Fitness is their complete mean; these are training environments, not held-out tests.')}</p>
      </fieldset>
      <label>{t('Evaluation budget')}<input type="number" min="2" max="96" value={budget} onChange={e=>setBudget(+e.target.value)}/></label>
      <div className={'training-budget '+(needed>budget?'over':'')}><strong>{needed} / {budget}</strong><span>{t('evaluations planned / limit')}</span><small>{population} × {generations} × {conditions.length}{mode==='contest'?' × 2':''} · {t(mode==='contest'?'Both spawn positions in every condition.':'One solo evaluation per condition and individual.')}</small></div>
      <TrainingWorkload population={population} generations={generations} mode={mode} conditions={conditions} duration={duration}/>
      <p className="training-hint">{t('Simulations run in a queue and may take minutes. Closing this page does not stop training.')}</p>
      <button className="primary wide" disabled={continuationPending||!!busy||!profile||!modelReady||!sensoryReady||!fitnessReady||!!problem} onClick={start}>{busy==='create'?<Loader2 size={16} className="spin"/>:<Play size={16}/>} {t('Start training')}<ArrowRight size={16}/></button>
      {problem&&<p className="training-hint" role="status">{t(problem)}</p>}
      {!profile&&<p className="training-hint">{t('Training simulation is unavailable on this server.')}</p>}
    </aside>
    <div className="training-main">
      {error&&<p className="training-error" role="alert">{error}</p>}{message&&<p className="training-message" role="status"><Check size={16}/>{message}</p>}
      <TrainingShowcase maps={maps} onReplay={onReplay} revision={showcaseRevision} copyAvailable={!!season?.gallery_copy_available} busy={!!busy} onBranch={copyExample}/>
      <TrainingComparison key={identity?.id||'guest'} runs={visibleRuns} maps={maps} flies={flies} onOpen={id=>{setFocus(id);setGeneration(null)}}/>
      <div className="training-tabs"><button className={!current?'active':''} onClick={()=>setFocus('')}>{t('New session')}</button>{visibleRuns.map(r=><button key={r.id} className={current?.id===r.id?'active':''} onClick={()=>{setFocus(r.id);setGeneration(null)}}>{r.spec.name}<small>{t(statusKey[r.status]||r.status)}</small></button>)}</div>
      {!current?<><div className="arena-stage training-map"><div className="stage-heading"><span>{t('YOUR TRAINING GROUND')}</span><span>{t('Seed')} {seed}</span></div><div className="arena-canvas">{previewProblem?<p className="training-hint" role="status">{t(previewProblem)}</p>:<MapPreview mapId={map} seed={seed} bridgeProfile={bridgeProfile} participants={mode==='forage'?[selectedFly]:[selectedFly,availableFlies.find(f=>f.id===opponent)]}/>}</div></div><div className="panel training-welcome"><GitBranch size={28}/><h2>{t('Give your fly a few generations.')}</h2><p>{t('Choose a strategy and a small budget. Compare descendants through actual matches, inspect their behavior, and keep the ones you want to compete with.')}</p><div><span>01 · {t('Design')}</span><ArrowRight size={16}/><span>02 · {t('Train')}</span><ArrowRight size={16}/><span>03 · {t('Compete')}</span></div></div></>:<>
        <section className="panel training-overview"><div className="panel-heading"><span><GitBranch size={17}/>{current.spec.name}</span><span className="training-status">{t(statusKey[current.status]||current.status)}</span></div><div className="training-context"><span>{t(algorithmName(current.spec.strategy))}</span><span>{t('Selection objective')} · {objectiveName(current.spec.fitness_objective||'food')}</span><span>{locale==='zh-CN'?'感觉—运动方案':'Sensorimotor setup'} · {bridgeLabel(current.spec.bridge_profile)}</span><span>{t('Sensory profile')} · {sensoryLabel(current.spec.sensory_profile||'odor-only-v1')}</span><span>{(locale==='en'?maps.find(map=>map.id===current.spec.map_id)?.english:maps.find(map=>map.id===current.spec.map_id)?.name)||current.spec.map_id}</span><span>{t(current.spec.mode==='forage'?'Collect food':'Compete for food')}</span><span>{t('Seed')} {current.spec.seed} · {current.spec.duration_seconds} {t('s')}</span></div><div className="training-summary"><div><span>{t('Evaluations completed')}</span><strong>{current.evaluations_completed}<small> / {current.evaluations_total}</small></strong></div><div><span>{t('Best fitness')}</span><strong>{best==null?'—':best.toFixed(2)}</strong></div><div><span>{t('Starting fitness')}</span><strong>{current.baseline_fitness===null?'—':current.baseline_fitness.toFixed(2)}</strong></div></div><div className="training-progress"><span style={{width:current.progress*100+'%'}}/></div><div className="training-controls"><small>{t(current.spec.fitness_objective==='sustained-foraging-v1'?'Fitness = (total food + food in the second half) × fraction of time not inverted. Contest fitness is the difference from the opponent, averaged across swapped positions and conditions.':current.spec.mode==='contest'?'Fitness is the mean of complete condition margins, each averaged across both positions.':'Fitness is the mean food consumed across all complete conditions.')} {t('Training results do not affect the public leaderboard.')}</small>{!terminal(current.status)&&<>{current.control==='pause'?<button className="secondary" disabled={!!busy} onClick={()=>control('resume')}><Play size={14}/>{t('Resume')}</button>:<button className="secondary" disabled={!!busy||current.control==='stop'} onClick={()=>control('pause')}><Pause size={14}/>{t('Pause')}</button>}<button className="secondary" disabled={!!busy||current.control==='stop'} onClick={()=>control('stop')}><Square size={13}/>{t('Stop')}</button></>}</div>{current.error&&<p className="training-error">{current.error}</p>}</section>
        {current.status==='complete'&&<div className="training-publish"><button className="secondary" disabled={!!busy} onClick={()=>act('publish',async()=>{await api(`/training/${current.id}/publish`,{method:'POST'},identity);setShowcaseRevision(v=>v+1);setMessage(t('Trajectory published in the gallery.'))})}>{t('Publish trajectory')}</button><p>{t('Shares this completed session, every candidate design, score and replay with all visitors.')}</p></div>}
        <div className="training-context">{evaluationConditions(current.spec).map((condition,i)=><span key={i}>{t('Condition')} {i+1} · {maps.find(m=>m.id===condition.map_id)?.[locale==='en'?'english':'name']||condition.map_id} · {t('Seed')} {condition.seed}</span>)}</div>
        <div className="training-tools"><code>{current.id}</code><button className="secondary" onClick={exportRun}><Download size={14}/>{t('Export results and lineage')}</button></div>
        {current.spec.strategy==='external'&&<section className="panel training-program"><div className="panel-heading"><span>{t('Your optimizer, this arena')}</span><a href="#tab=code" className="text-link">AI / API <ArrowRight size={13}/></a></div><p>{t('Run this command with your Arena URL and API token set. Edit propose() to use your own strategy.')}</p><p>{current.spec.optimizer_name}</p><pre>{`python scripts/custom_strategy.py --run ${current.id}\n# With your own Python / PyTorch optimizer:\npython scripts/custom_strategy.py --run ${current.id} --plugin my_optimizer.py --config config.json`}</pre><p>{t('Plugin contract: propose(founder, history, generation, slot, config) returns a FlySpec. Model files and configuration stay on your device.')}</p><a className="text-link" href="https://github.com/the-omega-institute/fly-arena/blob/main/docs/TRAINING.md" target="_blank" rel="noreferrer">{t('Plugin examples and setup')} ↗</a><details><summary>{t('Submit candidate JSON')}</summary><p>{t('Paste a proposal with generation, slot and spec. The API validates its weights and evaluation budget.')}</p><textarea aria-label={t('Candidate JSON')} value={proposal} onChange={e=>setProposal(e.target.value)} placeholder='{"generation":0,"slot":1,"spec":{...}}'/><button className="secondary" disabled={!!busy||!proposal.trim()||!current.open_slots.length} onClick={()=>act('propose',async()=>{await api(`/training/${current.id}/candidates`,{method:'POST',body:JSON.stringify(JSON.parse(proposal))},identity);accept(await api(`/training/${current.id}`,{},identity));setProposal('');setMessage(t('Candidate submitted.'))})}>{t('Submit candidate')}</button></details>{current.open_slots.length>0&&<p>{t('Open proposal slots')} · G{current.proposal_generation!+1} · {current.open_slots.map(slot=>slot+1).join(', ')}</p>}</section>}
        <section className="panel training-history"><div className="panel-heading"><span><TrendingUp size={16}/>{t(current.spec.strategy==='random_search'?'Search rounds':'Generations')}</span><small>{t('Select a generation to inspect its individuals.')}</small></div><div className="generation-list">{generationsHistory.map(h=><button key={h.generation} className={shownGeneration===h.generation?'active':''} onClick={()=>setGeneration(h.generation)}><span>{current.spec.strategy==='random_search'?'R':'G'}{h.generation+1}</span><strong>{h.best===null?'—':h.best.toFixed(2)}</strong><small>{h.count}/{current.spec.population} {t('evaluated')}{!h.complete&&h.count>0?' · '+t('Partial'):''}</small></button>)}</div></section>
        <div className="training-individuals">{members.map(m=>{const parent=current.members.find(candidate=>candidate.fly_id===m.fly.spec.parent_id)?.fly||flies.find(candidate=>candidate.id===m.fly.spec.parent_id);return <article className="panel training-individual" key={m.fly_id}><div className="individual-title"><span className="tiny-label">{current.spec.strategy==='random_search'?'R':'G'}{m.generation+1} · {t(memberRole(current.spec.strategy,m.generation,m.slot))}</span>{m.fly_id===current.best_fly_id&&<span className="best-label">{t('Best so far')}</span>}</div><h3>{m.fly.name}</h3><a className="text-link" href={lifeHash(m.fly_id)}>{t('Open life record')}</a><code>{m.fly_id.slice(0,8)}</code><div className="individual-score"><span>{t('Candidate fitness')}</span><strong>{m.fitness===null?'—':m.fitness.toFixed(2)}</strong></div><p><GitBranch size={13}/>{t('Parent')} · {parent?<button className="text-link" onClick={()=>setGeneration(current.members.find(candidate=>candidate.fly_id===m.fly.spec.parent_id)?.generation??0)}>{parent.name}</button>:m.fly.spec.parent_id?.slice(0,8)||'—'}</p><p>{t('Mutation budget')} · {m.fly.report.budget_used.toFixed(2)} / {m.fly.report.budget_limit}</p><div className="individual-genes">{m.fly.spec.weight_mutations.map(g=><span key={g.selector}>{t(season?.connectome.circuits.find(c=>c.id===g.selector)?.label||g.selector)} ×{g.scale.toFixed(3)}</span>)}</div><ConditionResults results={m.condition_results||[{condition:evaluationConditions(current.spec)[0],fitness:m.fitness,evaluations_completed:m.matches.filter(match=>match.status==='verified').length,evaluations_total:current.spec.mode==='contest'?2:1,matches:m.matches}]} maps={maps} onReplay={onReplay}/><div className="individual-actions"><button className="secondary" disabled={!!busy||m.fitness===null||!!m.saved} onClick={()=>save(m)}>{m.saved?<Check size={14}/>:<Save size={14}/>} {t(m.saved?'Saved':'Save')}</button><button className="primary" disabled={!!busy||m.fitness===null} onClick={()=>save(m,'compete')}>{t('Compete')}<ArrowRight size={14}/></button></div><button className="text-link training-parent-compare" disabled={!!busy||m.fitness===null} onClick={()=>save(m,parent?'parent':'compete')}>{parent?t('Compare with parent'):t('Compare with WT')}<ArrowRight size={14}/></button><button className="text-link training-branch" disabled={!!busy||m.fitness===null} onClick={()=>save(m,'branch')}><GitBranch size={13}/>{t('Branch training from this fly')}</button></article>})}</div>
        {!members.length&&<div className="panel training-welcome"><Loader2 className="spin"/><p>{t('Preparing the first generation. Actual evaluations will appear here.')}</p></div>}
      </>}
    </div>
  </div>
}
