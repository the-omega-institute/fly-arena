import {useMemo} from 'react'
import type {Frame,Scene} from '../../types'
import {colors} from '../../types'
import {useI18n} from '../../shared/i18n'
import {finiteResource,resourceMoments,resourcePath,resourceTotal} from './resourceAccounting'

export function SharedResources({scene,frame,frames,onSeek}:{scene:Scene;frame?:Frame;frames:Frame[];onSeek:(time:number)=>void}){
  const {locale}=useI18n(),zh=locale==='zh-CN'
  const initial=resourceTotal(scene.food?.map(f=>f.initial),scene.food?.length??0)
  const moments=useMemo(()=>scene.food?resourceMoments(scene,frames):{depletions:[],firstIntake:[]},[scene,frames])
  const paths=useMemo(()=>{
    if(!initial||!scene.food)return []
    return [{id:'remaining',color:'#77877d',path:resourcePath(frames,f=>resourceTotal(f.food,scene.food.length),initial)},...scene.flies.map((fly,slot)=>({id:fly.id+':'+slot,color:colors[fly.color]||colors.mint,path:resourcePath(frames,f=>finiteResource(f.scores?.[slot]),initial)}))]
  },[scene,frames,initial])
  if(!scene.food?.length)return null
  const remaining=resourceTotal(frame?.food,scene.food.length),consumed=resourceTotal(frame?.scores,scene.flies.length)
  const shown=(value:number|null)=>value===null?'—':value.toFixed(3)
  const first=frames[0]?.time??0,last=frames.at(-1)?.time??first,time=frame?.time??first
  const cursor=last>first?(time-first)/(last-first)*600:0
  const available=initial!==null&&initial>0&&remaining!==null&&consumed!==null
  return <section className="shared-resources" aria-label={zh?'共享食物与摄取记录':'Shared food and intake records'}>
    <div className="shared-resources-heading"><div><strong>{zh?'同一份食物，怎样被吃掉':'Where the shared food went'}</strong><p>{scene.flies.length>1?(zh?'双方争夺同一份有限食物。沿时间轴查看谁先吃到、各自吃了多少，以及还剩多少。':'Both flies compete for the same finite food. Follow who ate first, each fly’s intake, and what remains.'):(zh?'食物会被实际摄取消耗；查看停留摄食、食物耗尽和后续行为。':'Actual feeding depletes food. Inspect feeding, depletion and subsequent behavior.')}</p></div><b>{time.toFixed(2)} s</b></div>
    <div className="shared-resource-totals"><span>{zh?'初始食物':'Initial food'}<b>{shown(initial)}</b></span><span>{zh?'场上剩余':'Remaining in arena'}<b>{shown(remaining)}</b></span>{scene.flies.map((fly,slot)=><span key={slot} style={{borderColor:colors[fly.color]||colors.mint}}>{fly.name}<b>{shown(finiteResource(frame?.scores?.[slot]))}</b><small>{zh?'累计摄取':'Cumulative intake'} · {slot+1} · {fly.id.slice(0,8)}</small></span>)}</div>
    {available&&<div className="shared-resource-allocation" role="img" aria-label={zh?'当前食物分配：已摄取与场上剩余':'Current food allocation: consumed and remaining'}>{scene.flies.map((fly,slot)=><span key={slot} style={{width:`${Math.min(100,(frame!.scores![slot]/initial!)*100)}%`,background:colors[fly.color]||colors.mint}} title={`${fly.name}: ${shown(finiteResource(frame?.scores?.[slot]))}`}/>)}<span style={{width:`${Math.min(100,remaining!/initial!*100)}%`,background:'#77877d'}} title={`${zh?'场上剩余':'Remaining'}: ${shown(remaining)}`}/></div>}
    {initial!==null&&initial>0&&frames.length>1&&<><svg className="shared-resource-timeline" viewBox="0 0 600 106" preserveAspectRatio="none" role="img" aria-label={zh?'共享资源随时间的变化':'Shared resource history'} onClick={e=>{const rect=e.currentTarget.getBoundingClientRect();if(rect.width>0)onSeek(first+Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width))*(last-first))}}>
      {[8,52,96].map(y=><line key={y} x1="0" x2="600" y1={y} y2={y} stroke="currentColor" opacity=".1"/>)}
      {paths.map(p=><path key={p.id} d={p.path} fill="none" stroke={p.color} strokeWidth="2" strokeDasharray={p.id==='remaining'?'5 4':undefined} vectorEffect="non-scaling-stroke"/>)}
      {moments.depletions.map(d=><line key={d.food} x1={(d.time-first)/(last-first)*600} x2={(d.time-first)/(last-first)*600} y1="5" y2="99" stroke="currentColor" opacity=".2" strokeDasharray="2 4"/>)}
      <line x1={cursor} x2={cursor} y1="0" y2="106" stroke="currentColor" opacity=".7"/>
    </svg><div className="shared-resource-axis"><span>{first.toFixed(2)} s</span><span>{zh?'虚线：余量；实线：各自摄取。纵轴':'Dashed: remaining; solid: individual intake. Scale'} 0–{shown(initial)}</span><span>{last.toFixed(2)} s</span></div></>}
    <div className="shared-resource-moments">{scene.flies.map((fly,slot)=>moments.firstIntake[slot]!==null&&moments.firstIntake[slot]!==undefined?<button key={slot} onClick={()=>onSeek(moments.firstIntake[slot]!)}>{slot+1} · {fly.name} · {zh?'首次记录摄取':'First recorded intake'} {moments.firstIntake[slot]!.toFixed(2)} s →</button>:null)}{moments.depletions.map(d=><button key={'food-'+d.food} onClick={()=>onSeek(d.time)}>{scene.food[d.food].id} · {zh?'首次记录耗尽':'First observed depletion'} {d.time.toFixed(2)} s →</button>)}</div>
    <div className="shared-resource-patches">{scene.food.map((food,i)=><span key={food.id}><b>{food.id}</b><span>{shown(finiteResource(frame?.food?.[i]))} / {shown(finiteResource(food.initial))}</span></span>)}</div>
    <p className="shared-resource-note">{zh?'数值来自当前回放帧，缺失记录显示 —。各只果蝇的摄取量汇总所有食物点；耗尽属于共享环境，不归因给某一只果蝇。跳转定位首次观察到变化的采样时刻。食物单位为比赛规则中的资源量。':'Values come from the current replay frame; — means missing. Each fly’s intake totals all food patches. Depletion belongs to the shared environment and is not attributed to one fly. Jumps use the first sample showing the change. Food units follow the match rules.'}</p>
  </section>
}
