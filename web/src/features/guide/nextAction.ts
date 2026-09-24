import {useEffect,useState} from 'react'
import {api} from '../../api'
import type {ArenaMap,Fly,Identity,Match,Season} from '../../types'
import {buildExperimentPlan} from '../arena/experimentSetup'
import {wildTypeChallenge} from '../arena/wildtype'

export function guideSubject(flies:Fly[],selected:string,owner?:string){
 const saved=flies.filter(f=>f.owner===owner&&!!owner&&f.reference_kind!=='wildtype'&&f.reference_kind!=='official')
 return saved.find(f=>f.id===selected)||saved[0]
}

/** Use the same preset and admission checks as Arena; preparing never submits work. */
export function guideComparisonPlan(flies:Fly[],selected:string,maps:ArenaMap[],season:Season|null){
 const preset=wildTypeChallenge(flies,selected)
 if(!preset||!maps.find(map=>map.id===preset.map_id)?.modes?.includes(preset.mode))return null
 return buildExperimentPlan({selected:preset.subject.id,opponent:preset.reference.id,mapId:preset.map_id,mode:preset.mode,seedText:String(preset.seed),duration:preset.duration_seconds,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'},flies,maps,season).plan
}

/** A failed, partial or unmatched pair cannot advance onboarding. Zero effects can. */
export function baselineComparison(flies:Fly[],subject:Fly|undefined,matches:Match[]){
 if(!subject)return null
 const reference=wildTypeChallenge(flies,subject.id)?.reference
 if(!reference)return null
 const eligible=matches.filter(m=>m.status==='verified'&&!!m.result?.receipt_sha256&&m.request.mode==='contest'&&m.request.fly_ids.length===2&&m.request.fly_ids.includes(subject.id)&&m.request.fly_ids.includes(reference.id))
 const conditions=(m:Match)=>JSON.stringify([m.request.map_id,m.request.mode,m.request.seed,m.request.duration_seconds,m.request.bridge_profile||'legacy-v1',m.request.sensory_profile||'odor-only-v1'])
 for(const first of eligible){const second=eligible.find(m=>m.id!==first.id&&conditions(m)===conditions(first)&&m.request.fly_ids[0]===first.request.fly_ids[1]);if(second)return [first,second]}
 return null
}

type GuideRecord={fly:Fly;origin:null|{strategy:string;round:number;slot:number;fitness:number|null;saved:boolean};experiences:{match:Match}[]}
export function hasRecordedEvolution(record:GuideRecord|null,subject?:Fly){
 return !!subject&&record?.fly.id===subject.id&&!!record.origin&&['evolution','random_search','external'].includes(record.origin.strategy)&&(record.origin.round>1||record.origin.slot>0)&&record.origin.saved&&typeof record.origin.fitness==='number'&&Number.isFinite(record.origin.fitness)&&!!subject.spec.parent_id
}
export function useGuideEvidence(subject:Fly|undefined,identity:Identity|null){
 const [state,setState]=useState<{id:string;record:GuideRecord|null;error:string}>({id:'',record:null,error:''})
 useEffect(()=>{
  if(!subject)return
  const controller=new AbortController()
  api<GuideRecord>('/lives/'+encodeURIComponent(subject.id),{signal:controller.signal},identity).then(record=>{if(!controller.signal.aborted)setState({id:subject.id,record,error:''})}).catch(e=>{if(!controller.signal.aborted)setState({id:subject.id,record:null,error:String(e.message||e)})})
  return()=>controller.abort()
 },[subject?.id,identity?.id,identity?.token])
 return state.id===subject?.id?state:{record:null,error:''}
}
