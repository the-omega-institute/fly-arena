import type {ArenaMap,Fly,Season} from '../../types'
import {compatibleSensory,playableProfile,mapEligibility} from '../../types'

export type ExperimentIntent='forage'|'contest'|'contact'
export type ExperimentMode='forage'|'contest'|'sumo'|'duel'
export type ExperimentSetup={selected:string;opponent:string;mapId:string;mode:string;seedText:string;duration:number;bridgeProfile:string;sensoryProfile:string}
export type ExperimentRequest={sandbox:true;bridge_profile:string;sensory_profile:string;fly_ids:string[];map_id:string;mode:ExperimentMode;seed:number;duration_seconds:number}
export type ExperimentPlan={setup:ExperimentSetup;seeds:number[];matches:ExperimentRequest[];submissions:({endpoint:'/matches';body:ExperimentRequest}|{endpoint:'/observation-series';body:Omit<ExperimentRequest,'seed'|'mode'>&{mode:'forage'|'duel';seeds:number[];name:string}}|{endpoint:'/tournaments';body:Omit<ExperimentRequest,'seed'|'mode'>&{mode:'contest'|'sumo';seeds:number[];name:string}})[]}
export function experimentIntent(mode:string):ExperimentIntent{return mode==='sumo'||mode==='duel'?'contact':mode==='forage'?'forage':'contest'}
export function intentMode(intent:ExperimentIntent,map:ArenaMap):ExperimentMode|undefined{
 if(intent!=='forage'&&!mapEligibility(map).competition_eligible)return undefined
 if(intent==='contact')return map.id==='duel'&&map.modes.includes('duel')?'duel':map.id==='ring'&&map.modes.includes('sumo')?'sumo':undefined
 return map.id!=='duel'&&map.modes.includes(intent)?intent:undefined
}
export function parseExperimentSeeds(text:string):number[]|null{
 const parts=text.trim().split(/[\s,]+/)
 if(parts.length<1||parts.length>3||parts.some(p=>!/^\d+$/.test(p)))return null
 const seeds=parts.map(Number)
 return seeds.some(s=>!Number.isInteger(s)||s<0||s>2147483647)||new Set(seeds).size!==seeds.length?null:seeds
}
export function opponentReason(subject:Fly|undefined,opponent:Fly,bridge:string):string|undefined{
 if(subject?.id===opponent.id)return 'Choose a different opponent.'
 if(!subject||!subject.spec.connectome_sha256||!subject.spec.model_profile)return 'Select a saved subject with recorded graph and model.'
 if(opponent.spec.connectome_sha256!==subject.spec.connectome_sha256)return 'Different connectome; this comparison requires the same graph.'
 if(opponent.spec.model_profile!==subject.spec.model_profile)return 'Different neural model; this comparison requires the same model.'
 if(bridge==='sensorimotor-research-v2'&&opponent.spec.model_profile!=='malecns-lif-cpu-v1')return 'Research v2 supports LIF designs only. Choose Legacy v1 for rate designs.'
}
export function opponentGroup(fly:Fly,owner?:string){return fly.reference_kind==='wildtype'?'WT reference':fly.reference_kind==='official'?'Official reference':owner&&fly.owner===owner?'Your other saved designs':'Public designs'}
export function experimentScore(mode:string,mapId:string,metadata?:ArenaMap['metadata']){
 if(mapId!=='blank'&&!mapEligibility({id:mapId,metadata}).competition_eligible)return 'Observation only — arrival time is not a scored outcome yet (#82). Failure to arrive stays visible; there is no competitive winner.'
 return mode==='duel'?'Score: seconds of exclusive center occupancy. Contested occupancy earns neither fly points. Contact is measured separately; no attack or injury actions are modeled.':mode==='sumo'?'Score: ring exit decides the winner. Simultaneous exits or no exit before the limit are a draw; food is not the winning metric.':mapId==='labyrinth'?'Observation: first physical contact with the goal food and the exploration path. Failure to arrive stays visible; there is no opponent or competitive winner.':mapId==='blank'?'Observation: unstimulated movement and recorded neural activity. There is no food, opponent or competitive winner.':mode==='forage'?'Score: finite food actually consumed by this fly. This is a solo observation, with no competitive winner.':'Score: finite food actually consumed. More food wins; equal consumption is a draw. Movement alone does not score.'
}
export function buildExperimentPlan(setup:ExperimentSetup,flies:Fly[],maps:ArenaMap[],season:Season|null):{plan:ExperimentPlan|null;errors:string[]}{
 const errors:string[]=[],subject=flies.find(f=>f.id===setup.selected),opponent=flies.find(f=>f.id===setup.opponent),map=maps.find(m=>m.id===setup.mapId),seeds=parseExperimentSeeds(setup.seedText)
 const profile=season?.match_profiles?.find(p=>p.id===setup.bridgeProfile)
 if(!subject)errors.push('Choose a saved fly before submitting.')
 else if(!subject.spec.connectome_sha256||!subject.spec.model_profile)errors.push('Select a saved subject with recorded graph and model.')
 else if(setup.bridgeProfile==='sensorimotor-research-v2'&&subject.spec.model_profile!=='malecns-lif-cpu-v1')errors.push('Research v2 supports LIF designs only. Choose Legacy v1 for rate designs.')
 if(!playableProfile(profile))errors.push('Selected match profile is unavailable.')
 if(!compatibleSensory(season,setup.bridgeProfile,setup.sensoryProfile)||(setup.sensoryProfile!=='odor-only-v1'&&!season?.sensory_profiles?.some(p=>p.id===setup.sensoryProfile&&p.ready)))errors.push('Selected sensory profile is unavailable or incompatible. Choose an available profile explicitly.')
 if(!map||intentMode(experimentIntent(setup.mode),map)!==setup.mode)errors.push('Choose a map offered for this intent.')
 if(setup.mode!=='forage'){
  if(!opponent)errors.push('Choose an opponent before submitting.')
  else {const reason=opponentReason(subject,opponent,setup.bridgeProfile);if(reason)errors.push(reason)}
 }
 if(!seeds)errors.push('Enter 1–3 distinct whole-number seeds from 0 to 2147483647, separated by commas.')
 const tournament=setup.mode==='contest'||setup.mode==='sumo'
 if(!Number.isInteger(setup.duration)||setup.duration<1||setup.duration>180)errors.push('Use 1–180 whole simulated seconds per match.')
 if(errors.length||!seeds)return {plan:null,errors}
 const base={sandbox:true as const,bridge_profile:setup.bridgeProfile,sensory_profile:setup.sensoryProfile,map_id:setup.mapId,mode:setup.mode as ExperimentMode,duration_seconds:setup.duration}
 const slots=setup.mode==='forage'?[[setup.selected]]:[[setup.selected,setup.opponent],[setup.opponent,setup.selected]]
 const matches=seeds.flatMap(seed=>slots.map(fly_ids=>({...base,fly_ids,seed})))
 const submissions:ExperimentPlan['submissions']=tournament?[{endpoint:'/tournaments',body:{...base,mode:setup.mode as 'contest'|'sumo',fly_ids:slots[0],seeds,name:`Arena ${setup.mode} · ${setup.selected.slice(0,8)}`}}]:setup.mode==='duel'||seeds.length>1?[{endpoint:'/observation-series',body:{...base,mode:setup.mode as 'forage'|'duel',fly_ids:slots[0],seeds,name:`Arena ${setup.mode} · ${setup.selected.slice(0,8)}`}}]:matches.map(body=>({endpoint:'/matches',body}))
 return {plan:{setup:{...setup},seeds,matches,submissions},errors:[]}
}
