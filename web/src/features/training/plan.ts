import {trainingEligibilityProblem} from './trainingEligibility'
import type {ArenaMap,Fly,Season,TrainingBridge} from '../../types'

export type RecordedCondition={match_id:string;status:string;map_id?:string;seed?:number;bridge_profile?:string;sensory_profile?:string;fitness_objective?:string;duration_seconds?:number;mode?:string;opponent_id?:string}
export type ContinuationRecord={fly:Fly;continuation?:{conditions:RecordedCondition[];requires_copy:boolean}}
export type ContinuationReview={record:RecordedCondition;retained:boolean;reason:string}
/** Reuse actual requests, never infer observations or objectives from scores. */
export function continuationPlan(record:ContinuationRecord,season:Season,maps:ArenaMap[],flies:Fly[]){
  const bridges:TrainingBridge[]=season.training_bridge_profiles??(season.match_profiles??[]).filter(p=>p.id==='legacy-v1')
  const senses=season.training_sensory_profiles??[{id:'odor-only-v1',ready:true}]
  const objectives=season.training_fitness_objectives??[{id:'food',ready:true}]
  const reviews:ContinuationReview[]=[];const conditions:{map_id:string;seed:number}[]=[]
  let environment:RecordedCondition|null=null
  const setupKey=(c:RecordedCondition)=>JSON.stringify([c.bridge_profile,c.sensory_profile,c.fitness_objective,c.duration_seconds,c.mode,c.opponent_id])
  for(const c of record.continuation?.conditions??[]){
    let reason='';const bridge=bridges.find(p=>p.id===c.bridge_profile)
    const map=maps.find(m=>m.id===c.map_id)
    if(!['verified','failed'].includes(c.status))reason='Evaluation has not finished; its conditions were not reused.'
    else if(!c.bridge_profile||!bridge?.ready||bridge.models&&!bridge.models.includes(record.fly.spec.model_profile))reason='Recorded bridge is missing, unavailable, or incompatible with this brain.'
    else if(c.mode!=='forage'&&c.mode!=='contest')reason='Recorded mode is missing or unsupported for training.'
    else if(!map||!map.modes.includes(c.mode))reason='Recorded map is unavailable for this mode.'
    else reason=trainingEligibilityProblem(map.id,c.bridge_profile,c.mode,map.metadata)||''
    if(!reason&&(!Number.isInteger(c.seed)||c.seed!<0||c.seed!>2147483647))reason='Recorded seed is missing or outside training limits.'
    if(!reason&&(!Number.isInteger(c.duration_seconds)||c.duration_seconds!<1||c.duration_seconds!>30))reason='Recorded duration is missing or outside training limits.'
    if(!reason&&c.sensory_profile&&(!senses.some(p=>p.id===c.sensory_profile&&p.ready)||bridge?.sensory_profiles&&!bridge.sensory_profiles.includes(c.sensory_profile)))reason='Recorded sensory input is no longer eligible.'
    if(!reason&&c.fitness_objective&&!objectives.some(p=>p.id===c.fitness_objective&&p.ready))reason='Recorded selection objective is no longer eligible.'
    if(!reason&&c.mode==='contest'){
      const opponent=flies.find(f=>f.id===c.opponent_id)
      if(!opponent||bridge?.models&&!bridge.models.includes(opponent.spec.model_profile))reason='Recorded opponent is unavailable or incompatible.'
    }
    if(!reason&&environment&&setupKey(environment)!==setupKey(c))reason='A separate session is needed for this different recorded setup.'
    if(!reason&&conditions.some(value=>value.map_id===c.map_id&&value.seed===c.seed))reason='Duplicate map and seed; already retained once.'
    if(!reason&&conditions.length===4)reason='A session supports at most four distinct conditions.'
    if(reason){reviews.push({record:c,retained:false,reason});continue}
    environment??=c;conditions.push({map_id:c.map_id!,seed:c.seed!})
    reviews.push({record:c,retained:true,reason:c.status==='failed'?'Recorded failed evaluation; retaining its setup does not imply success.':'Recorded condition is currently eligible.'})
  }
  return {founder_id:record.fly.id,environment,conditions,reviews}
}

export type PlanLimits={population:number;generations:number;budget:number;duration:number;seed:number;circuits:string[];name:string;mode:'forage'|'contest';founder:string;opponent:string;strategy?:string;map_id?:string;bridge_profile?:string;conditions?:{map_id:string;seed:number}[]}
export function evaluationCount(p:Pick<PlanLimits,'population'|'generations'|'mode'|'conditions'>){
  return p.population*p.generations*(p.mode==='contest'?2:1)*(p.conditions?.length??1)
}
export function planProblem(p:PlanLimits):string|null{
  if(!p.name.trim())return 'Enter a session name.'
  if(!p.founder)return 'Choose a starting fly.'
  if(p.mode==='contest'&&!p.opponent)return 'Choose a fixed opponent.'
  if(p.strategy!=='external'&&!p.circuits.length)return 'Choose at least one circuit.'
  for(const [value,min,max] of [[p.population,2,6],[p.generations,1,8],[p.budget,2,96],[p.duration,1,30],[p.seed,0,2147483647]]){
    if(!Number.isInteger(value)||value<min||value>max)return 'Use whole numbers within the displayed limits.'
  }
  if(p.conditions){
    if(p.conditions.length<1||p.conditions.length>4)return 'Choose one to four evaluation conditions.'
    if(p.conditions.some(c=>!Number.isInteger(c.seed)||c.seed<0||c.seed>2147483647))return 'Use a valid map and whole-number seed for every condition.'
    if(new Set(p.conditions.map(c=>c.map_id+':'+c.seed)).size!==p.conditions.length)return 'Choose distinct map/seed conditions.'
  }
  if(p.map_id){const problem=trainingEligibilityProblem(p.map_id,p.bridge_profile,p.mode);if(problem)return problem}
  for(const condition of p.conditions??[{map_id:p.map_id??'orchard',seed:p.seed}]){
    const problem=trainingEligibilityProblem(condition.map_id,p.bridge_profile,p.mode)
    if(problem)return problem
  }
  if(evaluationCount(p)>p.budget)return 'This plan exceeds your evaluation budget.'
  return null
}

export function memberRole(strategy:string,generation:number,slot:number):string{
  if(generation===0&&slot===0)return 'Baseline'
  if(strategy==='external')return 'Optimizer proposal'
  return slot===0?'Retained parent':'Mutation'
}
export function trainingFocus(hash:string):string{
  const value=new URLSearchParams(hash.replace(/^#/, '')).get('training')||''
  return /^[a-f0-9]{32}$/.test(value)?value:''
}
export function trainingHash(id:string):string{
  const p=new URLSearchParams({tab:'train'});if(id)p.set('training',id);return '#'+p.toString()
}

export function competitionSetup(spec:{map_id:string;seed:number;duration_seconds:number;mode:string;opponent_id?:string|null;bridge_profile?:string;sensory_profile?:string;evaluation_conditions?:{map_id:string;seed:number}[]|null}){
  const condition=spec.evaluation_conditions?.[0]||spec
  return {map_id:condition.map_id,seed:condition.seed,duration_seconds:spec.duration_seconds,
    opponent_id:spec.mode==='contest'?spec.opponent_id:null,
    bridge_profile:spec.bridge_profile||'legacy-v1',sensory_profile:spec.sensory_profile||'odor-only-v1'}
}
