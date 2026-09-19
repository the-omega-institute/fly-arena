import {BrainActivityOverview} from '../arena/BrainActivityOverview'
import '../arena/brainActivity.css'
import {useEffect,useState} from 'react'
import {useI18n} from '../../shared/i18n'
import type {Circuit,Spec} from '../../types'
import './neuralPreview.css'

type Sample={time_ms:number;stimulus:{left:number;right:number};circuits:Record<string,number>;reference_circuits:Record<string,number>;total_spikes:number|null;reference_total_spikes:number|null}
export type NeuralPreview={schema:string;artifact_id:string;model_profile:string;connectome_sha256:string;steps:number;scope:string;spec?:Spec;reference?:{artifact_id:string;spec:Spec};protocol?:{duration_ms:number;sample_interval_ms:number;onset_ms:number;offset_ms:number};stimuli:{stimulus:{left:number;right:number};circuits:Record<string,number>;total_spikes:number|null;samples?:Sample[]}[];example?:{name:string;related_match_id:string;execution:string}}
export type PreviewRecord={data:NeuralPreview;specKey:string|null}
const finite=(value:number|undefined):value is number=>typeof value==='number'&&Number.isFinite(value)
const show=(value:number|undefined)=>finite(value)?value.toFixed(2):'—'

export function NeuralPreviewPanel({record,stale,circuits,onImport,onReplay}:{record:PreviewRecord;stale:boolean;circuits:Circuit[];onImport:(spec:Spec)=>void;onReplay:(id:string)=>void}){
 const {locale,t}=useI18n(),zh=locale==='zh-CN',p=record.data
 const [trial,setTrial]=useState(0),[sampleIndex,setSampleIndex]=useState(8),[circuit,setCircuit]=useState('projection')
 useEffect(()=>{setTrial(0);setSampleIndex(8)},[record])
 const row=p.stimuli[trial]||p.stimuli[0],samples=row?.samples||[],sample=samples[Math.min(sampleIndex,samples.length-1)]
 const paired=!!(sample&&p.protocol&&p.reference),example=record.specKey===null
 const keys=[...new Set([...Object.keys(row?.circuits||{}),...Object.keys(sample?.circuits||{}),...Object.keys(sample?.reference_circuits||{})])],label=(id:string)=>t(circuits.find(c=>c.id===id)?.label||id)
 const names=zh?['左侧气味','右侧气味','双侧气味','仅背景输入']:['Left odor','Right odor','Bilateral odor','Background only']
 const duration=p.protocol?.duration_ms||1
 const brainScale=Math.max(1,...p.stimuli.flatMap(row=>(row.samples||[]).flatMap(s=>[...Object.values(s.circuits),...Object.values(s.reference_circuits)])).filter(finite))
 const scale=Math.max(1,...samples.flatMap(s=>[s.circuits[circuit],s.reference_circuits[circuit]]).filter(finite))
 const x=(time:number)=>48+time/duration*630,y=(value:number)=>158-value/scale*126
 function line(reference:boolean){let pen=false;return samples.map(s=>{const value=(reference?s.reference_circuits:s.circuits)[circuit];if(!finite(value)){pen=false;return ''}const point=`${pen?'L':'M'}${x(s.time_ms)},${y(value)}`;pen=true;return point}).join(' ')}
 const changes=p.spec?.weight_mutations||[]
 return <section className="panel stimulus-preview" aria-label={zh?'设计与 WT 神经响应':'Design and WT neural response'}>
  <div className="panel-heading"><span>{zh?'刺激实验 · 这份大脑如何响应':'Stimulus lab · how this brain responds'}</span><small>{example?(zh?'已运行的 Nectar 样本':'Recorded Nectar example'):(zh?'已提交设计的记录':'Submitted design record')}</small></div>
  <div className="stimulus-preview__body">
   <p>{zh?'对设计与同模型 WT 分别施加相同气味脉冲，观察神经响应的出现与消退。每次刺激都从静息状态重新开始。':'The design and same-model WT receive identical odor pulses. Watch responses emerge and decay; each trial starts again from rest.'}</p>
   {example&&<p className="stimulus-preview__notice">{zh?'这是固定 Nectar 设计的真实计算样本，不是当前编辑草稿的结果。':'This is a computed example of the fixed Nectar design, not the current editor draft.'}</p>}
   {stale&&!example&&<p role="status" className="stimulus-preview__notice">{zh?'草稿已修改。下方仍是上一次提交的结果；再次运行预览以观察新设计。':'The draft has changed. These are the previous submission’s results; run preview again for the new design.'}</p>}
   {!paired&&<p role="status" className="stimulus-preview__notice">{zh?'当前服务返回旧版单时刻预览，没有 WT 对照或响应时间线。可查看已运行的刺激样本；新预览接口尚待部署。':'This server returned a legacy single-time preview without WT or a response timeline. Open the recorded stimulus example; the new preview API awaits deployment.'}</p>}
   {p.spec&&<div className="stimulus-preview__design"><strong>{p.spec.name}</strong><span>{changes.length?changes.map(m=>`${label(m.selector)} ×${m.scale.toFixed(2)}`).join(' · '):(zh?'连接权重无修改':'No weight mutations')}{p.spec.edge_deltas?.length?` · ${p.spec.edge_deltas.length} ${zh?'逐连接修改':'edge edits'}`:''}{p.spec.interventions?.length?` · ${p.spec.interventions.length} ${zh?'选择器修改':'selector edits'}`:''}</span><small>τ ×{p.spec.neuron_parameters.tau_scale} · {zh?'阈值偏移':'threshold shift'} {p.spec.neuron_parameters.threshold_shift_mv} mV</small></div>}
   <div className="stimulus-preview__controls"><label>{zh?'选择刺激':'Choose stimulus'} <select aria-label={zh?'选择刺激':'Choose stimulus'} value={trial} onChange={e=>setTrial(+e.target.value)}>{p.stimuli.map((r,i)=><option key={i} value={i}>{names[i]||`${r.stimulus.left}/${r.stimulus.right}`}</option>)}</select></label><span>{p.model_profile}</span></div>
   {paired&&<>
    <div className="stimulus-preview__legend"><span className="candidate">{zh?'设计':'Design'}</span><span className="reference">WT</span><span>{zh?'每侧背景 8 mV；脉冲侧增加 40 mV，20–80 ms。':'8 mV background per side; pulse adds 40 mV at 20–80 ms.'}</span></div>
    <svg viewBox="0 0 710 204" role="img" aria-label={`${label(circuit)} ${zh?'设计与 WT 响应曲线':'design and WT response curves'}`} className="stimulus-preview__chart">
     <rect x={x(p.protocol!.onset_ms)} y="22" width={x(p.protocol!.offset_ms)-x(p.protocol!.onset_ms)} height="136" fill="var(--accent)" opacity={trial===3?0:.09}/>
     {[0,scale/2,scale].map(v=><g key={v}><path d={`M48 ${y(v)}H678`} stroke="currentColor" opacity=".12"/><text x="40" y={y(v)+4} textAnchor="end">{v.toFixed(1)}</text></g>)}
     <text x="48" y="13">{label(circuit)} · Hz</text>
     <path d={line(true)} fill="none" stroke="#bd8252" strokeWidth="2" strokeDasharray="5 4"/>
     <path d={line(false)} fill="none" stroke="#398572" strokeWidth="2.5"/>
     <path d={`M${x(sample.time_ms)} 22V158`} stroke="currentColor" strokeDasharray="2 4"/>
     {[0,20,80,duration].map(ms=><text key={ms} x={x(ms)} y="181" textAnchor="middle">{ms} ms</text>)}
     <text x="678" y="201" textAnchor="end">{zh?'阴影为气味脉冲区间；缺失数据留空。':'Shading: odor pulse; missing samples stay blank.'}</text>
    </svg>
    <label className="stimulus-preview__clock">{zh?'观察时间':'Observation time'} <strong>{sample.time_ms} ms</strong><input type="range" aria-label={zh?'神经预览时间':'Neural preview time'} min={0} max={samples.length-1} step={1} value={Math.min(sampleIndex,samples.length-1)} onInput={e=>setSampleIndex(+e.currentTarget.value)} onChange={e=>setSampleIndex(+e.target.value)}/></label>
   </>}
   {paired&&circuits.length>0&&<div className="stimulus-preview__brains"><div><h3>{zh?'设计的大脑':'Design brain'}</h3><BrainActivityOverview circuits={circuits} activity={sample.circuits} scale={brainScale} mutations={changes} time={sample.time_ms/1000} onOpen={setCircuit} mode="preview"/></div><div><h3>WT</h3><BrainActivityOverview circuits={circuits} activity={sample.reference_circuits} scale={brainScale} time={sample.time_ms/1000} onOpen={setCircuit} mode="preview"/></div></div>}
   <div className="stimulus-preview__regions">{keys.map(id=>{const own=sample?sample.circuits[id]:row.circuits[id],wt=sample?.reference_circuits[id],delta=finite(own)&&finite(wt)?own-wt:undefined
    return <button key={id} className={circuit===id?'active':''} onClick={()=>setCircuit(id)} aria-pressed={circuit===id} aria-label={label(id)}><strong>{label(id)}</strong><span>{zh?'设计':'Design'} <b>{show(own)} Hz</b></span><span>WT <b>{show(wt)}{finite(wt)?' Hz':''}</b></span><small>Δ {finite(delta)?`${delta>0?'+':''}${delta.toFixed(2)} Hz`:'—'}</small></button>})}</div>
   <p className="stimulus-preview__scope">{zh?'这些是模型神经群的活动记录。零气味仍有背景电流；WT 指未修改参数的同模型基线。此实验没有身体、动作读出或比赛分数，响应差异不能直接当作行为优势。':'These are recorded model population activities. Zero odor retains tonic current; WT is the unmodified same-model baseline. There is no body, motor readout or match score. A neural difference is not evidence of better behavior.'}</p>
   {example&&p.spec&&<div className="stimulus-preview__actions"><button className="secondary" onClick={()=>onImport(p.spec!)}>{zh?'把样本设计载入编辑器':'Load example design into editor'}</button>{p.example?.related_match_id&&<button className="secondary" onClick={()=>onReplay(p.example!.related_match_id)}>{zh?'观看这份设计的真实对战':'Watch this design in a real contest'}</button>}</div>}
   <details><summary>{zh?'查看本次设计与实验条件':'Inspect design and experiment conditions'}</summary><pre>{JSON.stringify({artifact_id:p.artifact_id,connectome:p.connectome_sha256,reference:p.reference,protocol:p.protocol,spec:p.spec,scope:p.scope},null,2)}</pre></details>
  </div>
 </section>
}
