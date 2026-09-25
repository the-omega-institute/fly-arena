import type {Match} from '../../types'

export type RecordedDescriptorKey='food'|'latter_half_food'|'upright_fraction'|'path_length_mm'
export type RecordedDescriptorSummary=Partial<Record<RecordedDescriptorKey,number>>
export type RecordedDescriptorDelta={key:RecordedDescriptorKey;delta:number;candidate:number;parent:number}
export type RecordedCondition={map_id:string|null;seed:number|null;duration_seconds:number|null;bridge_profile:string;sensory_profile:string;mode:string|null;own_slot:number|null;opponent_ids:string[]}
export type RecordedDescriptorRecord={matchId:string;conditionKey:string;condition:RecordedCondition;descriptors:RecordedDescriptorSummary;unavailable:RecordedDescriptorKey[];conditionAvailable:boolean}
export type RecordedDescriptorPair={candidate:RecordedDescriptorRecord;parent:RecordedDescriptorRecord}
export type RecordedDescriptorComparison={deltas:RecordedDescriptorDelta[];pairs:RecordedDescriptorPair[];unmatchedCandidate:RecordedDescriptorRecord[];unmatchedParent:RecordedDescriptorRecord[];unavailableCandidate:RecordedDescriptorRecord[];unavailableParent:RecordedDescriptorRecord[]}

const descriptorKeys:RecordedDescriptorKey[]=['food','latter_half_food','upright_fraction','path_length_mm']
const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)

function ownSlot(match:Match,flyId:string){
 const slot=match.request?.fly_ids?.indexOf(flyId)??-1
 return slot>=0?slot:null
}

function condition(match:Match,flyId:string):RecordedCondition{
 const request=match.request
 const map_id=typeof request?.map_id==='string'&&request.map_id?request.map_id:null
 const seed=typeof request?.seed==='number'&&Number.isInteger(request.seed)?request.seed:null
 const duration_seconds=typeof request?.duration_seconds==='number'&&Number.isFinite(request.duration_seconds)?request.duration_seconds:null
 const mode=typeof request?.mode==='string'&&request.mode?request.mode:null
 const own=ownSlot(match,flyId)
 return {map_id,seed,duration_seconds,bridge_profile:request?.bridge_profile||'legacy-v1',sensory_profile:request?.sensory_profile||'odor-only-v1',mode,own_slot:own,opponent_ids:(request?.fly_ids||[]).filter(id=>id!==flyId)}
}

function keyOf(value:RecordedCondition){return JSON.stringify([value.map_id,value.seed,value.duration_seconds,value.bridge_profile,value.sensory_profile,value.mode,value.own_slot,value.opponent_ids])}

function descriptorValues(match:Match,slot:number|null):RecordedDescriptorSummary{
 const values:RecordedDescriptorSummary={}
 if(slot===null)return values
 const behavior=match.result?.behavior?.[slot]
 if(behavior?.schema==='sustained-foraging-v1'){
  for(const key of ['food','latter_half_food','upright_fraction'] as const)if(finite(behavior[key]))values[key]=behavior[key]
 }
 const path=match.result?.task?.path_length_mm?.[slot]
 if(finite(path))values.path_length_mm=path
 return values
}

function records(matches:Match[],flyId:string):RecordedDescriptorRecord[]{
 return matches.filter(match=>match.status==='verified').flatMap(match=>{
  const descriptor=condition(match,flyId),descriptors=descriptorValues(match,descriptor.own_slot)
  const unavailable=descriptorKeys.filter(key=>!finite(descriptors[key]))
  const conditionAvailable=descriptor.map_id!==null&&descriptor.seed!==null&&descriptor.duration_seconds!==null&&descriptor.mode!==null&&descriptor.own_slot!==null&&(descriptor.mode!=='contest'||descriptor.opponent_ids.length>0)
  return [{matchId:match.id,conditionKey:keyOf(descriptor),condition:descriptor,descriptors,unavailable,conditionAvailable}]
 })
}

/** Keep the normalized receipt condition visible to callers and pair only complete condition identities. */
export function recordedDescriptorRecords(matches:Match[],flyId:string){return records(matches,flyId)}

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

/** Compare one-to-one pairs of identical recorded conditions; this is descriptive and is never a score. */
export function recordedDescriptorDeltas(candidateMatches:Match[],candidateId:string,parentMatches:Match[],parentId:string):RecordedDescriptorDelta[]{
 return recordedDescriptorComparison(candidateMatches,candidateId,parentMatches,parentId).deltas
}

export function recordedDescriptorComparison(candidateMatches:Match[],candidateId:string,parentMatches:Match[],parentId:string):RecordedDescriptorComparison{
 const candidate=records(candidateMatches,candidateId),parent=records(parentMatches,parentId),parentByKey=new Map<string,RecordedDescriptorRecord[]>()
 for(const record of parent)if(record.conditionAvailable)parentByKey.set(record.conditionKey,[...(parentByKey.get(record.conditionKey)||[]),record])
 const pairs:RecordedDescriptorPair[]=[],unmatchedCandidate:RecordedDescriptorRecord[]=[],unmatchedParent:RecordedDescriptorRecord[]=[],unavailableCandidate=candidate.filter(record=>record.unavailable.length>0||!record.conditionAvailable),unavailableParent=parent.filter(record=>record.unavailable.length>0||!record.conditionAvailable)
 for(const record of candidate){
  if(!record.conditionAvailable){continue}
  const bucket=parentByKey.get(record.conditionKey)
  if(bucket?.length){pairs.push({candidate:record,parent:bucket.shift()!})}else unmatchedCandidate.push(record)
 }
 const pairedParent=new Set(pairs.map(pair=>pair.parent))
 for(const record of parent)if(record.conditionAvailable&&!pairedParent.has(record))unmatchedParent.push(record)
 const values={} as Record<RecordedDescriptorKey,{candidate:number[];parent:number[]}>
 for(const key of descriptorKeys)values[key]={candidate:[],parent:[]}
 for(const pair of pairs)for(const key of descriptorKeys)if(finite(pair.candidate.descriptors[key])&&finite(pair.parent.descriptors[key])){values[key].candidate.push(pair.candidate.descriptors[key]!);values[key].parent.push(pair.parent.descriptors[key]!)}
 const deltas=descriptorKeys.flatMap(key=>values[key].candidate.length?[{key,candidate:values[key].candidate.reduce((sum,value)=>sum+value,0)/values[key].candidate.length,parent:values[key].parent.reduce((sum,value)=>sum+value,0)/values[key].parent.length,delta:values[key].candidate.reduce((sum,value)=>sum+value,0)/values[key].candidate.length-values[key].parent.reduce((sum,value)=>sum+value,0)/values[key].parent.length}]:[])
 return {deltas,pairs,unmatchedCandidate,unmatchedParent,unavailableCandidate,unavailableParent}
}
