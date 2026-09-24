import type {ArenaMap,Fly} from '../../types'
import {intentMode,opponentReason} from './experimentSetup'
import type {ExperimentSetup} from './experimentSetup'

export const experimentPresets=[
 {id:'scarcity',mapId:'scarcity',mode:'contest',seedText:'42, 43',duration:5},
 {id:'center',mapId:'duel',mode:'duel',seedText:'42, 43',duration:5},
 {id:'maze',mapId:'labyrinth',mode:'forage',seedText:'42, 43, 44',duration:30},
] as const
export type ExperimentPreset=typeof experimentPresets[number]
export function presetAvailable(preset:ExperimentPreset,maps:ArenaMap[]){const map=maps.find(m=>m.id===preset.mapId);return !!map&&intentMode(preset.mode==='duel'?'contact':preset.mode,map)===preset.mode}
export function applyExperimentPreset(preset:ExperimentPreset,setup:ExperimentSetup,flies:Fly[]):ExperimentSetup{
 const subject=flies.find(f=>f.id===setup.selected),compatible=(f:Fly)=>!opponentReason(subject,f,setup.bridgeProfile)
 const wt=flies.find(f=>f.reference_kind==='wildtype'&&compatible(f))
 const opponent=preset.mode==='forage'?'':preset.id==='scarcity'?wt?.id||'':flies.find(f=>f.id===setup.opponent&&compatible(f))?.id||wt?.id||''
 return {...setup,mapId:preset.mapId,mode:preset.mode,seedText:preset.seedText,duration:preset.duration,opponent}
}
