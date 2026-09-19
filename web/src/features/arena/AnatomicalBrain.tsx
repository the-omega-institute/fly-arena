import {Component,useEffect,useMemo,useState} from 'react'
import type {ReactNode} from 'react'
import type {Frame,NeuralGraph} from '../../types'
import {useI18n} from '../../shared/i18n'
import {AnatomicalBrainCanvas} from './AnatomicalBrainCanvas'
import type {BrainAngle} from './AnatomicalBrainCanvas'
import {anatomySpace,loadAnatomy,spatialNodes} from './anatomy'
import type {Anatomy} from './anatomy'
import {LocalBrainGraph} from './LocalBrainGraph'
import {NeuronActivityTrace} from './NeuronActivityTrace'
import './anatomicalBrain.css'

class CanvasBoundary extends Component<{children:ReactNode;fallback:ReactNode},{failed:boolean}>{
  state={failed:false}
  static getDerivedStateFromError(){return {failed:true}}
  render(){return this.state.failed?this.props.fallback:this.props.children}
}

export function AnatomicalBrain({connectome,graph,activity,scale,frames,slot,time,onSeek}:{connectome?:string;graph:NeuralGraph;activity:Map<string,number>;scale:number;frames:Frame[];slot:number;time:number;onSeek:(time:number)=>void}){
  const {locale}=useI18n(),zh=locale==='zh-CN'
  const [data,setData]=useState<Anatomy|null>(null),[error,setError]=useState(false),[retry,setRetry]=useState(0)
  const [focus,setFocus]=useState<string|null>(null),[angle,setAngle]=useState<BrainAngle>('oblique'),[reset,setReset]=useState(0)
  useEffect(()=>{
    let active=true;const controller=new AbortController();setData(null);setError(false)
    if(!connectome){setError(true);return()=>controller.abort()}
    loadAnatomy(connectome,controller.signal).then(value=>{if(active)setData(value)}).catch(()=>{if(active)setError(true)})
    return()=>{active=false;controller.abort()}
  },[connectome,retry])
  const current=data?.connectome_sha256===connectome?data:null
  const space=useMemo(()=>current?anatomySpace(current):null,[current])
  const nodes=useMemo(()=>space?spatialNodes(graph,space,activity):[],[graph,space,activity])
  const chosen=graph.neurons.find(n=>n.id===focus)?.id||nodes.find(n=>n.position&&n.activity!==null)?.id||graph.neurons[0]?.id||null
  const selected=nodes.find(n=>n.id===chosen),position=graph.neurons.find(n=>n.id===chosen)?.position
  const noWebgl=<p className="empty">{zh?'此设备暂时无法显示三维视图。下方连接图和活动记录仍可查看。':'The 3D view is unavailable on this device. The connection graph and activity records below remain usable.'}</p>
  return <div className="anatomical-brain">
    <div className="anatomical-brain-heading"><div><strong>{zh?'在真实解剖空间中观察大脑':'Explore the brain in anatomical space'}</strong><p>{zh?'拖动旋转，滚轮缩放；点击前景神经元，查看其连接与活动。':'Drag to rotate, scroll to zoom. Select a foreground neuron to inspect its connections and activity.'}</p></div><b>{time.toFixed(2)} s</b></div>
    {current&&space?<>
      <div className="anatomical-brain-tools"><div role="group" aria-label={zh?'解剖视角':'Anatomical view angle'}>{(['oblique','xy','xz'] as const).map(value=><button key={value} aria-pressed={angle===value} onClick={()=>{setAngle(value);setReset(n=>n+1)}}>{value==='oblique'?(zh?'三维':'3D'):value.toUpperCase()}</button>)}</div><button onClick={()=>setReset(n=>n+1)}>{zh?'重置视角':'Reset anatomical view'}</button><span>{zh?'活动色标':'Activity scale'} 0–{Math.max(1,scale).toFixed(2)} Hz</span></div>
      <div className="anatomical-brain-stage"><CanvasBoundary key={connectome} fallback={noWebgl}><AnatomicalBrainCanvas space={space} nodes={nodes} graph={graph} focus={chosen} onFocus={setFocus} scale={scale} angle={angle} reset={reset}/></CanvasBoundary></div>
      <div className="anatomical-brain-counts"><span><b>{current.position_count.toLocaleString()}</b> {zh?'个真实胞体位置':'actual soma positions'}</span><span><b>{current.missing_position_count.toLocaleString()}</b> {zh?'个神经元缺少坐标':'neurons without coordinates'}</span><span><b>{nodes.filter(n=>n.position&&n.activity!==null).length}</b> {zh?'个邻域节点在本帧有位置及活动':'neighborhood nodes positioned and recorded now'}</span></div>
      <p className="anatomical-brain-position">{zh?'所选神经元的原始坐标':'Selected neuron source coordinates'} · {selected?.position&&position?position.map(v=>v.toFixed(0)).join(' / '):(zh?'未提供；仍可查看下方活动记录':'Unavailable; activity can still be inspected below')}</p>
      <p className="anatomical-brain-note">{zh?'灰色点云仅表示结构位置，不代表零活动。前景显示所选范围内有活动记录的节点，以及选中节点的直接邻居：空心节点未采样，实心节点颜色来自本帧记录；金色框为选中节点。连线表示胞体间的连接关系，不是轴突形状；金色连接标记设计修改，方向与权重见下方。缺坐标节点不编造位置。坐标使用原始图谱单位，并统一缩放显示。':'Gray points show anatomical context, not zero activity. The foreground shows recorded nodes in this scope and direct neighbors of the selected node: hollow nodes are unrecorded; filled-node colors use this frame’s recorded activity. Gold outline marks selection. Lines join connected somata, not axon paths; gold edges mark design edits, with directions and weights below. Missing positions are not invented. Source coordinates use a uniform display scale.'}</p>
    </>:error?<p className="empty">{zh?'未找到与这份回放连接组匹配的解剖坐标。仍可查看下方连接与活动。':'Matching anatomical coordinates are unavailable for this replay. Connections and activity remain available below.'} <button onClick={()=>setRetry(n=>n+1)}>{zh?'重试':'Retry anatomy'}</button></p>:<p className="empty" role="status">{zh?'正在载入真实胞体坐标…':'Loading actual soma coordinates…'}</p>}
    <LocalBrainGraph graph={graph} activity={activity} scale={scale} selectedClass={null} focusId={chosen} onFocus={setFocus} renderActivity={neuronId=><NeuronActivityTrace neuronId={neuronId} frames={frames} slot={slot} time={time} onSeek={onSeek}/>}/>
  </div>
}
