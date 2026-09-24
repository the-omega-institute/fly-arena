import {validateObstacleGeometry} from '../arena/obstacleGeometry'
import type {ArenaObstacle} from '../../types'
import type {ExperimentSubject,ProbeReport,TrajectoryPoint} from '../../shared/research'

export type ProbeGeometry={size:number;obstacles:ArenaObstacle[];spawns:number[][];food:{id:string;position:number[];initial:number}[]}
export type ProbeTrack={subject:ExperimentSubject;status:string;segments:TrajectoryPoint[][];invalid:boolean}
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)
const vector=(v:unknown,n:number):v is number[]=>Array.isArray(v)&&v.length===n&&v.every(finite)
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'
/** Never fill absent coordinates or dimensions with plausible scene defaults. */
export function probeGeometry(value:unknown):ProbeGeometry|null{
 if(!record(value)||!finite(value.size)||value.size<=0||!Array.isArray(value.obstacles)||!Array.isArray(value.food)||!Array.isArray(value.spawns))return null
 const obstacles:ArenaObstacle[]=[]
 for(const o of value.obstacles){
  if(!record(o)||!validateObstacleGeometry(o))return null
  obstacles.push({position:[...o.position],size:[...o.size],...(o.shape?{shape:o.shape as ArenaObstacle['shape']}:{}),...(o.quaternion?{quaternion:[...o.quaternion as number[]]}:{}),...(o.material?{material:o.material as ArenaObstacle['material']}:{}),...(typeof o.color==='string'?{color:o.color}:{})})
 }
 const food:ProbeGeometry['food']=[]
 for(const f of value.food){if(!record(f)||typeof f.id!=='string'||!vector(f.position,3)||!finite(f.initial)||f.initial<0)return null;food.push({id:f.id,position:[...f.position],initial:f.initial})}
 if(!value.spawns.every(p=>vector(p,3)))return null
 return {size:value.size,obstacles,food,spawns:value.spawns.map(p=>[...p])}
}

/** Invalid samples break trails; ambiguous time ordering invalidates the track. */
export function probeSegments(points:TrajectoryPoint[],duration:number){
 const segments:TrajectoryPoint[][]=[];let current:TrajectoryPoint[]=[];let previous=-Infinity;let invalid=false
 for(const p of points){
  if(p&&finite(p.time)&&p.time<=previous)return {segments:[],invalid:true}
  if(p&&finite(p.time))previous=p.time
  if(!p||![p.time,p.x,p.y,p.yaw].every(finite)||p.time<0||!finite(duration)||p.time>duration){if(current.length)segments.push(current);current=[];invalid=true;continue}
  current.push({time:p.time,x:p.x,y:p.y,yaw:p.yaw})
 }
 if(current.length)segments.push(current)
 return {segments,invalid}
}

/** Display interpolation only, within a contiguous recorded interval; no extrapolation. */
export function probeSampleAt(segments:TrajectoryPoint[][],time:number):TrajectoryPoint|null{
 if(!finite(time))return null
 for(const points of segments){
  if(!points.length||time<points[0].time||time>points[points.length-1].time)continue
  const i=points.findIndex(p=>p.time>=time),b=points[i]
  if(b.time===time)return b
  const a=points[i-1],f=(time-a.time)/(b.time-a.time),angle=Math.atan2(Math.sin(b.yaw-a.yaw),Math.cos(b.yaw-a.yaw))
  return {time,x:a.x+(b.x-a.x)*f,y:a.y+(b.y-a.y)*f,yaw:a.yaw+angle*f}
 }
 return null
}

export function adaptProbeScene(reports:ProbeReport[],subjects:ExperimentSubject[],seed:number){
 const selected=subjects.map(subject=>({subject,matches:reports.filter(r=>r.seed===seed&&r.fly_id===subject.fly_id&&r.artifact_id===subject.artifact_id)}))
 const tracks:ProbeTrack[]=selected.map(({subject,matches})=>{const r=matches.length===1?matches[0]:null;return {subject,status:r?.status||'Unavailable',...(r?probeSegments(Array.isArray(r.trajectory)?r.trajectory:[],r.duration_seconds):{segments:[],invalid:matches.length>1})}})
 const matched=selected.flatMap(s=>s.matches)
 let geometry:ProbeGeometry|null=null;let reason:'missing'|'invalid'|'conflict'|null=null
 if(!matched.length||matched.some(r=>!r.scene))reason='missing'
 else{
  const scenes=matched.map(r=>probeGeometry(r.scene))
  if(scenes.some(s=>!s))reason='invalid'
  else if(scenes.some(s=>JSON.stringify(s)!==JSON.stringify(scenes[0]))||selected.some(s=>s.matches.length>1))reason='conflict'
  else geometry=scenes[0]
 }
 return {geometry,reason,tracks}
}

/** Frame recorded bounds and outlying data at equal x/y physical scale. */
export function probeFraming(geometry:ProbeGeometry,tracks:ProbeTrack[]){
 const half=geometry.size/2;let x0=-half,x1=half,y0=-half,y1=half,z1=0
 const include=(x:number,y:number,z=0)=>{x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);z1=Math.max(z1,z)}
 for(const o of geometry.obstacles){const r=Math.hypot(...o.size)/2;include(o.position[0]-r,o.position[1]-r,o.position[2]+r);include(o.position[0]+r,o.position[1]+r)}
 for(const p of geometry.spawns)include(p[0],p[1]) // Third spawn coordinate is yaw, never altitude.
 for(const f of geometry.food)include(f.position[0],f.position[1],f.position[2])
 for(const track of tracks)for(const segment of track.segments)for(const p of segment)include(p.x,p.y)
 const span=Math.max(x1-x0,y1-y0,z1*2,1),target:[number,number,number]=[(x0+x1)/2,(y0+y1)/2,0]
 return {span,target,position:[target[0]+span*.8,target[1]-span,span*1.15] as [number,number,number]}
}
