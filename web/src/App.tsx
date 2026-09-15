import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import {ArrowDownToLine,ArrowRight,ArrowUpRight,AudioLines,Beaker,Bug,Check,ChevronDown,Code2,Copy,Dna,ExternalLink,FlaskConical,GitBranch,Leaf,Loader2,Pause,Play,Plus,RotateCcw,Settings2,ShieldCheck,Sparkles,Swords,Terminal,Trophy,UserRound,X} from 'lucide-react'
import {api} from './api'
import {ArenaCanvas} from './ArenaCanvas'
import type {ArenaMap,Fly,Frame,Identity,Match,Preview,Report,Scene,Season,Spec} from './types'
import {colors,modes,num} from './types'

type Tab='design'|'arena'|'lab'|'code'
type Ranking={fly:Fly;wins:number;draws:number;losses:number;matches:number;food:number;points:number}
const defaultScales=()=>({olfactory:1,projection:1,local:1,memory:1,readout:1,descending:1,visual:1,motor:1})

function MapDrawing({map}:{map:ArenaMap}){
  return <svg viewBox="0 0 220 105" className={'map-drawing '+map.id} aria-hidden="true">
    <defs><pattern id={'grid-'+map.id} width="14" height="14" patternUnits="userSpaceOnUse"><path d="M14 0H0V14" fill="none" stroke="currentColor" strokeWidth=".45" opacity=".18"/></pattern></defs>
    <rect x="8" y="3" width="204" height="98" rx="9" fill={'url(#grid-'+map.id+')'}/>
    {map.id==='ring'?<><ellipse cx="110" cy="54" rx="57" ry="38" fill="none" stroke="currentColor" strokeWidth="1.5"/><ellipse cx="110" cy="54" rx="46" ry="30" fill="none" stroke="currentColor" opacity=".15"/><path d="M62 68L145 28M78 80L158 40" stroke="currentColor" opacity=".09"/></>:map.id==='maze'?<><path d="M83 19v49h-23M137 88V39h24" fill="none" stroke="currentColor" strokeWidth="7"/><path d="M40 50h25q10 0 10 14v9q0 8 20 8h24" fill="none" stroke="currentColor" strokeDasharray="3 4" opacity=".45"/></>:<><path d="M39 62Q70 16 109 53T175 44" fill="none" stroke="currentColor" strokeDasharray="3 4" opacity=".4"/>{[[75,27],[112,61],[163,34],[57,80],[168,79]].map(([x,y],i)=><g key={i}><circle cx={x} cy={y} r="10" fill="currentColor" opacity=".07"/><circle cx={x} cy={y} r="3" fill="currentColor" opacity=".7"/></g>)}</>}
    <g transform="translate(54,55) rotate(-25)"><ellipse rx="4" ry="2.5" fill="currentColor"/><path d="M-1 -2l-4 -4m4 8l-4 4M1 -2l2 -4m-2 8l2 4" stroke="currentColor" strokeWidth=".8"/></g>
    <g transform="translate(166,53) rotate(150)"><ellipse rx="4" ry="2.5" fill="currentColor"/><path d="M-1 -2l-4 -4m4 8l-4 4M1 -2l2 -4m-2 8l2 4" stroke="currentColor" strokeWidth=".8"/></g>
  </svg>
}

function download(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}

