import type {ArenaLayout} from '../../types'

export type MapMetadata={supported_modes:string[];recommended_horizon_seconds:{min:number;max:number};purpose:string;scientific_status:'qualified'|'observation-only';status_reason:string}
export type MapPreviewLayout=ArenaLayout&{metadata?:MapMetadata;modes?:string[]}
const modeLabels:Record<string,string>={forage:'Solo forage',contest:'Two-fly food competition',sumo:'Contact ring contest',duel:'Contact / territory'}

// Count the returned seeded geometry, never a map-name lookup or contestants.
// Missing geometry stays unknown; an actual empty array is a measured zero.
export function mapPurpose(layout:Partial<MapPreviewLayout>,t:(key:string)=>string=key=>key){
  const metadata=layout.metadata,horizon=metadata?.recommended_horizon_seconds
  return {
    spawnSlots:Array.isArray(layout.spawns)?layout.spawns.length:null,
    foodCount:Array.isArray(layout.food)?layout.food.length:null,
    obstacleCount:Array.isArray(layout.obstacles)?layout.obstacles.length:null,
    sizeMm:typeof layout.size==='number'&&Number.isFinite(layout.size)&&layout.size>0?layout.size:null,
    purpose:metadata?.purpose?t(metadata.purpose):t('Map purpose unavailable'),
    modes:(metadata?.supported_modes||layout.modes||[]).map(mode=>t(modeLabels[mode]||mode)),
    status:t(metadata?.scientific_status==='qualified'?'Qualified':metadata?.scientific_status==='observation-only'?'Observation only':'Scientific status unavailable'),
    limitation:metadata?.status_reason?t(metadata.status_reason):t('Map suitability metadata is unavailable on this server.'),
    horizon:horizon&&Number.isFinite(horizon.min)&&Number.isFinite(horizon.max)&&horizon.min>0&&horizon.max>=horizon.min?`${horizon.min}–${horizon.max}`:null,
  }
}
