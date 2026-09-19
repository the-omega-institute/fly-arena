import {BrainModelPicker} from './features/design/BrainModelPicker'
import {LifeLedger} from './features/life/LifeLedger'
import {PlaygroundGuide} from './features/guide/PlaygroundGuide'
import {matchingWildType} from './features/arena/wildtype'
import {TrainingSandbox} from './features/training/TrainingSandbox'
import {SavedFlyCard} from './features/design/SavedFlyCard'
import {AuthDialogs} from './features/auth/AuthDialogs'
import {DevelopersFeature} from './features/developers/DevelopersFeature'
import {ArenaFeature} from './features/arena/ArenaFeature'
import {useReplay} from './features/arena/useReplay'
import {selectReplayFrames} from './features/arena/replayFrames'
import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import {ArrowDownToLine,ArrowRight,ArrowUpRight,AudioLines,Beaker,Bug,Check,ChevronDown,Code2,Copy,Dna,ExternalLink,FlaskConical,GitBranch,Leaf,Loader2,Pause,Play,Plus,RotateCcw,Settings2,ShieldCheck,Sparkles,Swords,Terminal,Trophy,UserRound,X} from 'lucide-react'
import {api,setCsrfToken} from './api'
import {PhenotypeLab} from './features/phenotype/PhenotypeLab'
import {AdvancedInterventions} from './features/design/AdvancedInterventions'
import {assertSpec,composeSpec} from './features/design/spec'
import {Preferences,useI18n} from './shared/i18n'
import type {InterventionSpec} from './shared/research'
import {ArenaCanvas} from './ArenaCanvas'
import type {ArenaMap,AuthSettings,Fly,Frame,Identity,Match,Preview,Report,Scene,Season,Spec} from './types'
import {defaultMatchProfile,colors,modes,num,preferredReplay} from './types'

import {readRoute,routeHash,type Tab} from './shared/navigation'
type Ranking={fly:Fly;wins:number;draws:number;losses:number;matches:number;food:number;points:number}
type NeuralPreview={schema:string;artifact_id:string;model_profile:string;connectome_sha256:string;steps:number;stimuli:{stimulus:{left:number;right:number};circuits:Record<string,number>;total_spikes:number|null}[];scope:string}
const defaultScales=()=>({olfactory:1,projection:1,local:1,memory:1,readout:1,descending:1,visual:1,motor:1})

function MapDrawing({map}:{map:ArenaMap}){
  return <svg viewBox="0 0 220 105" className={'map-drawing '+map.id} aria-hidden="true">
    <defs><pattern id={'grid-'+map.id} width="14" height="14" patternUnits="userSpaceOnUse"><path d="M14 0H0V14" fill="none" stroke="currentColor" strokeWidth=".45" opacity=".18"/></pattern></defs>
    <rect x="8" y="3" width="204" height="98" rx="9" fill={'url(#grid-'+map.id+')'}/>
    {map.id==='terrarium'?<><path d="M43 63L91 42h38l48 21-48 9H91Z" fill="currentColor" opacity=".28"/><path d="M43 63L91 42h38l48 21M91 42v30m38-30v30" fill="none" stroke="currentColor" strokeWidth="2"/>{[[62,25],[158,83],[153,27],[68,84]].map(([x,y],i)=><ellipse key={i} cx={x} cy={y} rx={i<2?15:10} ry="8" fill="currentColor" opacity=".35"/>)}<path d="M27 55Q64 2 110 19T193 53M27 65Q66 101 111 88T193 64" fill="none" stroke="currentColor" strokeDasharray="3 4"/></>:map.id==='scarcity'?<><circle cx="110" cy="54" r="26" fill="currentColor" opacity=".06"/><circle cx="110" cy="54" r="5" fill="currentColor"/><path d="M64 54h32m28 0h32" stroke="currentColor" strokeDasharray="3 4" opacity=".5"/></>:map.id==='ring'?<><ellipse cx="110" cy="54" rx="57" ry="38" fill="none" stroke="currentColor" strokeWidth="1.5"/><ellipse cx="110" cy="54" rx="46" ry="30" fill="none" stroke="currentColor" opacity=".15"/><path d="M62 68L145 28M78 80L158 40" stroke="currentColor" opacity=".09"/></>:map.id==='maze'?<><path d="M83 19v49h-23M137 88V39h24" fill="none" stroke="currentColor" strokeWidth="7"/><path d="M40 50h25q10 0 10 14v9q0 8 20 8h24" fill="none" stroke="currentColor" strokeDasharray="3 4" opacity=".45"/></>:<><path d="M39 62Q70 16 109 53T175 44" fill="none" stroke="currentColor" strokeDasharray="3 4" opacity=".4"/>{[[75,27],[112,61],[163,34],[57,80],[168,79]].map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r="10" fill="currentColor" opacity=".07"/><circle cx={x} cy={y} r="3" fill="currentColor" opacity=".7"/></g>)}</>}
    <g transform="translate(54,55) rotate(-25)"><ellipse rx="4" ry="2.5" fill="currentColor"/><path d="M-1 -2l-4 -4m4 8l-4 4M1 -2l2 -4m-2 8l2 4" stroke="currentColor" strokeWidth=".8"/></g>
    <g transform="translate(166,53) rotate(150)"><ellipse rx="4" ry="2.5" fill="currentColor"/><path d="M-1 -2l-4 -4m4 8l-4 4M1 -2l2 -4m-2 8l2 4" stroke="currentColor" strokeWidth=".8"/></g>
  </svg>
}

