import {useMemo} from 'react'
import type {Frame} from '../../types'
import {colors} from '../../types'
import {useI18n} from '../../shared/i18n'
import {planBounds,planFood,planPosition,planTrails,playbackTime,projectObstacle,validPlanWorld,type PlanWorld} from './sceneProjection'
import './scenePresentation.css'

export function ScenePlanView({world,recorded=false,frame,next,alpha=0,frames=[],selectedId,participants=[]}:{world?:PlanWorld|null;recorded?:boolean;frame?:Frame;next?:Frame;alpha?:number;frames?:Frame[];selectedId?:string;participants?:{name:string;color:string}[]}){
 const {t}=useI18n(),valid=validPlanWorld(world)
 const geometry=useMemo(()=>valid?world.obstacles.map(projectObstacle):[],[world,valid])
 const bounds=useMemo(()=>valid?planBounds(world,frames):null,[world,frames,valid])
 if(!valid||!bounds)return <p className="scene-plan-unavailable" role="status">{t('scene.geometryUnavailable')}</p>
 const time=playbackTime(frame,next,alpha),half=world.size/2,unit=Math.max(bounds[2],bounds[3])/65
 const flies='flies' in world?world.flies:[],spawns=Array.isArray(world.spawns)?world.spawns:[]
 return <div className="scene-plan-view">
  <svg className="scene-plan" viewBox={bounds.join(' ')} preserveAspectRatio="xMidYMid meet" role="img" aria-label={t(recorded?'scene.recordedPlan':'scene.layoutPlan')}>
   <title>{t(recorded?'scene.recordedPlan':'scene.layoutPlan')}</title>
   <g transform="scale(1,-1)">
    <rect className="scene-plan-floor" x={-half} y={-half} width={world.size} height={world.size}/>
    {world.ring_radius&&<circle className="scene-plan-ring" r={world.ring_radius}/>}
    {world.task?.control_radius_mm&&<circle className="scene-plan-ring" r={world.task.control_radius_mm} strokeDasharray="4 3"/>}
    {geometry.map((g,i)=><g key={i} className="scene-plan-obstacle" data-obstacle={i}><title>{`${t('scene.obstacle')} ${i+1}`}</title>{g.shape==='box'?<polygon points={g.points.map(p=>p.join(',')).join(' ')}/>:<ellipse cx={g.center[0]} cy={g.center[1]} rx={g.rx} ry={g.ry} transform={`rotate(${g.angle} ${g.center.join(' ')})`}/>}</g>)}
    {flies.map((fly,slot)=><g key={fly.id} className="scene-plan-trail" stroke={colors[fly.color]||colors.mint} data-trail-slot={slot}>{planTrails(frames,slot,time).map((points,i)=>points.length>1?<polyline key={i} points={points.map(p=>p.join(',')).join(' ')}/>:<circle key={i} cx={points[0][0]} cy={points[0][1]} r={unit*.08}/>)}</g>)}
   </g>
   {spawns.map((spawn,i)=>Array.isArray(spawn)&&spawn.length>=3&&spawn.every(Number.isFinite)&&<g key={i} className="scene-plan-spawn" transform={`translate(${spawn[0]} ${-spawn[1]})`}><title>{`${t('scene.spawn')} ${i+1}${participants[i]?` · ${participants[i].name}`:''}`}</title><circle r={unit*.48}/><path d={`M ${-unit*.3} 0 H ${unit*.8} l ${-unit*.3} ${-unit*.2} M ${unit*.8} 0 l ${-unit*.3} ${unit*.2}`} transform={`rotate(${-spawn[2]*180/Math.PI})`}/><text y={unit*1.1} fontSize={unit*.72} textAnchor="middle">{t('scene.spawn')} {i+1}</text></g>)}
   {world.food.map((food,i)=>{const amount=planFood(food,i,recorded,frame),label=`${food.id} · ${t(recorded?'scene.remaining':'scene.initial')}: ${amount===null?t('scene.unrecorded'):amount.toLocaleString(undefined,{maximumFractionDigits:3})}`;return <g key={food.id} className="scene-plan-food" data-food={food.id} data-amount={amount??'unrecorded'} transform={`translate(${food.position[0]} ${-food.position[1]})`}><title>{label}</title><circle r={unit*.6} fill={amount!==null&&amount>0?'currentColor':'none'} strokeDasharray={amount===null?'3 2':undefined}/>{world.task?.goal_food===food.id&&<circle r={unit*.95} fill="none"/>}<text y={-unit*1.15} fontSize={unit*.75} textAnchor="middle">{amount===null?'?':amount.toLocaleString(undefined,{maximumFractionDigits:2})}{world.task?.goal_food===food.id?` · ${t('scene.goal')}`:''}</text></g>})}
   {flies.map((fly,slot)=>{const p=planPosition(frame,next,alpha,slot);return p&&<g key={fly.id} className="scene-plan-position" data-position-slot={slot} transform={`translate(${p[0]} ${-p[1]})`} style={{color:colors[fly.color]||colors.mint}}><title>{fly.name}</title><circle r={unit*(fly.id===selectedId ? .6 : .45)}/><text y={unit*1.5} fontSize={unit*.85} textAnchor="middle">{slot+1} · {fly.name}</text></g>})}
  </svg>
  <div className="scene-plan-legend"><span>{t('scene.axes')}</span><span>{t(recorded?'scene.recordedNote':'scene.layoutNote')}</span>{recorded&&!world.spawns&&<span>{t('scene.spawnsUnavailable')}</span>}{flies.map((fly,slot)=>!planPosition(frame,next,alpha,slot)&&<span role="status" key={fly.id}>{fly.name} · {t('scene.positionUnavailable')}</span>)}</div>
 </div>
}
