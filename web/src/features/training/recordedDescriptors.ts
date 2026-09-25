import type {Match} from '../../types'

export type RecordedDescriptorKey='food'|'latter_half_food'|'upright_fraction'|'path_length_mm'
export type RecordedDescriptorSummary=Partial<Record<RecordedDescriptorKey,number>>
export type RecordedDescriptorDelta={key:RecordedDescriptorKey;delta:number;candidate:number;parent:number}

const descriptorKeys:RecordedDescriptorKey[]=['food','latter_half_food','upright_fraction','path_length_mm']
const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)

function ownSlot(match:Match,flyId:string){
 const slot=match.request?.fly_ids?.indexOf(flyId)??-1
 return slot>=0?slot:null
}

/** Extract only descriptors emitted in the verified match result. Missing is not zero. */
export function recordedDescriptorSummary(matches:Match[],flyId:string):RecordedDescriptorSummary{
 const values:Record<RecordedDescriptorKey,number[]>={food:[],latter_half_food:[],upright_fraction:[],path_length_mm:[]}
 for(const match of matches){
  if(match.status!=='verified'||!match.result)continue
  const slot=ownSlot(match,flyId)
  if(slot===null)continue
  const behavior=match.result.behavior?.[slot]
  if(behavior?.schema==='sustained-foraging-v1'){
   for(const key of ['food','latter_half_food','upright_fraction'] as const)if(finite(behavior[key]))values[key].push(behavior[key])
  }
  const path=match.result.task?.path_length_mm?.[slot]
  if(finite(path))values.path_length_mm.push(path)
 }
 return Object.fromEntries(descriptorKeys.flatMap(key=>values[key].length?[[key,values[key].reduce((sum,value)=>sum+value,0)/values[key].length]]:[])) as RecordedDescriptorSummary
}

/** Compare paired recorded summaries; this is descriptive and is never a score. */
export function recordedDescriptorDeltas(candidateMatches:Match[],candidateId:string,parentMatches:Match[],parentId:string):RecordedDescriptorDelta[]{
 const candidate=recordedDescriptorSummary(candidateMatches,candidateId)
 const parent=recordedDescriptorSummary(parentMatches,parentId)
 return descriptorKeys.flatMap(key=>finite(candidate[key])&&finite(parent[key])?[{key,delta:candidate[key]-parent[key],candidate:candidate[key],parent:parent[key]}]:[])
}
