import {useId} from 'react'
import type {Circuit,Spec} from '../../types'
import {useI18n} from '../../shared/i18n'

// A functional schematic, not anatomical coordinates or inferred connections.
const locations:Record<string,[number,number]>={
  olfactory:[150,76],projection:[340,76],local:[120,161],memory:[365,161],
  readout:[145,247],visual:[370,247],descending:[180,329],motor:[350,329],
}

export function BrainActivityOverview({circuits,activity,scale,mutations=[],time,onOpen}:{
  circuits:Circuit[];activity:Record<string,number>;scale:number;
  mutations?:Spec['weight_mutations'];time?:number;onOpen:(id:string)=>void;
}) {
  const {t,locale}=useI18n()
  const prefix=useId().replace(/:/g,'')
  const zh=locale==='zh-CN'
  const ceiling=Number.isFinite(scale)&&scale>0?scale:1
  return <div className="brain-overview">
    <div className="brain-overview-heading"><span>{zh?'这一刻，大脑在做什么':'Inside this brain, now'}</span><b>{time===undefined?'—':time.toFixed(2)+' s'}</b></div>
    <svg viewBox="0 0 520 395" className="brain-overview-map" role="group" aria-label={zh?'记录的全脑功能群活动':'Recorded brain functional group activity'}>
      <defs>{circuits.map(c=><radialGradient key={c.id} id={`${prefix}-${c.id}`}><stop offset="0" stopColor={c.color} stopOpacity=".9"/><stop offset="1" stopColor={c.color} stopOpacity="0"/></radialGradient>)}</defs>
      <path className="brain-overview-outline" d="M260 43 C206 9 82 18 52 91 C17 175 66 283 150 297 C153 349 191 377 260 378 C329 377 367 349 370 297 C454 283 503 175 468 91 C438 18 314 9 260 43Z"/>
      <path className="brain-overview-midline" d="M260 45 C245 116 272 187 260 271 L260 367"/>
      {circuits.map((c,i)=>{
        const [x,y]=locations[c.id]||[120+(i%2)*250,65+Math.floor(i/2)*82]
        const raw=activity[c.id],recorded=Number.isFinite(raw)
        const strength=recorded?Math.max(0,Math.min(1,raw/ceiling)):0
        const changes=mutations.filter(m=>m.selector===c.id)
        const scaleFactor=changes.reduce((v,m)=>v*m.scale,1)
        const label=t(c.label)
        const value=recorded?raw.toFixed(2)+' Hz':zh?'未记录':'Not recorded'
        return <g key={c.id} data-circuit={c.id} data-recorded={recorded} className="brain-overview-region" role="button" tabIndex={0}
          aria-label={`${label}: ${value}${changes.length?` · ×${scaleFactor.toFixed(2)}`:''}`}
          onClick={()=>onOpen(c.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onOpen(c.id)}}}>
          <ellipse cx={x} cy={y} rx="105" ry="68" fill={`url(#${prefix}-${c.id})`} opacity={strength} data-activity-glow={strength}/>
          <rect x={x-81} y={y-26} width="162" height="59" rx="15" fill="#142c2b" stroke={changes.length?'#efc784':recorded?c.color:'#6a7c7b'} strokeWidth={changes.length?2:1} strokeDasharray={recorded?undefined:'4 4'} fillOpacity=".87"/>
          <circle cx={x-64} cy={y-7} r="3" fill={recorded?c.color:'none'} stroke={c.color}/>
          <text x={x-54} y={y-3} className="brain-overview-label">{label}</text>
          <text x={x-63} y={y+19} className="brain-overview-value">{value}</text>
          {changes.length>0&&<text x={x+69} y={y+19} textAnchor="end" className="brain-overview-edit">×{scaleFactor.toFixed(2)}</text>}
          <title>{`${label} · ${c.neuron_count?.toLocaleString()??'—'} ${zh?'神经元；点击展开类别':'neurons; open classes'}`}</title>
        </g>
      })}
    </svg>
    <div className="brain-overview-legend"><span><i/>{zh?'活动亮度':'Activity brightness'} 0–{ceiling.toFixed(2)} Hz</span><span className="brain-overview-edited">○ {zh?'金色边框：权重修改':'Gold outline: weight edit'}</span></div>
    <p>{zh?'点击功能群，展开神经元类别与局部连接。位置为示意；亮度来自记录的群体平均活动，整段回放与双方共用同一色标。未记录不等于零活动。':'Select a group to open neuron classes and local connections. Positions are schematic; brightness is recorded mean activity, with one scale across this replay and both flies. Missing data is not zero activity.'}</p>
  </div>
}
