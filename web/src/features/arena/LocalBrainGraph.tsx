import {useEffect,useId,useState} from 'react'
import type {ReactNode} from 'react'
import type {NeuralGraph} from '../../types'
import {useI18n} from '../../shared/i18n'

/** Show actual incoming/outgoing edges around a selected canonical neuron.
 * The placement is schematic. Unsampled neighbors never acquire activity. */
export function LocalBrainGraph({graph,activity,scale,selectedClass,renderActivity,focusId,onFocus}:{graph:NeuralGraph;activity:Map<string,number>;scale:number;selectedClass:string|null;renderActivity?:(neuronId:string)=>ReactNode;focusId?:string|null;onFocus?:(id:string)=>void}){
  const {locale}=useI18n(),zh=locale==='zh-CN',prefix=useId().replace(/:/g,'')
  const [focus,setFocus]=useState<string|null>(null),[selectedEdge,setSelectedEdge]=useState<number|null>(null)
  useEffect(()=>{setFocus(null);setSelectedEdge(null)},[selectedClass])
  useEffect(()=>{
    if(focus!==null&&!graph.neurons.some(n=>n.id===focus))setFocus(null)
    if(selectedEdge!==null&&!graph.edges.some(e=>e.edge===selectedEdge))setSelectedEdge(null)
  },[graph,focus,selectedEdge])
  const candidates=graph.neurons.filter(n=>!selectedClass||(n.class||n.type||'unannotated')===selectedClass)
  const node=graph.neurons.find(n=>n.id===(focusId===undefined?focus:focusId))||candidates.find(n=>activity.has(n.id))||candidates[0]
  if(!node)return <p className="empty">{zh?'此类别没有展示神经元。':'No displayed neurons in this class.'}</p>
  const edges=graph.edges.filter(e=>e.pre===node.id||e.post===node.id)
  const upstream=new Set(edges.filter(e=>e.post===node.id&&e.pre!==node.id).map(e=>e.pre))
  const downstream=new Set(edges.filter(e=>e.pre===node.id&&e.post!==node.id&&!upstream.has(e.post)).map(e=>e.post))
  const points=new Map<string,{x:number;y:number}>([[node.id,{x:320,y:185}]])
  for(const [set,x] of [[upstream,105],[downstream,535]] as const)[...set].forEach((id,i)=>points.set(id,{x,y:65+(i+1)*280/(set.size+1)}))
  const shownNodes=graph.neurons.filter(n=>points.has(n.id)),value=activity.get(node.id),recorded=value!==undefined&&Number.isFinite(value)
  const edge=edges.find(e=>e.edge===selectedEdge)||edges.find(e=>e.multiplier!==undefined&&Math.abs(e.multiplier-1)>1e-8)||edges[0]
  const show=(n:number|undefined)=>n===undefined||!Number.isFinite(n)?'—':n.toFixed(4)
  const sign=(weight:number|undefined)=>weight===undefined?'unknown':weight>0?'positive':weight<0?'negative':'silent'
  const colors={positive:'#418c78',negative:'#bb7388',silent:'#86918a',unknown:'#86918a'}
  const selectNode=(id:string)=>{setFocus(id);setSelectedEdge(null);onFocus?.(id)}
  return <div className="local-brain-neighborhood">
    <div className="local-brain-toolbar"><label>{zh?'中心神经元':'Focus neuron'} <select aria-label={zh?'中心神经元':'Focus neuron'} value={node.id} onChange={e=>selectNode(e.target.value)}>{graph.neurons.map(n=><option key={n.id} value={n.id}>{n.id} · {n.type||n.class||'—'}{activity.has(n.id)?' ●':''}</option>)}</select></label><span>{zh?'实线节点有活动记录；空心邻居未记录。':'Filled nodes have activity records; hollow neighbors were not sampled.'}</span></div>
    <svg className="local-brain-canvas" viewBox="0 0 640 390" role="group" aria-label={zh?'真实神经连接邻域':'Actual neuron connection neighborhood'}>
      <defs>{Object.entries(colors).map(([key,color])=><marker key={key} id={`${prefix}-${key}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill={color}/></marker>)}</defs>
      <text x="105" y="26" textAnchor="middle" className="local-brain-column">{zh?'上游邻居':'Incoming neighbors'}</text><text x="320" y="26" textAnchor="middle" className="local-brain-column">{zh?'选中的神经元':'Selected neuron'}</text><text x="535" y="26" textAnchor="middle" className="local-brain-column">{zh?'下游邻居':'Outgoing neighbors'}</text>
      {edges.map(e=>{
        const a=points.get(e.pre),b=points.get(e.post);if(!a||!b)return null
        const kind=sign(e.weight),edited=e.multiplier!==undefined&&Math.abs(e.multiplier-1)>1e-8
        const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1,r=e.post===node.id?20:12
        const d=e.pre===e.post?`M${a.x-10},${a.y-16}C${a.x-62},${a.y-80} ${a.x+62},${a.y-80} ${a.x+12},${a.y-18}`:`M${a.x+dx/length*12},${a.y+dy/length*12}Q${(a.x+b.x)/2-dy/length*12},${(a.y+b.y)/2+dx/length*12} ${b.x-dx/length*r},${b.y-dy/length*r}`
        return <g key={e.edge} role="button" tabIndex={0} aria-label={`${zh?'连接':'Edge'} ${e.edge}: ${e.pre} → ${e.post}`} onClick={()=>setSelectedEdge(e.edge)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setSelectedEdge(e.edge)}}} data-edge={e.edge} data-edited={edited}>
          <path d={d} stroke="transparent" strokeWidth="13" fill="none"/>
          <path d={d} stroke={colors[kind]} strokeWidth={edge?.edge===e.edge?3:1.4} strokeDasharray={kind==='silent'?'2 4':edited?'6 3':undefined} fill="none" markerEnd={`url(#${prefix}-${kind})`} opacity={edge?.edge===e.edge?1:.65}/>
          <title>{e.pre} → {e.post} · {e.count} {zh?'突触':'synapses'} · {show(e.baseline_weight)} → {show(e.weight)} · ×{show(e.multiplier)}</title>
        </g>
      })}
      {shownNodes.map(n=>{const p=points.get(n.id)!,v=activity.get(n.id),has=v!==undefined&&Number.isFinite(v),selected=n.id===node.id
        return <g key={n.id} role="button" tabIndex={0} aria-label={`${zh?'神经元':'Neuron'} ${n.id}: ${has?v.toFixed(2)+' Hz':zh?'未记录':'Not recorded'}`} onClick={()=>selectNode(n.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectNode(n.id)}}} data-neuron={n.id} data-recorded={has}>
          {has&&v>0&&<circle cx={p.x} cy={p.y} r={selected?33:23} fill="#f2ce77" opacity={Math.min(1,v/Math.max(1,scale))*.4}/>}
          <circle cx={p.x} cy={p.y} r={selected?17:10} fill={has?(v>0?`hsl(${145-Math.min(1,v/Math.max(1,scale))*115} 65% 55%)`:'#71897c'):'var(--surface)'} stroke={selected?'var(--text)':'#7e8e80'} strokeWidth={selected?2:1.2} strokeDasharray={has?undefined:'3 3'}/>
          <text x={p.x} y={p.y+(selected?34:25)} textAnchor="middle" className="local-brain-node-label">{n.id}</text>
          <title>{n.type||n.class||'—'} · {has?v.toFixed(2)+' Hz':zh?'未记录，不等于零活动':'Not recorded, not zero activity'}</title>
        </g>
      })}
    </svg>
    <div className="local-brain-node-details"><span>{zh?'神经元':'Neuron'} <b>{node.id}</b></span><span>{zh?'类别 / 类型':'Class / type'} <b>{node.class||'—'} / {node.type||'—'}</b></span><span>{zh?'递质注释':'Transmitter annotation'} <b>{node.nt||'—'}</b></span><span>{zh?'这一帧的活动':'Activity in this frame'} <b>{recorded?value.toFixed(2)+' Hz':zh?'未记录':'Not recorded'}</b></span></div>
    {renderActivity?.(node.id)}
    {edge?<div className="local-brain-edge-details"><label>{zh?'检查连接':'Inspect edge'} <select aria-label={zh?'检查连接':'Inspect edge'} value={edge.edge} onChange={e=>setSelectedEdge(Number(e.target.value))}>{edges.map(e=><option key={e.edge} value={e.edge}>{e.pre} → {e.post} · #{e.edge}</option>)}</select></label><div><span>{zh?'真实突触数量':'Anatomical synapses'}<b>{edge.count}</b></span><span>{zh?'模型基线权重':'Baseline model weight'}<b>{show(edge.baseline_weight)}</b></span><span>{zh?'设计权重倍率':'Design multiplier'}<b>×{show(edge.multiplier)}</b></span><span>{zh?'这只果蝇的权重':'This fly’s model weight'}<b>{show(edge.weight)}</b></span></div></div>:<p>{zh?'此展示样本中没有该神经元的连接。':'No connections for this neuron in the display sample.'}</p>}
    {edges.some(e=>e.weight===undefined)&&<p className="local-brain-note">{zh?'这份回放未提供逐连接权重；— 表示缺失，不是零权重。':'This replay did not provide per-edge weights; — means missing, not zero weight.'}</p>}
    <p className="local-brain-note">{zh?'箭头为真实连接方向；绿色为模型兴奋权重，粉色为模型抑制权重，灰色虚线为模型零权重；长虚线表示设计修改。权重来自本次参赛设计，单位为模型突触强度，不是实测生理强度。位置为示意，邻域只展示所选连接；未采样邻居不会补造活动。':'Arrows follow actual connections. Green: excitatory model weight; pink: inhibitory; gray dotted: zero model weight. Long dashes mark design edits. Weights belong to this contestant and use model synaptic strength, not measured physiology. Positions are schematic and the neighborhood is a display sample. Unsampled neighbors receive no invented activity.'}</p>
  </div>
}
