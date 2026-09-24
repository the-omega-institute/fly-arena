import {mapEligibility,mapEligibilityDefaults} from '../../types'
import type {ArenaMap} from '../../types'
// Creation eligibility is separate from the historical TrainingSpec map literals.
// Both bridges accept the same maps. Server readiness, brain and sensory compatibility are separate gates.
export const trainingMapIds=Object.keys(mapEligibilityDefaults).filter(id=>mapEligibility({id}).training_eligible)
export const trainingBridgeProfiles=['legacy-v1','sensorimotor-research-v2'] as const
export function trainingEligibilityProblem(mapId:string,bridgeProfile='legacy-v1',mode:'forage'|'contest'='forage',metadata?:ArenaMap['metadata']):string|null{
  if(!trainingBridgeProfiles.some(id=>id===bridgeProfile))return 'This sensorimotor setup is not supported for training. Choose a supported setup.'
  if(!mapEligibility({id:mapId,metadata}).training_eligible)return 'This map is not eligible for training with the selected sensorimotor setup. Choose a training map.'
  if(mapId==='blank'&&mode==='contest')return 'Blank control supports solo observation only. Choose Collect food or another training map.'
  return null
}
export function eligibleTrainingMaps<T extends Pick<ArenaMap,'id'|'metadata'>>(maps:T[],bridgeProfile='legacy-v1',mode:'forage'|'contest'='forage'):T[]{
  return maps.filter(map=>trainingEligibilityProblem(map.id,bridgeProfile,mode,map.metadata)===null)
}