export default function App(){
  const [tab,setTab]=useState<Tab>('design')
  const [season,setSeason]=useState<Season|null>(null)
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
  const [identity,setIdentity]=useState<Identity|null>(()=>{try{return JSON.parse(localStorage.getItem('flyarena.identity')||'null')}catch{return null}})
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
  const [focused,setFocused]=useState<string>('')
  const [scene,setScene]=useState<Scene|null>(null)
  const [frames,setFrames]=useState<Frame[]>([])
  const [play,setPlay]=useState(false)
  const [playtime,setPlaytime]=useState(0)
  const [playbackSpeed,setPlaybackSpeed]=useState(1)
  const [jsonEditor,setJsonEditor]=useState('')
  const [inspect,setInspect]=useState<{neurons:{id:string;type:string;nt:string}[];edges:{pre:string;post:string;count:number}[]}|null>(null)
  const [inspectOpen,setInspectOpen]=useState(false)
  const [inspectCircuit,setInspectCircuit]=useState('descending')
  const fileInput=useRef<HTMLInputElement>(null)
  const selectedFly=flies.find(f=>f.id===selected)
  const current=matches.find(m=>m.id===focused)
  const chosenMap=maps.find(m=>m.id===mapId)

  const refresh=useCallback(async()=>{
    const [fs,ms,rs]=await Promise.all([api<Fly[]>('/flies'),api<Match[]>('/matches'),api<Ranking[]>('/leaderboard')]);setFlies(fs);setMatches(ms);setRankings(rs)
  },[])
  useEffect(()=>{
    Promise.all([api<Season>('/season'),api<Fly[]>('/flies'),api<ArenaMap[]>('/maps'),api<Match[]>('/matches')]).then(([s,f,m,ms])=>{
      setSeason(s);setFlies(f);setMaps(m);setMatches(ms)
      if(f.length){setSelected(f[f.length-1].id);setOpponent(f.length>1?f[1].id:f[0].id)}
    }).catch(e=>setError(e.message))
    api<Preview>('/preview').then(setPreview).catch(e=>setError('身体模型加载失败：'+e.message))
    api<Ranking[]>('/leaderboard').then(setRankings).catch(()=>{})
  },[])
  useEffect(()=>{const timer=setInterval(()=>refresh().catch(()=>{}),2500);return()=>clearInterval(timer)},[refresh])
  useEffect(()=>{if(toast){const timer=setTimeout(()=>setToast(''),4500);return()=>clearTimeout(timer)}},[toast])
  useEffect(()=>{
    if(current?.status!=='verified'){setScene(null);setFrames([]);return}
    let active=true
    setBusy('replay')
    Promise.all([api<Scene>(`/matches/${focused}/scene`),api<Frame[]>(`/matches/${focused}/frames`)]).then(([s,f])=>{if(active){setScene(s);setFrames(f);setPlaytime(0);setPlay(true)}}).catch(e=>setError(e.message)).finally(()=>{if(active)setBusy('')})
    return()=>{active=false}
  },[focused,current?.status])
  useEffect(()=>{
    if(!play||!frames.length)return
    let id:number;let previous=performance.now()
    const animate=(now:number)=>{const dt=(now-previous)/1000;previous=now;setPlaytime(t=>{const next=t+dt*playbackSpeed;if(next>=frames[frames.length-1].time){setPlay(false);return frames[frames.length-1].time}return next});id=requestAnimationFrame(animate)}
    id=requestAnimationFrame(animate);return()=>cancelAnimationFrame(id)
  },[play,frames,playbackSpeed])

  const spec=useMemo<Spec>(()=>({schema_version:'flyspec/v1',name,description:'Designed in Fly Arena',color,parent_id:selected||null,
    connectome_sha256:season?.connectome.sha256||'',model_profile:'malecns-lif-cpu-v1',
    weight_mutations:Object.entries(scales).filter(([,v])=>Math.abs(v-1)>.00001).map(([selector,scale])=>({selector,scale})),
    edge_deltas:edgeDeltas,neuron_parameters:{tau_scale:tau,threshold_shift_mv:threshold},plasticity:'none'}),[name,color,selected,season,scales,edgeDeltas,tau,threshold])

  function clone(fly:Fly){setSelected(fly.id);setName(fly.name.split(' / ')[0]+' 02');setColor(fly.color);const values:Record<string,number>=defaultScales();for(const m of fly.spec.weight_mutations)values[m.selector]*=m.scale;setScales(values);setTau(fly.spec.neuron_parameters.tau_scale);setThreshold(fly.spec.neuron_parameters.threshold_shift_mv);setEdgeDeltas(fly.spec.edge_deltas);setReport(null)}
  async function action(label:string,fn:()=>Promise<void>){setBusy(label);setError('');try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}}
  async function register(){await action('identity',async()=>{const user=await api<Identity>('/identities',{method:'POST',body:JSON.stringify({name:identityName||'Explorer'}),headers:{'X-Invite-Code':invite}});setIdentity(user);localStorage.setItem('flyarena.identity',JSON.stringify(user));setLogin(false);setToast('设计师身份已创建，现在可以保存与参赛。')})}
  async function validate(){if(!identity){setLogin(true);return}await action('validate',async()=>{const r=await api<Report>('/flies/validate',{method:'POST',body:JSON.stringify(spec)},identity);setReport(r);setToast('权重、图谱版本和变异预算验证通过。')})}
  async function publish(){if(!identity){setLogin(true);return}await action('publish',async()=>{const fly=await api<Fly>('/flies',{method:'POST',body:JSON.stringify(spec)},identity);await refresh();setSelected(fly.id);setReport(fly.report);setToast('果蝇已保存。它的网络版本已冻结，可以参赛了。')})}
  async function startMatch(){if(!identity){setLogin(true);return}if(!selected){setError('请先选择或保存一只果蝇。');return}await action('match',async()=>{const match=await api<Match>('/matches',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({fly_ids:mode==='forage'?[selected]:[selected,opponent||selected],map_id:mapId,mode,seed,duration_seconds:duration})},identity);setFocused(match.id);setTab('arena');await refresh();setToast('比赛已进入仿真队列，完成后自动加载回放。')})}
  async function startSeries(){if(!identity){setLogin(true);return}if(selected===(opponent||selected)){setError('系列赛需要两只不同的果蝇');return}await action('series',async()=>{const series=await api<{id:string;matches:Match[]}>('/tournaments',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({name:'双循环 / '+(selectedFly?.name||'Fly'),fly_ids:[selected,opponent],map_id:mapId,mode:mode==='sumo'?'sumo':'contest',seeds:[seed],duration_seconds:duration})},identity);setFocused(series.matches[0].id);await refresh();setToast('双循环已创建：同一地图与种子，两场交换出生位置的比赛。')})}
  function loadSpec(value:Spec){if(value.connectome_sha256!==season?.connectome.sha256||value.model_profile!=='malecns-lif-cpu-v1'||value.plasticity!=='none')throw new Error('图谱、动力学或可塑性版本与当前赛季不兼容');if(value.schema_version!=='flyspec/v1'||!Array.isArray(value.weight_mutations))throw new Error('请选择有效的 FlySpec v1 JSON 文件');setName(value.name);setColor(value.color);setSelected(value.parent_id||'');const values:Record<string,number>=defaultScales();for(const m of value.weight_mutations)values[m.selector]*=m.scale;setScales(values);setTau(value.neuron_parameters?.tau_scale??1);setThreshold(value.neuron_parameters?.threshold_shift_mv??0);setEdgeDeltas(value.edge_deltas||[]);setReport(null);setTab('design');setToast('设计已导入；保存时将再次通过服务端验证。')}
  const estimated=useMemo(()=>{
    if(!season)return 0
    // This is labeled an estimate. The authoritative compiler uses synapse-weighted costs.
    const e=season.connectome.edge_count
    return Object.entries(scales).reduce((s,[k,v])=>s+(season.connectome.circuits.find(c=>c.id===k)?.edge_count||0)/e*Math.abs(Math.log(v))/.08*100,0)+100*Math.abs(Math.log(tau))+20*Math.abs(threshold)
  },[scales,tau,threshold,season])
  const used=report?.budget_used??estimated
  const frameIndex=frames.length?Math.max(0,frames.findIndex(f=>f.time>playtime)-1):0
  const index=frames.length&&playtime>=frames[frames.length-1].time?frames.length-1:frameIndex
  const frame=frames[index]
  const next=frames[Math.min(index+1,frames.length-1)]
  const alpha=frame&&next&&next.time>frame.time?(playtime-frame.time)/(next.time-frame.time):0

  return <div className="app-shell">
    <header className="header">
      <button className="brand" onClick={()=>setTab('design')} aria-label="Fly Arena 首页"><span className="brand-mark"><Bug size={22} strokeWidth={1.6}/></span><span>fly<span className="brand-light">arena</span><sup>α</sup></span></button>
      <nav>{([['design','设计工坊',Dna],['arena','竞技场',Swords],['lab','实验记录',FlaskConical],['code','AI / API',Code2]] as const).map(([id,label,Icon])=><button className={tab===id?'active':''} key={id} onClick={()=>setTab(id)}><Icon size={15}/>{label}</button>)}</nav>
      <div className="header-right"><span className="season-badge"><span className="live-dot"/>GENESIS SEASON</span><button className="identity-button" onClick={()=>identity?setShowToken(true):setLogin(true)}><UserRound size={16}/><span>{identity?.name||'加入实验'}</span></button></div>
    </header>

    <main>
      <div className="page-heading"><div><div className="eyebrow"><span/> AN OPEN EVOLUTIONARY PLAYGROUND</div><h1>{tab==='design'?<>小小生命，<em>无限可能。</em></>:tab==='arena'?<>让你的设计，<em>接受挑战。</em></>:tab==='lab'?<>每次进化，<em>都有迹可循。</em></>:<>你的 AI，<em>也是设计师。</em></>}</h1><p>{tab==='design'?'从真实果蝇神经图谱出发。改变连接，塑造本能，创造属于你的数字果蝇。':tab==='arena'?'同一身体，同一世界。让不同的神经设计，在食物与空间的竞争中相遇。':tab==='lab'?'比较设计、回看行为、追踪神经活动。让下一次修改有据可依。':'一份 FlySpec，一套开放接口。让任何 AI 设计、评测并提交自己的果蝇。'}</p></div><div className="science-stamp"><span>BUILT ON REAL BIOLOGY</span><strong>MaleCNS <i>v1.0</i></strong><small>{season?num(season.connectome.neuron_count):'165,122'} neurons · Full retained graph <ArrowUpRight size={12}/></small></div></div>

      {error&&<div className="error-banner" role="alert"><span>{error}</span><button onClick={()=>setError('')} aria-label="关闭错误"><X size={16}/></button></div>}

      {tab==='design'&&<>
        <div className="design-workspace">
          <aside className="collection panel"><div className="panel-heading"><span>我的果蝇库</span><span className="count">{flies.length.toString().padStart(2,'0')}</span></div><div className="tiny-label">SELECT A STARTING POINT</div>
            <div className="fly-list">{flies.slice(0,12).map(f=><button key={f.id} className={'fly-card '+(selected===f.id?'selected':'')} onClick={()=>clone(f)}><div className="fly-avatar" style={{'--fly-color':colors[f.color]} as React.CSSProperties}><Bug size={27} strokeWidth={1.1}/></div><div><strong>{f.name.split(' / ')[0]}</strong><small>{f.owner==='arena'?'Arena Lab · 起始设计':f.designer}</small></div>{selected===f.id&&<span className="selected-dot"/>}</button>)}</div>
            <button className="new-fly" onClick={()=>{setScales(defaultScales());setTau(1);setThreshold(0);setName('Untitled 01');setEdgeDeltas([]);setReport(null);setToast('已恢复基线参数，为新设计取个名字吧。')}}><Plus size={15}/>从原型开始设计</button>
            <div className="collection-footer"><GitBranch size={18}/><strong>进化，有迹可循</strong><p>每个设计都保留图谱来源、父代和不可变的权重版本。</p><button onClick={()=>setTab('lab')}>查看实验记录 <ArrowRight size={14}/></button></div>
          </aside>

          <section className="specimen-panel"><div className="specimen-top"><span><span className="live-dot"/> SPECIMEN / {selectedFly?.name.split(' / ')[0]||'NEW DESIGN'}</span><span>NEUROMECHFLY</span></div>
            <div className="specimen-canvas">{preview?<ArenaCanvas preview={preview} color={color} design/>:<div className="canvas-loading"><Loader2 className="spin"/><span>正在载入真实身体模型</span></div>}</div>
            <div className="specimen-label"><span className="italic-label">Drosophila melanogaster</span><small>黑腹果蝇 · 解剖模型预览</small></div>
            <div className="specimen-controls"><span>拖动旋转 · 滚轮缩放</span><button onClick={()=>{setInspectOpen(true);api<typeof inspect>('/connectome/neurons?circuit='+inspectCircuit).then(setInspect).catch(e=>setError(e.message))}}><AudioLines size={15}/>探索真实神经元 <ArrowUpRight size={12}/></button></div>
            <div className="specimen-stats"><div><span>NEURONS</span><strong>{season?num(season.connectome.neuron_count):'—'}</strong></div><div><span>CONNECTIONS</span><strong>{season?(season.connectome.edge_count/1e6).toFixed(2)+'M':'—'}</strong></div><div><span>BODY MODEL</span><strong>MuJoCo <small>3.9</small></strong></div></div>
          </section>

          <aside className="editor panel"><div className="panel-heading"><span><Settings2 size={16}/> 神经设计</span><button className="icon-button" title="重置参数" onClick={()=>{setScales(defaultScales());setTau(1);setThreshold(0);setEdgeDeltas([]);setReport(null)}}><RotateCcw size={15}/></button></div>
            <label className="field-label" htmlFor="fly-name">给你的果蝇命名</label><input id="fly-name" value={name} onChange={e=>setName(e.target.value)} maxLength={64}/>
            <div className="color-row"><span>个体标记</span><div>{Object.entries(colors).map(([key,value])=><button key={key} title={key} aria-label={'选择 '+key+' 配色'} className={color===key?'chosen':''} style={{background:value}} onClick={()=>setColor(key)}>{color===key&&<Check size={11}/>}</button>)}</div></div>
            <div className="section-divider"/>
            <div className="controls-caption"><strong>连接权重</strong><span>原型 × 1.00</span></div>
            <div className="sliders">{season?.connectome.circuits.map(c=><label key={c.id} className="slider-control"><span><span className="circuit-dot" style={{background:c.color}}/>{c.label}<small>× {scales[c.id]?.toFixed(2)}</small></span><input aria-label={c.label+'权重'} type="range" min="0.5" max="2" step=".01" value={scales[c.id]??1} onChange={e=>{setScales(s=>({...s,[c.id]:Number(e.target.value)}));setReport(null)}}/></label>)}</div>
            <details className="intrinsic"><summary>神经元动力学 <ChevronDown size={13}/></summary><label>膜时间常数 <b>× {tau.toFixed(2)}</b><input aria-label="膜时间常数" type="range" min=".8" max="1.2" step=".01" value={tau} onChange={e=>{setTau(+e.target.value);setReport(null)}}/></label><label>发放阈值变化 <b>{threshold>0?'+':''}{threshold.toFixed(1)} mV</b><input aria-label="发放阈值" type="range" min="-1" max="1" step=".1" value={threshold} onChange={e=>{setThreshold(+e.target.value);setReport(null)}}/></label></details>
            <div className={'budget '+(used>100?'over':'')}><div><span>{report?'已验证预算':'预算估算'}</span><strong>{used.toFixed(1)} <small>/ 100</small></strong></div><div className="budget-track"><span style={{width:Math.min(100,used)+'%'}}/></div><p>{report?`${num(report.changed_edges)} 条连接已修改`:'强化与削弱都消耗预算，最终由服务端核算。'}</p></div>
            <div className="editor-actions"><button className="secondary" onClick={validate} disabled={!!busy}>{busy==='validate'?<Loader2 className="spin" size={15}/>:<ShieldCheck size={15}/>}验证</button><button className="primary" onClick={publish} disabled={!!busy||!season}>{busy==='publish'?<Loader2 className="spin" size={15}/>:<Plus size={15}/>}保存果蝇</button></div>
          </aside>
        </div>
        <div className="section-title"><div><span className="eyebrow">CHOOSE YOUR CHALLENGE</span><h2>下一站，竞技场。</h2></div><button className="text-link" onClick={()=>setTab('arena')}>探索全部环境 <ArrowUpRight size={16}/></button></div>
        <div className="map-grid">{maps.map((m,i)=><button className="map-card" key={m.id} onClick={()=>{setMapId(m.id);setMode(m.id==='ring'?'sumo':'contest');setTab('arena')}}><div className="map-card-top"><span>0{i+1} / {m.english.toUpperCase()}</span><ArrowUpRight size={17}/></div><MapDrawing map={m}/><div className="map-card-bottom"><div><h3>{m.name}</h3><p>{m.id==='orchard'?'感知 · 探索 · 觅食':m.id==='maze'?'路径 · 障碍 · 适应':'接触 · 推挤 · 争夺'}</p></div><span className="map-tag">{m.id==='ring'?'对抗':'觅食'}</span></div></button>)}<div className="ai-card"><span className="ai-icon"><Sparkles size={21}/></span><span className="eyebrow">CO-DESIGN WITH AI</span><h3>让 AI，<br/>设计它的第一只果蝇。</h3><p>开放 FlySpec 与 API。<br/>你的 agent，可以直接加入。</p><button onClick={()=>{setJsonEditor(JSON.stringify(spec,null,2));setTab('code')}}>接入你的 AI <ArrowRight size={16}/></button></div></div>
      </>}

      {tab==='arena'&&<div className="arena-layout"><div className="arena-main"><div className="arena-stage">
        <div className="stage-heading"><span><span className="live-dot"/>{scene?'VERIFIED REPLAY':'ARENA / '+(chosenMap?.english.toUpperCase()||'ORCHARD')}</span><span>{current?current.id.slice(0,8):'GENESIS ALPHA'}</span></div>
        <div className="arena-canvas">{scene&&frame?<ArenaCanvas scene={scene} frame={frame} next={next} alpha={alpha}/>:preview?<ArenaCanvas preview={preview} color={selectedFly?.color||'mint'} design/>:<div className="canvas-loading"><Loader2 className="spin"/></div>}</div>
        {!scene&&<div className="stage-message">{current?.status==='running'||current?.status==='queued'?<><span className="running-orb"><Dna size={27}/></span><h3>{current.status==='queued'?'正在等待运行节点':'神经网络正在驱动身体'}</h3><p>真实全图仿真需要一些时间，完成后将自动载入回放。</p><div className="run-track"><span style={{width:current.progress*100+'%'}}/></div><strong>{Math.round(current.progress*100)}%</strong></>:current?.status==='failed'?<><h3>这次实验未完成</h3><p>{current.error}</p></>:<><h3>一个世界，两种本能。</h3><p>选择你的果蝇与对手，开始第一场比赛。</p></>}</div>}
        {scene&&frame&&<div className="score-overlay">{scene.flies.map((f,i)=><div key={i}><i style={{background:colors[f.color]}}/><span>{f.name.split(' / ')[0]}</span><strong>{frame.scores?.[i]?.toFixed(2)||'0.00'}</strong></div>)}</div>}
        <div className="playback"><button className="icon-button" aria-label={play?'暂停回放':'播放回放'} disabled={!frames.length} onClick={()=>{if(playtime>=frames[frames.length-1].time)setPlaytime(0);setPlay(!play)}}>{play?<Pause size={17}/>:<Play size={17}/>}</button><span>{playtime.toFixed(2)}s</span><input aria-label="回放进度" type="range" min="0" max={frames[frames.length-1]?.time||1} step=".01" value={playtime} disabled={!frames.length} onChange={e=>{setPlay(false);setPlaytime(+e.target.value)}}/><span>{frames[frames.length-1]?.time.toFixed(2)||'0.00'}s</span><button className="speed" onClick={()=>setPlaybackSpeed(s=>s===1?.5:s===.5?2:1)}>{playbackSpeed}×</button></div>
      </div>
      {frames.length>0&&<div className="trace-panel panel"><div className="panel-heading"><span><AudioLines size={16}/> 回路活动</span><small>实际神经发放率 · Hz</small></div><div className="trace-circuits">{season?.connectome.circuits.slice(0,6).map(c=><div key={c.id}><span style={{color:c.color}}>{c.label}</span><strong>{frame?.traces?.[0]?.[c.id]?.toFixed(1)||'0.0'}</strong><svg viewBox="0 0 120 30"><polyline fill="none" stroke={c.color} strokeWidth="1.6" points={frames.map((f,i)=>`${i/(frames.length-1)*120},${28-Math.min(26,(f.traces?.[0]?.[c.id]||0)/300*26)}`).join(' ')}/></svg></div>)}</div></div>}
      <div className="recent-matches panel"><div className="panel-heading"><span>最近的比赛</span><span className="tiny-label">MATCH LOG</span></div>{matches.slice(0,6).map(m=><button key={m.id} onClick={()=>setFocused(m.id)} className={'match-row '+(focused===m.id?'focused':'')}><span className={'status-dot '+m.status}/><div><strong>{m.request.fly_ids.map(id=>flies.find(f=>f.id===id)?.name.split(' / ')[0]||'Fly').join(' vs ')}</strong><small>{maps.find(x=>x.id===m.request.map_id)?.name} · {modes[m.request.mode]} · seed {m.request.seed}</small></div><span className={'status-label '+m.status}>{m.status==='verified'?(m.result?.outcome==='draw'?'平局 · 可回放':'已验证 · 可回放'):m.status==='running'?Math.round(m.progress*100)+'%':m.status==='queued'?'排队中':'未完成'}</span><ArrowUpRight size={15}/></button>)}{!matches.length&&<p className="empty">尚无比赛。第一段进化史，等你开启。</p>}</div></div>
      <aside className="match-setup panel"><div className="panel-heading"><span><Swords size={17}/> 新建比赛</span><small>01 / SETUP</small></div><label className="field-label">你的果蝇</label><select aria-label="参赛果蝇" value={selected} onChange={e=>setSelected(e.target.value)}>{flies.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select><label className="field-label">竞技环境</label><div className="map-options">{maps.map(m=><button key={m.id} className={m.id===mapId?'selected':''} onClick={()=>{setMapId(m.id);if(mode==='sumo'&&m.id!=='ring')setMode('contest')}}><span style={{background:m.color}}/>{m.name}{m.id===mapId&&<Check size={13}/>}</button>)}</div><label className="field-label">比赛模式</label><select aria-label="比赛模式" value={mode} onChange={e=>setMode(e.target.value)}>{(chosenMap?.modes||['forage','contest']).map(m=><option key={m} value={m}>{modes[m]}</option>)}</select>{mode!=='forage'&&<><label className="field-label">对手</label><select aria-label="对手" value={opponent} onChange={e=>setOpponent(e.target.value)}>{flies.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></>}<div className="two-fields"><label>模拟时长<select aria-label="模拟时长" value={duration} onChange={e=>setDuration(+e.target.value)}>{[2,5,10,20,30].map(v=><option key={v} value={v}>{v} 秒</option>)}</select></label><label>随机种子<input aria-label="随机种子" type="number" value={seed} min={0} max={2147483647} onChange={e=>setSeed(+e.target.value)}/></label></div><div className="match-note"><ShieldCheck size={19}/><p>完整 MaleCNS 网络<br/><span>固定身体与读出 · 同世界物理 · 独立裁判</span></p></div><button className="primary wide" disabled={!!busy||!selected} onClick={startMatch}>{busy==='match'?<Loader2 size={16} className="spin"/>:<Play size={15}/>}开始比赛 <ArrowRight size={16}/></button><button className="secondary wide" style={{marginTop:10}} disabled={!!busy||mode==='forage'||!selected||selected===opponent} onClick={startSeries}><Trophy size={15}/>创建双循环系列赛</button><p className="setup-footnote">系列赛交换双方位置，各赛一场。<br/>异步仿真，完成后提供真实轨迹回放。<br/>无需保持当前页面打开。</p></aside></div>}

      {tab==='lab'&&<div className="lab-layout"><section className="panel ranking-panel"><div className="panel-heading"><span><Trophy size={17}/> 创生季排行榜</span><small>VERIFIED MATCHES ONLY</small></div><table><thead><tr><th>#</th><th>果蝇 / 设计师</th><th>比赛</th><th>胜 / 平 / 负</th><th>积分</th></tr></thead><tbody>{rankings.map((r,i)=><tr key={r.fly.id}><td>{String(i+1).padStart(2,'0')}</td><td><div className="rank-fly"><Bug style={{color:colors[r.fly.color]}} size={22}/><span><strong>{r.fly.name}</strong><small>{r.fly.designer}</small></span></div></td><td>{r.matches}</td><td>{r.wins} / {r.draws} / {r.losses}</td><td><b>{r.points}</b></td></tr>)}</tbody></table><p className="table-note">工作区探索榜：胜 3 分，平 1 分。不同地图与模式的比赛可在记录中逐一核查；自对战不计分。</p></section><section className="panel lab-history"><div className="panel-heading"><span><Beaker size={17}/> 实验与回放</span><button className="text-link" onClick={()=>setTab('arena')}>新建实验 <Plus size={14}/></button></div>{matches.map(m=><button key={m.id} className="match-row" onClick={()=>{setFocused(m.id);setTab('arena')}}><span className={'status-dot '+m.status}/><div><strong>{modes[m.request.mode]} · {maps.find(x=>x.id===m.request.map_id)?.name}</strong><small>{m.id.slice(0,12)} · {m.request.duration_seconds}s · attempt {m.attempt}{m.tournament?' · 双循环系列赛':''}</small></div><span className="status-label">{m.status==='verified'?'查看回放':m.status==='running'?'运行中':m.status==='queued'?'排队中':'未完成'}</span><ArrowUpRight size={15}/></button>)}{!matches.length&&<div className="empty-large"><FlaskConical size={34}/><h3>从一个问题开始。</h3><p>加强嗅觉连接，真的更擅长觅食吗？<br/>创建实验，让行为给你答案。</p><button className="primary" onClick={()=>setTab('arena')}>运行第一次实验 <ArrowRight size={15}/></button></div>}</section></div>}

      {tab==='code'&&<div className="code-layout"><section className="panel code-main"><div className="panel-heading"><span><Code2 size={17}/> FlySpec 编辑器</span><div><button className="text-link" onClick={()=>setJsonEditor(JSON.stringify(spec,null,2))}><Copy size={14}/>载入当前设计</button><button className="text-link" onClick={()=>download('flyspec.json',spec)}><ArrowDownToLine size={14}/>导出</button></div></div><textarea aria-label="FlySpec JSON 编辑器" spellCheck={false} value={jsonEditor||JSON.stringify(spec,null,2)} onChange={e=>setJsonEditor(e.target.value)}/><div className="code-actions"><input type="file" accept=".json,application/json" hidden ref={fileInput} onChange={async e=>{const f=e.target.files?.[0];if(f)try{loadSpec(JSON.parse(await f.text()))}catch(err){setError(String(err))}}}/><button className="secondary" onClick={()=>fileInput.current?.click()}>导入 JSON</button><button className="primary" onClick={()=>{try{loadSpec(JSON.parse(jsonEditor||JSON.stringify(spec)))}catch(e){setError(String(e))}}}>在工坊中打开 <ArrowRight size={15}/></button></div></section><aside className="api-guide"><div className="api-guide-card"><Terminal size={25}/><span className="eyebrow">AGENT-NATIVE BY DESIGN</span><h2>同一格式。<br/>无限设计师。</h2><p>AI 与网页玩家使用相同的图谱、预算和验证流程。设计完成后，上传 FlySpec 并请求一次评测。</p><ol><li><span>01</span><div>读取当前规则<code>GET /api/v1/season</code></div></li><li><span>02</span><div>验证并保存设计<code>POST /api/v1/flies</code></div></li><li><span>03</span><div>提交比赛、轮询结果<code>POST /api/v1/matches</code></div></li></ol><a className="primary wide" href="/docs" target="_blank" rel="noreferrer">交互式 API 文档 <ExternalLink size={15}/></a><button className="secondary wide" onClick={()=>identity?setShowToken(true):setLogin(true)}>获取我的 API 身份 <ArrowUpRight size={15}/></button></div><p className="small-print">支持任意 AI agent。所有提交是声明式数据，比赛运行期间不会执行玩家上传的代码。</p></aside></div>}

      <p className="small-print" style={{marginTop:24}}>研究预览：完整保留图采用简化 LIF 动力学；当前输入为双侧气味，运动读出与步态控制器固定。视觉与学习尚未接入。权重变化的行为效果需通过比赛验证。</p><footer><span><Bug size={14}/> FLY ARENA <i>by The Omega Institute</i></span><span>真实图谱 · 可变神经网络 · 开放竞技</span><a href="https://male-cns.janelia.org/" target="_blank" rel="noreferrer">MaleCNS 数据来源 <ArrowUpRight size={12}/></a></footer>
    </main>
    {toast&&<div className="toast" role="status"><Check size={17}/>{toast}</div>}
    {login&&<div className="modal-backdrop"><section className="modal"><button className="modal-close icon-button" onClick={()=>setLogin(false)} aria-label="关闭"><X size={19}/></button><span className="modal-icon"><Leaf size={26}/></span><div className="eyebrow">WELCOME TO THE PLAYGROUND</div><h2>为你的设计署名。</h2><p>创建一个设计师身份，保存果蝇、运行比赛，并让你的 AI 使用同一身份参与。</p>{error&&<p role="alert" className="error-banner">{error}</p>}<label className="field-label">设计师名称</label><input autoFocus value={identityName} onChange={e=>setIdentityName(e.target.value)} placeholder="例如：Lexa / My Research Agent" maxLength={48}/>{season?.invite_required&&<><label className="field-label">内测邀请码</label><input value={invite} onChange={e=>setInvite(e.target.value)} placeholder="输入邀请码"/></>}<button className="primary wide" disabled={!!busy} onClick={register}>{busy==='identity'?<Loader2 className="spin" size={16}/>:<Plus size={16}/>}创建身份</button><small>当前工作区中，已发布果蝇与比赛回放公开可见。</small><details><summary>已有 API token？</summary><input aria-label="已有 API token" type="password" placeholder="粘贴你自己的 token" onKeyDown={async e=>{if(e.key==='Enter'){const token=e.currentTarget.value;try{const user=await api<Omit<Identity,'token'>>('/me',{headers:{Authorization:`Bearer ${token}`}});const id={...user,token};setIdentity(id);localStorage.setItem('flyarena.identity',JSON.stringify(id));setLogin(false)}catch(err){setError(String(err))}}}}/><small>按 Enter 连接已有身份</small></details></section></div>}
    {showToken&&identity&&<div className="modal-backdrop"><section className="modal"><button className="modal-close icon-button" onClick={()=>setShowToken(false)} aria-label="关闭"><X size={19}/></button><Terminal size={28}/><h2>{identity.name}</h2><p>你的 agent 可以用这个 Bearer token 调用 API。请保存在自己的凭据管理器中。</p><input aria-label="API token" type="password" readOnly value={identity.token}/><button className="primary wide" onClick={()=>navigator.clipboard.writeText(identity.token).then(()=>setToast('API token 已复制。'))}><Copy size={15}/>复制 API token</button><button className="text-link" onClick={()=>{setIdentity(null);localStorage.removeItem('flyarena.identity');setShowToken(false)}}>退出当前浏览器身份</button></section></div>}
    {inspectOpen&&<div className="modal-backdrop"><section className="modal neuron-modal"><button className="modal-close icon-button" onClick={()=>setInspectOpen(false)} aria-label="关闭"><X size={19}/></button><div className="eyebrow">REAL NEURONS · REAL CONNECTIONS</div><h2>走进真实回路。</h2><select aria-label="查看神经回路" value={inspectCircuit} onChange={e=>{setInspectCircuit(e.target.value);api<typeof inspect>('/connectome/neurons?circuit='+e.target.value).then(setInspect).catch(x=>setError(x.message))}}>{season?.connectome.circuits.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select><p>这里展示所选回路的前 80 个真实神经元；仿真运行完整的保留图。</p><div className="neuron-list">{inspect?.neurons.map(n=><div key={n.id}><span className="neuron-dot"/><strong>{n.type||'Unannotated'}</strong><code>{n.id}</code><small>{n.nt||'unknown'}</small></div>)}</div><small>{inspect?.edges.length||0} 条样本内连接 · ID 来自 MaleCNS v1.0</small></section></div>}
  </div>
}
