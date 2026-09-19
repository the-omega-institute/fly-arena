import type {Frame} from '../../types'

export type SignalPoint={time:number;value:number|null}
export type ResponseSignal={id:string;color:string;points:SignalPoint[]}
export type ResponseRow={id:string;unit:string;signals:ResponseSignal[];maximum:number}
const finite=(value:unknown):number|null=>typeof value==='number'&&Number.isFinite(value)?value:null

/** Read actual samples. Inputs belong to the beginning of the recorded block;
 * neural rates, motor drives and body positions belong to its end. A missing
 * cadence is left unshifted and must be disclosed by the caller. */
export function responseSignals(frames:Frame[],slot:number,inputInterval:number|null):ResponseRow[]{
  const signal=(id:string,color:string,read:(f:Frame,i:number)=>unknown,input=false):ResponseSignal=>({id,color,
    points:frames.map((f,i)=>({time:f.time-(input&&i>0?(inputInterval??0):0),value:finite(read(f,i))}))})
  const channels=[['taste','#b58728'],['touch_left','#b46796'],['touch_right','#548cc2']] as const
  const rows=[
    {id:'input',unit:'0 / 1',signals:channels.map(([key,color])=>signal(key,color,f=>f.senses?.[slot]?.[key],true))},
    {id:'activity',unit:'Hz',signals:channels.map(([key,color])=>signal(key,color,f=>f.senses?.[slot]?.contact_activity?.[key]))},
    {id:'descending',unit:'Hz',signals:[signal('descending','#38897d',f=>f.traces?.[slot]?.descending)]},
    {id:'drive',unit:'drive',signals:[signal('left','#b46796',f=>f.drives?.[slot]?.[0]),signal('right','#548cc2',f=>f.drives?.[slot]?.[1])]},
    {id:'speed',unit:'mm/s',signals:[signal('speed','#38897d',(f,i)=>{
      if(i===0)return null
      const previous=frames[i-1],a=previous.positions?.[slot],b=f.positions?.[slot],dt=f.time-previous.time
      return a&&b&&[a[0],a[1],b[0],b[1]].every(Number.isFinite)&&dt>0?Math.hypot(b[0]-a[0],b[1]-a[1])/dt:null
    })]},
    {id:'intake',unit:'food',signals:[signal('intake','#b58728',f=>f.scores?.[slot])]},
  ]
  return rows.map(row=>({...row,maximum:row.signals.reduce((max,s)=>s.points.reduce((m,p)=>Math.max(m,p.value??0),max),row.id==='input'?1:0)||1}))
}

/** Exact samples only, with gaps kept open. Input channels are step-held. */
export function responsePath(points:SignalPoint[],start:number,end:number,maximum:number,step=false):string{
  if(end<=start||maximum<=0)return ''
  let connected=false
  return points.map(point=>{
    if(point.value===null||!Number.isFinite(point.value)||!Number.isFinite(point.time)){connected=false;return ''}
    const x=(point.time-start)/(end-start)*600,y=48-point.value/maximum*44
    const part=connected?(step?`H${x.toFixed(2)}V${y.toFixed(2)}`:`L${x.toFixed(2)},${y.toFixed(2)}`):`M${x.toFixed(2)},${y.toFixed(2)}`
    connected=true;return part
  }).join(' ')
}

export function responsePointAt(points:SignalPoint[],time:number):SignalPoint|undefined{
  // For input, duplicate time zero contains the initial frame and the first
  // block's actual observation. Prefer the latter recorded observation.
  let found:SignalPoint|undefined
  for(const point of points){if(point.time>time+1e-9)break;found=point}
  return found
}
