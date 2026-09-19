import {useMemo} from 'react'
import type {Frame,NeuralGraph} from '../../types'
import {useI18n} from '../../shared/i18n'

export function pairedNeuralChanges(before:Frame,after:Frame,slot:number){
 const recorded=(frame:Frame)=>{
  const brain=frame.brain?.[slot]
  return new Map((brain?.sampled_nodes??brain?.top_nodes??[]).filter(n=>Number.isFinite(n.activity)).map(n=>[n.id,n.activity]))
 }
 const a=recorded(before),b=recorded(after)
 const paired=[...a].flatMap(([id,value])=>b.has(id)?[{id,before:value,after:b.get(id)!,delta:b.get(id)!-value}]:[])
 return {paired:paired.length,unpaired:new Set([...a.keys(),...b.keys()]).size-paired.length,
  changes:paired.filter(n=>n.delta!==0).sort((x,y)=>Math.abs(y.delta)-Math.abs(x.delta)||x.id.localeCompare(y.id))}
}

export function EventNeuralResponse({before,after,slot,time,graph,onSeek,onInspect}:{before:Frame;after:Frame;slot:number;time:number;graph:NeuralGraph|null;onSeek:(time:number)=>void;onInspect:(id:string)=>void}){
 const {locale}=useI18n(),zh=locale==='zh-CN'
 const response=useMemo(()=>pairedNeuralChanges(before,after,slot),[before,after,slot])
 const nodes=new Map(graph?.neurons.map(n=>[n.id,n])||[])
 return <section className="event-neural-response" aria-label={zh?'事件前后神经元响应':'Neuron response around this event'}>
  <h3>{zh?'这次情境变化，哪些记录节点响应了？':'Which recorded neurons changed around this event?'}</h3>
  <div className="event-neural-samples">
   <button aria-pressed={time===before.time} onClick={()=>onSeek(before.time)}>{zh?'查看事件前/当时':'View before / at event'} · {before.time.toFixed(2)} s</button>
   <button aria-pressed={time===after.time} onClick={()=>onSeek(after.time)}>{zh?'查看响应采样':'View response sample'} · {after.time.toFixed(2)} s</button>
  </div>
  {before.time===after.time?<p>{zh?'记录已到边界，没有两个不同时间的采样可比较。':'The recording boundary leaves no two distinct samples to compare.'}</p>:<>
   <p>{zh?`两端都有记录：${response.paired} 个；仅一端记录：${response.unpaired} 个。下方按活动变化绝对值列出最多 6 个节点。`:`${response.paired} neurons recorded at both samples; ${response.unpaired} at only one. Up to 6 nodes are listed by absolute activity change.`}</p>
   {response.changes.length?<div className="event-neural-table" role="table" aria-label={zh?'实际神经元活动变化':'Recorded neuron activity changes'}>
    <div role="row" className="event-neural-table-heading"><span role="columnheader">{zh?'神经元 / 类型':'Neuron / type'}</span><span role="columnheader">{zh?'前 → 后':'Before → after'} · Hz</span><span role="columnheader">Δ Hz</span></div>
    {response.changes.slice(0,6).map(n=><div role="row" key={n.id} data-response-neuron={n.id}>
     <span role="cell"><button disabled={!nodes.has(n.id)} onClick={()=>{onSeek(after.time);onInspect(n.id)}} aria-label={`${zh?'检查响应神经元':'Inspect responding neuron'} ${n.id}`}>{n.id} →</button><small>{nodes.get(n.id)?.type||nodes.get(n.id)?.class||(zh?'结构未载入':'Structure unavailable')}</small></span>
     <span role="cell">{n.before.toFixed(2)} → {n.after.toFixed(2)}</span><b role="cell" data-direction={n.delta>0?'increase':'decrease'}>{n.delta>0?'+':''}{n.delta.toFixed(2)}</b>
    </div>)}
   </div>:<p>{response.paired?zh?'这些配对节点在两次采样中的数值没有变化。':'The paired nodes have unchanged values at these samples.':zh?'缺少同一神经元的前后配对记录；不把缺失当作零活动。':'No neuron has paired recordings here; missing values are not zero activity.'}</p>}
  </>}
  <small>{zh?'切换采样会同步定位身体和脑图；点击节点查看其连接、设计权重和活动曲线。这里只比较本次记录的节点，不是全脑排名，时间先后也不证明因果。':'Switching samples seeks body and brain together. Select a node to inspect its connections, design weights and activity trace. This compares recorded nodes, not the entire brain, and timing alone does not establish causality.'}</small>
 </section>
}
