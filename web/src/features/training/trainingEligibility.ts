// Mirrors TrainingSpec/EvaluationCondition in services/training.py; contract tests pin both lists.
// Both bridges accept the same maps. Server readiness, brain and sensory compatibility are separate gates.
export const trainingMapIds=['orchard','maze','scarcity','ring','terrarium','enclosure','canopy','switchback','blank'] as const
export const trainingBridgeProfiles=['legacy-v1','sensorimotor-research-v2'] as const
export function trainingEligibilityProblem(mapId:string,bridgeProfile='legacy-v1',mode:'forage'|'contest'='forage'):string|null{
  if(!trainingBridgeProfiles.some(id=>id===bridgeProfile))return 'This sensorimotor setup is not supported for training. Choose a supported setup.'
  if(!trainingMapIds.some(id=>id===mapId))return 'This map is not eligible for training with the selected sensorimotor setup. Choose a training map.'
  if(mapId==='blank'&&mode==='contest')return 'Blank control supports solo observation only. Choose Collect food or another training map.'
  return null
}
export function eligibleTrainingMaps<T extends {id:string}>(maps:T[],bridgeProfile='legacy-v1',mode:'forage'|'contest'='forage'):T[]{
  return maps.filter(map=>trainingEligibilityProblem(map.id,bridgeProfile,mode)===null)
}