function download(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}

export default function App(){
  const {t,locale}=useI18n()
  const [experimentId,setExperimentId]=useState(()=>new URLSearchParams(location.hash.slice(1)).get('experiment')||'')
  const [parentId,setParentId]=useState<string|null>(null)
  const [baseSpec,setBaseSpec]=useState<Partial<Spec>>({})
  const [interventions,setInterventions]=useState<InterventionSpec[]>([])
  const [tab,setTabState]=useState<Tab>(readRoute(location.hash).tab)
  const [bridgeProfile,setBridgeProfile]=useState('')
  const [sensoryProfile,setSensoryProfile]=useState('odor-only-v1')
  const selectedSensoryProfile=bridgeProfile==='legacy-v1'?sensoryProfile:'odor-only-v1'
  const [season,setSeason]=useState<Season|null>(null)
  const [branchFly,setBranchFly]=useState<Fly|null>(null)
  const [flies,setFlies]=useState<Fly[]>([])
  const [maps,setMaps]=useState<ArenaMap[]>([])
  const [matches,setMatches]=useState<Match[]>([])
  const [rankings,setRankings]=useState<Ranking[]>([])
  const [preview,setPreview]=useState<Preview|null>(null)
  const [selected,setSelected]=useState<string>('')
  const [scales,setScales]=useState<Record<string,number>>(defaultScales)
  const [tau,setTau]=useState(1)
  const [threshold,setThreshold]=useState(0)
  const [name,setName]=useState('Nectar 01')
  const [color,setColor]=useState('mint')
  const [edgeDeltas,setEdgeDeltas]=useState<{edge:number;log_delta:number}[]>([])
  const [report,setReport]=useState<Report|null>(null)
  const [neuralPreview,setNeuralPreview]=useState<NeuralPreview|null>(null)
  const [identity,setIdentity]=useState<Identity|null>(null)
  const [authSettings,setAuthSettings]=useState<AuthSettings|null>(null)
  const [freshToken,setFreshToken]=useState('')
  const [agentTokens,setAgentTokens]=useState<{id:string;expires:number}[]>([])
  const [login,setLogin]=useState(false)
  const [identityName,setIdentityName]=useState('')
  const [invite,setInvite]=useState('')
  const [showToken,setShowToken]=useState(false)
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const [toast,setToast]=useState('')
  const [mapId,setMapId]=useState('orchard')
  const [mode,setMode]=useState('contest')
  const [opponent,setOpponent]=useState('')
  const [duration,setDuration]=useState(5)
  const [seed,setSeed]=useState(42)
  const [focused,setFocusedState]=useState<string>(readRoute(location.hash).match)
  const [play,setPlay]=useState(false)
  const [playtime,setPlaytime]=useState(0)
  const [playbackSpeed,setPlaybackSpeed]=useState(1)
  const [jsonEditor,setJsonEditor]=useState('')
  const [inspect,setInspect]=useState<{neurons:{id:string;type:string;nt:string}[];edges:{pre:string;post:string;count:number}[]}|null>(null)
  const [inspectOpen,setInspectOpen]=useState(false)
  const [inspectCircuit,setInspectCircuit]=useState('descending')
  const fileInput=useRef<HTMLInputElement>(null)
  const availableFlies=branchFly&&!flies.some(f=>f.id===branchFly.id)?[branchFly,...flies]:flies
  const selectedFly=availableFlies.find(f=>f.id===selected)
  const [archivedMatch,setArchivedMatch]=useState<Match|null>(null)
  const [archiveError,setArchiveError]=useState<{id:string;message:string}|null>(null)
  const listedMatch=matches.find(m=>m.id===focused)
  const current=listedMatch||(archivedMatch?.id===focused?archivedMatch:undefined)
  const matchError=!current&&archiveError?.id===focused?archiveError.message:''
  useEffect(()=>{
    if(!focused||listedMatch)return
    setArchiveError(null)
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
    async function load(){
      try{
        const match=await api<Match>('/matches/'+encodeURIComponent(focused),{signal:controller.signal})
        if(controller.signal.aborted)return
        setArchivedMatch(match);setArchiveError(null)
        if(match.status==='queued'||match.status==='running')timer=setTimeout(load,2500)
      }catch(e){if(!controller.signal.aborted)setArchiveError({id:focused,message:e instanceof Error?e.message:String(e)})}
    }
    void load()
    return()=>{controller.abort();clearTimeout(timer)}
  },[focused,listedMatch?.id])
  const replay=useReplay(focused,current?.status)
  const {scene,frames,events}=replay
  const chosenMap=maps.find(m=>m.id===mapId)
  function navigate(next:Tab,experiment=experimentId,match=focused){history.pushState(null,'',routeHash(next,experiment,match));setTabState(next);setExperimentId(experiment);setFocusedState(match)}
  function setTab(next:Tab){navigate(next)}
  function setFocused(next:string|((old:string)=>string)){const value=typeof next==='function'?next(focused):next;navigate('arena',experimentId,value)}
  const openExperiment=useCallback((id:string)=>{history.pushState(null,'',routeHash('lab',id));setExperimentId(id);setTabState('lab')},[])
  useEffect(()=>{const sync=()=>{const r=readRoute(location.hash);setTabState(r.tab);setExperimentId(r.experiment);setFocusedState(r.match)};window.addEventListener('hashchange',sync);window.addEventListener('popstate',sync);return()=>{window.removeEventListener('hashchange',sync);window.removeEventListener('popstate',sync)}},[])


  const refresh=useCallback(async()=>{
    const [fs,ms,rs]=await Promise.all([api<Fly[]>('/flies'),api<Match[]>('/matches'),api<Ranking[]>('/leaderboard')]);setFlies(fs);setMatches(ms);setRankings(rs)
  },[])
  useEffect(()=>{
    api<AuthSettings>('/auth/config').then(async settings=>{
      setAuthSettings(settings)
      if(settings.mode==='nyxid'){
        setIdentity(null)
        const session=await api<{authenticated:boolean;user:Identity|null;csrf_token:string|null}>('/auth/session')
        setCsrfToken(session.csrf_token);setIdentity(session.user)
      }else{
        try{const cached=JSON.parse(localStorage.getItem('flyarena.identity')||'null') as Identity|null;if(cached?.token){const verified=await api<Identity>('/me',{},cached);setIdentity({...verified,token:cached.token})}else setIdentity(null)}catch{setIdentity(null)}
      }
    }).catch(e=>setError(t("登录配置加载失败：")+e.message))
    const url=new URL(window.location.href)
    if(url.searchParams.has('auth_error')){setError(t("NyxID 登录未完成，请重新点击登录。"));url.searchParams.delete('auth_error');history.replaceState(null,'',url.pathname+url.search+url.hash)}
    const expired=()=>{setIdentity(null);setCsrfToken(null);setToast(t("登录已过期，请重新登录后继续。"))}
    window.addEventListener('arena:session-expired',expired)
    return()=>window.removeEventListener('arena:session-expired',expired)
  },[])
  useEffect(()=>{
    if(!season)return
    const pending=sessionStorage.getItem('flyarena.pendingDesign')
    if(pending){try{const draft=JSON.parse(pending);loadSpec(draft.spec||draft);if(draft.jsonEditor!==undefined)setJsonEditor(draft.jsonEditor);if(draft.tab)setTab(draft.tab);sessionStorage.removeItem('flyarena.pendingDesign')}catch(e){setError(String(e))}}
  },[authSettings?.mode,season])
  useEffect(()=>{
    if(showToken&&authSettings?.mode==='nyxid'&&identity&&!identity.token)api<{id:string;expires:number}[]>('/auth/agent-tokens').then(setAgentTokens).catch(e=>setError(e.message))
    if(!showToken)setFreshToken('')
  },[showToken,authSettings?.mode,identity?.id])
  useEffect(()=>{
    Promise.all([api<Season>('/season'),api<Fly[]>('/flies'),api<ArenaMap[]>('/maps'),api<Match[]>('/matches')]).then(([s,f,m,ms])=>{
      setSeason(s);setBridgeProfile(defaultMatchProfile(s));setFlies(f);setMaps(m);setMatches(ms);setFocusedState(old=>old||preferredReplay(ms)?.id||'')
      if(f.length){setOpponent(f.length>1?f[1].id:f[0].id)}
    }).catch(e=>setError(e.message))
    api<Preview>('/preview').then(setPreview).catch(e=>setError(t("身体模型加载失败：")+e.message))
    api<Ranking[]>('/leaderboard').then(setRankings).catch(()=>{})
  },[])
  useEffect(()=>{const timer=setInterval(()=>refresh().catch(()=>{}),2500);return()=>clearInterval(timer)},[refresh])
  useEffect(()=>{if(toast){const timer=setTimeout(()=>setToast(''),4500);return()=>clearTimeout(timer)}},[toast])
  useEffect(()=>{setPlaytime(0);setPlay(replay.status==='ready')},[focused,replay.status])
  useEffect(()=>{
    if(!play||!frames.length)return
    let id:number;let previous=performance.now()
    const animate=(now:number)=>{const dt=(now-previous)/1000;previous=now;setPlaytime(t=>{const next=t+dt*playbackSpeed;if(next>=frames[frames.length-1].time){setPlay(false);return frames[frames.length-1].time}return next});id=requestAnimationFrame(animate)}
    id=requestAnimationFrame(animate);return()=>cancelAnimationFrame(id)
  },[play,frames,playbackSpeed])

  const spec=useMemo<Spec>(()=>composeSpec(baseSpec,{schema_version:'flyspec/v1',name,description:baseSpec.description??'Designed in Fly Arena',color,parent_id:parentId,
    connectome_sha256:baseSpec.connectome_sha256||season?.connectome.sha256||'',model_profile:baseSpec.model_profile||'malecns-lif-cpu-v1',
    weight_mutations:Object.entries(scales).filter(([,v])=>Math.abs(v-1)>.00001).map(([selector,scale])=>({selector,scale})),
    edge_deltas:edgeDeltas,interventions,neuron_parameters:{...baseSpec.neuron_parameters,tau_scale:tau,threshold_shift_mv:threshold},plasticity:baseSpec.plasticity||'none'}),[baseSpec,interventions,name,color,parentId,season,scales,edgeDeltas,tau,threshold])

  function clone(fly:Fly){setParentId(fly.id);setBaseSpec(fly.spec);setInterventions(fly.spec.interventions||[]);setSelected(fly.id);setName(fly.name.split(' / ')[0]+' 02');setColor(fly.color);const values:Record<string,number>=defaultScales();for(const m of fly.spec.weight_mutations)values[m.selector]=(values[m.selector]??1)*m.scale;setScales(values);setTau(fly.spec.neuron_parameters.tau_scale);setThreshold(fly.spec.neuron_parameters.threshold_shift_mv);setEdgeDeltas(fly.spec.edge_deltas);setReport(null)}
  async function action(label:string,fn:()=>Promise<void>){setBusy(label);setError('');try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}}
  function loginNyxID(){if(!authSettings?.login_url)return;try{sessionStorage.setItem('flyarena.pendingDesign',JSON.stringify({spec,jsonEditor,tab}));window.location.assign(authSettings.login_url)}catch(e){setError(String(e))}}
  async function createAgentToken(){await action('agent-token',async()=>{const key=await api<{token:string}>('/auth/agent-tokens',{method:'POST'});setFreshToken(key.token);setAgentTokens(await api('/auth/agent-tokens'))})}
  async function logout(){await action('logout',async()=>{if(authSettings?.mode==='nyxid'&&!identity?.token)await api('/auth/logout',{method:'POST'});setIdentity(null);setCsrfToken(null);setFreshToken('');if(authSettings?.mode==='local')localStorage.removeItem('flyarena.identity');setShowToken(false)})}
  async function register(){await action('identity',async()=>{const user=await api<Identity>('/identities',{method:'POST',body:JSON.stringify({name:identityName||'Explorer'}),headers:{'X-Invite-Code':invite}});setIdentity(user);localStorage.setItem('flyarena.identity',JSON.stringify(user));setLogin(false);setToast(t("设计师身份已创建，现在可以保存与参赛。"))})}
  async function validate(){if(!identity){setLogin(true);return}await action('validate',async()=>{const r=await api<Report>('/flies/validate',{method:'POST',body:JSON.stringify(spec)},identity);setReport(r);setToast(t("权重、图谱版本和变异预算验证通过。"))})}
  async function previewNeural(){if(!identity){setLogin(true);return}await action('neural-preview',async()=>{const result=await api<NeuralPreview>('/flies/preview',{method:'POST',body:JSON.stringify(spec)},identity);setNeuralPreview(result);setToast(t('Neural preview recorded from the retained graph.'))})}
  async function publish(){if(!identity){setLogin(true);return}await action('publish',async()=>{const fly=await api<Fly>('/flies',{method:'POST',body:JSON.stringify(spec)},identity);await refresh();setSelected(fly.id);setReport(fly.report);setBaseSpec(fly.spec);setParentId(fly.id);setTab('train');setToast(t('Design saved. Choose a strategy and budget to start training.'))})}
  async function startMatch(){if(!season?.match_profiles?.some(p=>p.id===bridgeProfile&&p.ready)){setError(t('Selected match profile is unavailable.'));return}if(!identity){setLogin(true);return}if(!selected){setError(t("请先选择或保存一只果蝇。"));return}await action('match',async()=>{const match=await api<Match>('/matches',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({fly_ids:mode==='forage'?[selected]:[selected,opponent||selected],map_id:mapId,mode,seed,duration_seconds:duration,bridge_profile:bridgeProfile,sensory_profile:selectedSensoryProfile})},identity);setFocused(match.id);await refresh();setToast(t("比赛已进入仿真队列，完成后自动加载回放。"))})}
  async function startSeries(){if(!season?.match_profiles?.some(p=>p.id===bridgeProfile&&p.ready)){setError(t('Selected match profile is unavailable.'));return}if(!identity){setLogin(true);return}if(selected===(opponent||selected)){setError(t("系列赛需要两只不同的果蝇"));return}await action('series',async()=>{const series=await api<{id:string;matches:Match[]}>('/tournaments',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({name:t("双循环 / ")+(selectedFly?.name||'Fly'),fly_ids:[selected,opponent],map_id:mapId,mode:mode==='sumo'?'sumo':'contest',seeds:[seed],duration_seconds:duration,bridge_profile:bridgeProfile,sensory_profile:selectedSensoryProfile})},identity);setFocused(series.matches[0].id);await refresh();setToast(t("双循环已创建：同一地图与种子，两场交换出生位置的比赛。"))})}
  function loadSpec(value:Spec){assertSpec(value);setParentId(value.parent_id||null);setBaseSpec(value);setInterventions(value.interventions||[]);setName(value.name);setColor(value.color);setSelected(value.parent_id||'');const values:Record<string,number>=defaultScales();for(const m of value.weight_mutations)values[m.selector]=(values[m.selector]??1)*m.scale;setScales(values);setTau(value.neuron_parameters?.tau_scale??1);setThreshold(value.neuron_parameters?.threshold_shift_mv??0);setEdgeDeltas(value.edge_deltas||[]);setReport(null);setTab('design');setToast(t("设计已导入；保存时将再次通过服务端验证。"))}
  const estimated=useMemo(()=>{
    if(!season)return 0
    // This is labeled an estimate. The authoritative compiler uses synapse-weighted costs.
    const e=season.connectome.edge_count
    return Object.entries(scales).reduce((s,[k,v])=>s+(season.connectome.circuits.find(c=>c.id===k)?.edge_count||0)/e*Math.abs(Math.log(v))/.08*100,0)+100*Math.abs(Math.log(tau))+20*Math.abs(threshold)
  },[scales,tau,threshold,season])
  const used=report?.budget_used??estimated
  const {frame,next,alpha}=selectReplayFrames(frames,playtime)

  return <div className="app-shell">
    <header className="header">
      <button className="brand" onClick={()=>setTab('design')} aria-label={t("Fly Arena 首页")}><span className="brand-mark"><Bug size={22} strokeWidth={1.6}/></span><span>fly<span className="brand-light">arena</span><sup>α</sup></span></button>
      <nav>{([['design',t("设计工坊"),Dna],['train',t('Training sandbox'),GitBranch],['life',t('Life archive'),GitBranch],['lab',t("表型实验室"),FlaskConical],['arena',t("竞技场"),Swords],['code','AI / API',Code2]] as const).map(([id,label,Icon])=><button className={tab===id?'active':''} key={id} onClick={()=>setTab(id)}><Icon size={15}/>{label}</button>)}</nav>
      <div className="header-right"><Preferences/><span className="season-badge"><span className="live-dot"/>{t("GENESIS SEASON")}</span><button className="identity-button" onClick={()=>identity?setShowToken(true):setLogin(true)}><UserRound size={16}/><span>{identity?.name||t("加入实验")}</span></button></div>
    </header>

    <main>
      <div className="page-heading"><div><div className="eyebrow"><span/> {t("AN OPEN EVOLUTIONARY PLAYGROUND")}</div><h1>{tab==='design'?<>{t("小小生命，")}<em>{t("无限可能。")}</em></>:tab==='life'?<>{t('Every life,')}<em>{t('a recorded journey.')}</em></>:tab==='train'?<>{t('Train a fly,')}<em>{t('grow a lineage.')}</em></>:tab==='arena'?<>{t("让你的设计，")}<em>{t("接受挑战。")}</em></>:tab==='lab'?<>{t("每次进化，")}<em>{t("都有迹可循。")}</em></>:<>{t("你的 AI，")}<em>{t("也是设计师。")}</em></>}</h1><p>{tab==='design'?t("从真实果蝇神经图谱出发。改变连接，塑造本能，创造属于你的数字果蝇。"):tab==='life'?t('Explore individuals, experiences and choices. Continue evolution from recorded evidence.'):tab==='train'?t('Choose a strategy, set a budget, and explore generations through actual competition.'):tab==='arena'?t("同一身体，同一世界。让不同的神经设计，在食物与空间的竞争中相遇。"):tab==='lab'?t("比较设计、回看行为、追踪神经活动。让下一次修改有据可依。"):t("一份 FlySpec，一套开放接口。让任何 AI 设计、评测并提交自己的果蝇。")}</p></div><div className="science-stamp"><span>{t("BUILT ON REAL BIOLOGY")}</span><strong>MaleCNS <i>v1.0</i></strong><small>{season?num(season.connectome.neuron_count):'—'} {t("neurons · Full retained graph")}<ArrowUpRight size={12}/></small></div></div>

      {error&&<div className="error-banner" role="alert"><span>{error}</span><button onClick={()=>setError('')} aria-label={t("关闭错误")}><X size={16}/></button></div>}

      {tab==='design'&&<>
        <PlaygroundGuide neuronCount={season?.connectome.neuron_count}
          canCloneWT={!!matchingWildType(flies)} hasSavedDesign={!!identity&&flies.some(f=>f.owner===identity.id)}
          onDesign={()=>{document.getElementById('fly-name')?.scrollIntoView({block:'center',behavior:'smooth'});document.getElementById('fly-name')?.focus({preventScroll:true})}}
          onCloneWT={()=>{const wt=matchingWildType(flies);if(wt){clone(wt);setToast(locale==='zh-CN'?'已复制 WT 为草稿。修改并保存后，再训练或挑战。':'WT copied into a draft. Edit and save it before training or competing.');document.getElementById('fly-name')?.focus()}}}
          onTrain={()=>setTab('train')} onArena={()=>{setFocused('');setPlay(false)}}
          onAI={()=>{setJsonEditor(JSON.stringify(spec,null,2));setTab('code')}}/>
        <div className="design-workspace">
          <aside className="collection panel"><div className="panel-heading"><span>{t("我的果蝇库")}</span><span className="count">{flies.length.toString().padStart(2,'0')}</span></div><div className="tiny-label">{t("SELECT A STARTING POINT")}</div><p className="draft-status">{parentId?t('Unsaved draft from parent')+': '+parentId:t('Unsaved canonical draft')}</p>
            <div className="fly-list">{flies.slice(0,12).map(f=><SavedFlyCard key={f.id} fly={f} viewer={identity?.id} selected={parentId===f.id} onClone={clone}/>)}</div>
            <button className="new-fly" onClick={()=>{setScales(defaultScales());setTau(1);setThreshold(0);setName('Untitled 01');setSelected('');setParentId(null);setBaseSpec({});setInterventions([]);setEdgeDeltas([]);setReport(null);setToast(t("已恢复基线参数，为新设计取个名字吧。"))}}><Plus size={15}/>{t("从原型开始设计")}</button>
            <div className="collection-footer"><GitBranch size={18}/><strong>{t("进化，有迹可循")}</strong><p>{t("每个设计都保留图谱来源、父代和不可变的权重版本。")}</p><button onClick={()=>setTab('train')}>{t("Training sandbox")}<ArrowRight size={14}/></button></div>
          </aside>

          <section className="specimen-panel"><div className="specimen-top"><span><span className="live-dot"/> {t("SPECIMEN /")}{name||t('NEW DESIGN')}</span><span>NEUROMECHFLY</span></div>
            <div className="specimen-canvas">{preview?<ArenaCanvas preview={preview} color={color} design/>:<div className="canvas-loading"><Loader2 className="spin"/><span>{t("正在载入真实身体模型")}</span></div>}</div>
            <div className="specimen-label"><span className="italic-label">Drosophila melanogaster</span><small>{t("黑腹果蝇 · 解剖模型预览")}</small></div>
            <div className="specimen-controls"><span>{t("拖动旋转 · 滚轮缩放")}</span><button onClick={()=>{setInspectOpen(true);api<typeof inspect>('/connectome/neurons?circuit='+inspectCircuit).then(setInspect).catch(e=>setError(e.message))}}><AudioLines size={15}/>{t("探索真实神经元")}<ArrowUpRight size={12}/></button></div>
            <div className="specimen-stats"><div><span>{t("NEURONS")}</span><strong>{season?num(season.connectome.neuron_count):'—'}</strong></div><div><span>{t("CONNECTIONS")}</span><strong>{season?(season.connectome.edge_count/1e6).toFixed(2)+'M':'—'}</strong></div><div><span>{t("BODY MODEL")}</span><strong>MuJoCo <small>3.9</small></strong></div></div>
          </section>

          <aside className="editor panel"><div className="panel-heading"><span><Settings2 size={16}/> {t("神经设计")}</span><button className="icon-button" title={t("重置参数")} onClick={()=>{setScales(defaultScales());setTau(1);setThreshold(0);setInterventions([]);setEdgeDeltas([]);setReport(null)}}><RotateCcw size={15}/></button></div>
            <label className="field-label" htmlFor="fly-name">{t("给你的果蝇命名")}</label><input id="fly-name" value={name} onChange={e=>setName(e.target.value)} maxLength={64}/>
            <div className="color-row"><span>{t("个体标记")}</span><div>{Object.entries(colors).map(([key,value])=><button key={key} title={t(key)} aria-label={t("选择 ")+t(key)+t(" 配色")} className={color===key?'chosen':''} style={{background:value}} onClick={()=>setColor(key)}>{color===key&&<Check size={11}/>}</button>)}</div></div>
            <div className="section-divider"/>
            <BrainModelPicker value={spec.model_profile} onChange={model=>{setBaseSpec(old=>({...old,model_profile:model}));setReport(null)}}/>
            <div className="controls-caption"><strong>{t("连接权重")}</strong><span>{t("原型 × 1.00")}</span></div>
            <p className="capability-note">{t('Primary: olfactory → projection / local → readout loop. Vision, memory and motor edits are exploratory; vision input and learning are unavailable.')}</p><div className="sliders">{season?.connectome.circuits.filter(c=>!['visual','memory','motor'].includes(c.id)).map(c=><label key={c.id} className={'slider-control '+(['visual','memory','motor'].includes(c.id)?'exploratory':'primary-control')}><span><span className="circuit-dot" style={{background:c.color}}/>{t(c.label)}<small>× {scales[c.id]?.toFixed(2)}</small></span><input aria-label={t(c.label)+' '+t('Weight')} type="range" min="0.5" max="2" step=".01" value={scales[c.id]??1} onChange={e=>{setScales(s=>({...s,[c.id]:Number(e.target.value)}));setReport(null)}}/></label>)}</div><details className="exploratory-controls"><summary>{t('Exploratory edits: vision, memory and motor')}</summary><p>{t('These edits do not enable vision, memory tasks, learning or additional motor action channels.')}</p><div className="sliders">{season?.connectome.circuits.filter(c=>['visual','memory','motor'].includes(c.id)).map(c=><label key={c.id} className={'slider-control '+(['visual','memory','motor'].includes(c.id)?'exploratory':'primary-control')}><span><span className="circuit-dot" style={{background:c.color}}/>{t(c.label)}<small>× {scales[c.id]?.toFixed(2)}</small></span><input aria-label={t(c.label)+' '+t('Weight')} type="range" min="0.5" max="2" step=".01" value={scales[c.id]??1} onChange={e=>{setScales(s=>({...s,[c.id]:Number(e.target.value)}));setReport(null)}}/></label>)}</div></details>
            <details className="intrinsic"><summary>{t("神经元动力学")}<ChevronDown size={13}/></summary><label>{t("膜时间常数")}<b>× {tau.toFixed(2)}</b><input aria-label={t("膜时间常数")} type="range" min=".8" max="1.2" step=".01" value={tau} onChange={e=>{setTau(+e.target.value);setReport(null)}}/></label><label>{t("发放阈值变化")}<b>{threshold>0?'+':''}{threshold.toFixed(1)} {t("mV")}</b><input aria-label={t("发放阈值")} type="range" min="-1" max="1" step=".1" value={threshold} onChange={e=>{setThreshold(+e.target.value);setReport(null)}}/></label></details>
            <div className={'budget '+(used>100?'over':'')}><div><span>{report?t("已验证预算"):t("预算估算")}</span><strong>{used.toFixed(1)} <small>/ 100</small></strong></div><div className="budget-track"><span style={{width:Math.min(100,used)+'%'}}/></div><p>{report?`${num(report.changed_edges)} ${t('Changed connections')}`:t("强化与削弱都消耗预算，最终由服务端核算。")}</p>{!report&&(interventions.length>0||edgeDeltas.length>0)&&<p>{t('Estimate excludes advanced and edge edits. Validate for the authoritative total.')}</p>}</div>
            <div className="editor-actions"><button className="secondary" onClick={validate} disabled={!!busy}>{busy==='validate'?<Loader2 className="spin" size={15}/>:<ShieldCheck size={15}/>}{t("验证")}</button><button className="secondary" onClick={previewNeural} disabled={!!busy||!season}>{busy==='neural-preview'?<Loader2 className="spin" size={15}/>:<AudioLines size={15}/>}{t('Preview neural response')}</button><button className="primary" onClick={publish} disabled={!!busy||!season}>{busy==='publish'?<Loader2 className="spin" size={15}/>:<Plus size={15}/>}{t("保存果蝇")}</button></div>
          </aside>
        </div>
        {neuralPreview&&<section className="panel neural-design-preview"><div className="panel-heading"><span><AudioLines size={16}/>{t('Design neural preview')}</span><small>{t('Fixed bilateral stimuli · actual model state')}</small></div><p>{t('This preview runs the submitted FlySpec through the retained connectome. It has no body, score or ranking.')}</p><div className="neural-preview-grid">{neuralPreview.stimuli.map((row,index)=><article key={index}><span>{t('Stimulus')} · {row.stimulus.left.toFixed(1)} / {row.stimulus.right.toFixed(1)}</span>{Object.entries(row.circuits).slice(0,6).map(([id,value])=><div key={id}><small>{t(season?.connectome.circuits.find(c=>c.id===id)?.label||id)}</small><strong>{value.toFixed(2)} <em>Hz</em></strong><i><b style={{width:`${Math.min(100,value/250*100)}%`}}/></i></div>)}</article>)}</div><code>{neuralPreview.model_profile} · {neuralPreview.artifact_id.slice(0,16)} · {t('50 neural steps per stimulus')}</code></section>}
        <AdvancedInterventions value={interventions} onChange={v=>{setInterventions(v);setReport(null)}} report={report} spec={spec} onValidate={validate} busy={!!busy}/>
        <div className="section-title"><div><span className="eyebrow">{t("CHOOSE YOUR CHALLENGE")}</span><h2>{t("下一站，竞技场。")}</h2></div><button className="text-link" onClick={()=>setTab('arena')}>{t("探索全部环境")}<ArrowUpRight size={16}/></button></div>
        <div className="map-grid">{maps.map((m,i)=><button className="map-card" key={m.id} onClick={()=>{setMapId(m.id);setMode(m.id==='ring'?'sumo':'contest');setFocused('');setPlay(false)}}><div className="map-card-top"><span>0{i+1} / {(locale==='en'?m.english:m.name).toUpperCase()}</span><ArrowUpRight size={17}/></div><MapDrawing map={m}/><div className="map-card-bottom"><div><h3>{locale==='en'?m.english:m.name}</h3><p>{m.id==='orchard'?t("感知 · 探索 · 觅食"):m.id==='maze'?t("路径 · 障碍 · 适应"):m.id==='scarcity'?t("稀缺 · 竞争 · 耗尽"):m.id==='terrarium'?(locale==='en'?'Slopes · routes · shared food':'坡地 · 多路 · 共享食物'):t("接触 · 推挤 · 争夺")}</p></div><span className="map-tag">{m.id==='ring'?t("对抗"):t("觅食")}</span></div></button>)}<div className="ai-card"><span className="ai-icon"><Sparkles size={21}/></span><span className="eyebrow">{t("CO-DESIGN WITH AI")}</span><h3>{t("让 AI，")}<br/>{t("设计它的第一只果蝇。")}</h3><p>{t("开放 FlySpec 与 API。")}<br/>{t("你的 agent，可以直接加入。")}</p><button onClick={()=>{setJsonEditor(JSON.stringify(spec,null,2));setTab('code')}}>{t("接入你的 AI")}<ArrowRight size={16}/></button></div></div>
      </>}

      {tab==='arena'&&<ArenaFeature replayStatus={!current&&focused?(matchError?'error':'loading'):replay.status} replayError={matchError||replay.error} bridgeProfile={bridgeProfile} setBridgeProfile={setBridgeProfile} sensoryProfile={selectedSensoryProfile} setSensoryProfile={setSensoryProfile} scene={scene} frame={frame} next={next} alpha={alpha} focused={focused} preview={preview} selectedFly={selectedFly} chosenMap={chosenMap} current={current} selected={selected} identity={identity} flies={availableFlies} frames={frames} events={events} play={play} playtime={playtime} playbackSpeed={playbackSpeed} setPlay={setPlay} setPlaytime={setPlaytime} setPlaybackSpeed={setPlaybackSpeed} season={season} matches={matches} setFocused={setFocused} maps={maps} setSelected={setSelected} mapId={mapId} setMapId={setMapId} mode={mode} setMode={setMode} opponent={opponent} setOpponent={setOpponent} duration={duration} setDuration={setDuration} seed={seed} setSeed={setSeed} busy={busy||(replay.status==='loading'?'replay':'')} startMatch={startMatch} startSeries={startSeries}/>}

      {tab==='train'&&<TrainingSandbox flies={availableFlies} identity={identity} selected={selected} season={season} maps={maps} onLogin={()=>setLogin(true)} onSaved={async fly=>{await refresh();setSelected(fly.id)}} onCompete={(fly,setup)=>{setSelected(fly.id);const configured=setup?.opponent_id?flies.find(item=>item.id===setup.opponent_id):undefined;const reference=configured||matchingWildType(flies,fly);if(reference)setOpponent(reference.id);setMode('contest');if(setup){setMapId(setup.map_id);setSeed(setup.seed);setDuration(setup.duration_seconds)}setFocused('');setPlay(false)}} onReplay={match=>{setMatches(old=>[match,...old.filter(m=>m.id!==match.id)]);setFocused(match.id)}}/>}

      {tab==='life'&&<LifeLedger identity={identity} selected={selected} onBranch={fly=>{setBranchFly(fly);setSelected(fly.id);setTab('train')}} onCompete={fly=>{setBranchFly(fly);setSelected(fly.id);const wt=matchingWildType(flies,fly);if(wt)setOpponent(wt.id);setMode('contest');setFocused('');setPlay(false)}} onReplay={match=>{setMatches(old=>[match,...old.filter(m=>m.id!==match.id)]);setFocused(match.id)}}/>}

      {tab==='lab'&&<PhenotypeLab flies={flies} identity={identity} selected={selected} experimentId={experimentId} onExperiment={openExperiment} onLogin={()=>setLogin(true)}/>}

      {tab==='code'&&<DevelopersFeature jsonEditor={jsonEditor} setJsonEditor={setJsonEditor} spec={spec} download={download} fileInput={fileInput} loadSpec={loadSpec} setError={setError} identity={identity} setShowToken={setShowToken} setLogin={setLogin}/>}

      <p className="small-print" style={{marginTop:24}}>{t("研究预览：完整保留图采用简化 LIF 动力学；当前输入为双侧气味，运动读出与步态控制器固定。视觉与学习尚未接入。权重变化的行为效果需通过比赛验证。")}</p><footer><span><Bug size={14}/> FLY ARENA <i>by The Omega Institute</i></span><span>{t("真实图谱 · 可变神经网络 · 开放竞技")}</span><a href="https://male-cns.janelia.org/" target="_blank" rel="noreferrer">{t("MaleCNS 数据来源")}<ArrowUpRight size={12}/></a></footer>
    </main>
    {toast&&<div className="toast" role="status"><Check size={17}/>{toast}</div>}
      <AuthDialogs login={login} setLogin={setLogin} authSettings={authSettings} error={error} setError={setError} loginNyxID={loginNyxID} identityName={identityName} setIdentityName={setIdentityName} season={season} invite={invite} setInvite={setInvite} busy={busy} register={register} setIdentity={setIdentity} showToken={showToken} setShowToken={setShowToken} identity={identity} freshToken={freshToken} setFreshToken={setFreshToken} setToast={setToast} createAgentToken={createAgentToken} agentTokens={agentTokens} setAgentTokens={setAgentTokens} action={action} logout={logout}/>

    {inspectOpen&&<div className="modal-backdrop"><section className="modal neuron-modal"><button className="modal-close icon-button" onClick={()=>setInspectOpen(false)} aria-label={t("关闭")}><X size={19}/></button><div className="eyebrow">{t("REAL NEURONS · REAL CONNECTIONS")}</div><h2>{t("走进真实回路。")}</h2><select aria-label={t("查看神经回路")} value={inspectCircuit} onChange={e=>{setInspectCircuit(e.target.value);api<typeof inspect>('/connectome/neurons?circuit='+e.target.value).then(setInspect).catch(x=>setError(x.message))}}>{season?.connectome.circuits.map(c=><option key={c.id} value={c.id}>{t(c.label)}</option>)}</select><p>{t("这里展示所选回路的前 80 个真实神经元；仿真运行完整的保留图。")}</p><div className="neuron-list">{inspect?.neurons.map(n=><div key={n.id}><span className="neuron-dot"/><strong>{n.type||t('Unannotated')}</strong><code>{n.id}</code><small>{n.nt||t('unknown')}</small></div>)}</div><small>{inspect?.edges.length||0} {t("条样本内连接 · ID 来自 MaleCNS v1.0")}</small></section></div>}
  </div>
}
