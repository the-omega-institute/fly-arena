export type ReplayReceipt = {
 request?:Record<string,unknown>;runtime?:Record<string,unknown>;replay_policy?:Record<string,unknown>;recording_policy?:Record<string,unknown>;observation_motor?:Record<string,unknown>;[key:string]:unknown
}
export type ReplayEvidence = {match?:{request?:Record<string,unknown>};receipt?:ReplayReceipt|null;participant?:{spec?:Record<string,unknown>}}
export type ComparisonConditionId='map'|'seed'|'horizon'|'bridgeReadout'|'sensoryProfile'|'motorProfile'|'runtimeSource'|'recordingPolicy'
export type ComparisonCondition = {id:ComparisonConditionId;label:string;status:'agree'|'differ'|'unavailable';left:string|null;right:string|null}
export type ReplayComparisonContext = {conditions:ComparisonCondition[];interpretation:'matched'|'descriptive'|'unavailable';hasDifferences:boolean;hasUnavailable:boolean}

function object(value:unknown):Record<string,unknown>|undefined{return value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:undefined}
function stable(value:unknown):string|null{
 if(value===undefined||value===null)return null
 if(typeof value==='string'||typeof value==='number'||typeof value==='boolean')return JSON.stringify(value)
 if(Array.isArray(value)){const parts=value.map(stable);return '['+parts.map(part=>part===null?'null':part).join(',')+']'}
 const source=object(value);if(!source)return null
 return '{'+Object.keys(source).sort().map(key=>JSON.stringify(key)+':'+(stable(source[key])??'null')).join(',')+'}'
}
function first(...values:unknown[]):unknown{return values.find(value=>value!==undefined&&value!==null&&value!=='')}
function request(evidence:ReplayEvidence):Record<string,unknown>{return {...object(evidence.match?.request),...object(evidence.receipt?.request)}}
function runtime(evidence:ReplayEvidence):Record<string,unknown>{return object(evidence.receipt?.runtime)||{}}
function scalar(value:unknown):string|null{return value===undefined||value===null||value===''?null:String(value)}
function field(evidence:ReplayEvidence,key:string):string|null{return scalar(request(evidence)[key])}
function bridgeReadout(evidence:ReplayEvidence):string|null{
 const receipt=evidence.receipt||{},run=runtime(evidence),profile=object(run.profile),hashes=object(profile?.hashes)
 const bridge=first(request(evidence).bridge_profile,run.bridge_profile,'legacy-v1')
 const readout=first(receipt.readout_sha256,receipt.readout_weights_sha256,run.readout_weights_sha256,run.readout_sha256,hashes?.readout,hashes?.readout_metadata)
 if(bridge===undefined||readout===undefined)return null
 return `${String(bridge)} · ${String(readout)}`
}
function sensory(evidence:ReplayEvidence):string|null{
 const run=runtime(evidence),profile=object(run.sensory_profile)
 return scalar(first(request(evidence).sensory_profile,profile?.id,run.sensory_profile))
}
function motor(evidence:ReplayEvidence):string|null{
 const receipt=evidence.receipt||{},run=runtime(evidence),profile=object(run.profile),motorProfile=object(run.motor_profile),motorManifest=object(receipt.observation_motor)
 return scalar(first(motorManifest?.profile_id,receipt.motor_profile,run.motor_profile,run.motor_id,motorProfile?.id,profile?.motor_id,motorProfile?.id))
}
function source(evidence:ReplayEvidence):string|null{
 const receipt=evidence.receipt||{},run=runtime(evidence),closure=object(run.closure),profile=object(run.profile),hashes=object(profile?.hashes)
 const runtimeIdentity=first(receipt.runtime_identity,receipt.source_identity,run.runtime_id,run.runtime_identity,run.source_id,run.source_identity,run.sha256,run.runtime_sha256)
 const sources=first(run.sources,closure?.sources)
 const lock=first(run.lock_sha256,closure?.lock_sha256)
 const connectome=first(run.connectome_sha256,closure?.connectome_sha256)
 const closureHash=first(hashes?.runtime_closure)
 const value={runtime_identity:runtimeIdentity,sources,lock_sha256:lock,connectome_sha256:connectome,runtime_closure:closureHash}
 return stable(Object.values(value).some(item=>item!==undefined&&item!==null)?value:null)
}
function recording(evidence:ReplayEvidence):string|null{
 const receipt=evidence.receipt||{},run=runtime(evidence)
 return stable(first(receipt.recording_policy,receipt.replay_policy,run.recording_policy,run.replay_policy))
}

const definitions:[ComparisonConditionId,string,(evidence:ReplayEvidence)=>string|null][]=[
 ['map','map',evidence=>field(evidence,'map_id')],
 ['seed','seed',evidence=>field(evidence,'seed')],
 ['horizon','horizon',evidence=>field(evidence,'duration_seconds')],
 ['bridgeReadout','bridge/readout',bridgeReadout],
 ['sensoryProfile','sensory profile',sensory],
 ['motorProfile','motor profile',motor],
 ['runtimeSource','runtime/source identity',source],
 ['recordingPolicy','recording policy',recording],
]

export function replayComparisonContext(left:ReplayEvidence,right:ReplayEvidence):ReplayComparisonContext{
 const conditions=definitions.map(([id,label,read])=>{
  const leftValue=read(left),rightValue=read(right)
  const status:ComparisonCondition['status']=leftValue===null||rightValue===null?'unavailable':leftValue===rightValue?'agree':'differ'
  return {id,label,status,left:leftValue,right:rightValue}
 })
 const hasDifferences=conditions.some(condition=>condition.status==='differ'),hasUnavailable=conditions.some(condition=>condition.status==='unavailable')
 return {conditions,interpretation:hasDifferences?'descriptive':hasUnavailable?'unavailable':'matched',hasDifferences,hasUnavailable}
}

export const compareReplayConditions=replayComparisonContext
