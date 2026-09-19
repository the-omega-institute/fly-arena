import {useMemo} from 'react'
import type {Frame} from '../../types'
import {useI18n} from '../../shared/i18n'

/** Inspect only the recorded values for this neuron and contestant. */
export function NeuronActivityTrace({neuronId,frames,slot,time,onSeek}:{neuronId:string;frames:Frame[];slot:number;time:number;onSeek:(time:number)=>void}){
  const {locale}=useI18n(),zh=locale==='zh-CN'
  const trace=useMemo(()=>{
    const samples=frames.map(frame=>{
      const brain=frame.brain?.[slot]
      const value=(brain?.sampled_nodes??brain?.top_nodes??[]).find(n=>n.id===neuronId)?.activity
      return {time:frame.time,value:value!==undefined&&Number.isFinite(value)?value:null}
    })
    const recorded=samples.filter((s):s is {time:number;value:number}=>s.value!==null)
    const peak=recorded.reduce<{time:number;value:number}|null>((best,s)=>best===null||s.value>best.value?s:best,null)
    const maximum=Math.max(1,peak?.value??0),start=samples[0]?.time??0,end=samples.at(-1)?.time??start
    const x=(t:number)=>end>start?(t-start)/(end-start)*600:300
    let connected=false
    const path=samples.map(s=>{
      if(s.value===null){connected=false;return ''}
      const part=`${connected?'L':'M'}${x(s.time).toFixed(2)},${(76-s.value/maximum*68).toFixed(2)}`
      connected=true;return part
    }).join(' ')
    return {samples,recorded,peak,maximum,start,end,x,path}
  },[frames,slot,neuronId])
  let index=0
  for(let i=0;i<trace.samples.length;i++){if(trace.samples[i].time>time)break;index=i}
  const current=trace.samples[index]
  const seekNearest=(target:number)=>{
    const nearest=trace.samples.reduce((best,s)=>Math.abs(s.time-target)<Math.abs(best.time-target)?s:best)
    onSeek(nearest.time)
  }
  return <section className="neuron-activity-trace" aria-label={zh?'所选神经元活动时间线':'Selected neuron activity timeline'} data-neuron-id={neuronId}>
    <div className="neuron-activity-heading"><strong>{zh?'神经元活动时间线':'Neuron activity over time'} · {neuronId}</strong><span>{trace.recorded.length}/{trace.samples.length} {zh?'帧有记录':'frames recorded'}</span></div>
    {trace.recorded.length===0?<p>{zh?'这场回放没有记录该神经元的活动。结构邻居存在不代表它没有放电；请选择有记录的节点。':'This replay did not record this neuron’s activity. A structural neighbor without samples is not a silent neuron; select a recorded node.'}</p>:<>
      <div className="neuron-activity-summary"><span>{zh?'当前记录':'Current sample'}: <b>{current?.value==null?'—':current.value.toFixed(2)+' Hz'}</b> · {current?.time.toFixed(2)} s</span><button className="text-link" onClick={()=>onSeek(trace.peak!.time)}>{zh?'定位记录峰值':'Go to recorded peak'} · {trace.peak!.value.toFixed(2)} Hz / {trace.peak!.time.toFixed(2)} s</button></div>
      <svg viewBox="0 0 600 88" preserveAspectRatio="none" role="img" aria-label={zh?'所选神经元记录曲线':'Selected neuron recorded activity'} onClick={event=>{const bounds=event.currentTarget.getBoundingClientRect();if(bounds.width>0)seekNearest(trace.start+Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width))*(trace.end-trace.start))}}>
        <line x1="0" x2="600" y1="76" y2="76" stroke="currentColor" opacity=".15"/>
        <path data-neuron-trace="true" d={trace.path} fill="none" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke"/>
        {trace.samples.map((s,i)=>s.value!==null&&trace.samples[i-1]?.value==null&&trace.samples[i+1]?.value==null?<circle key={s.time} cx={trace.x(s.time)} cy={76-s.value/trace.maximum*68} r="2" fill="var(--accent)"/>:null)}
        {time>=trace.start&&time<=trace.end&&<line data-neuron-cursor="true" x1={trace.x(time)} x2={trace.x(time)} y1="0" y2="88" stroke="currentColor" opacity=".6"/>}
      </svg>
      <div className="neuron-activity-seek"><span>{trace.start.toFixed(2)} s</span><input type="range" aria-label={zh?'按神经元采样定位回放':'Seek replay by neuron sample'} min="0" max={trace.samples.length-1} step="1" value={index} disabled={trace.samples.length<2} onChange={event=>onSeek(trace.samples[Number(event.target.value)].time)}/><span>{trace.end.toFixed(2)} s</span></div>
      <p>{zh?`纵轴 0–${trace.maximum.toFixed(2)} Hz，整场固定。空缺表示未记录；点击曲线或峰值同步定位身体和脑图。连线仅帮助阅读采样，活动变化本身不证明因果。`:`Fixed scale: 0–${trace.maximum.toFixed(2)} Hz for the whole replay. Gaps mean unrecorded. Click the curve or peak to seek the body and brain together. Lines connect samples for readability; activity changes alone do not establish causality.`}</p>
    </>}
  </section>
}
