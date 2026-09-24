import type {Fly,Identity} from '../../types'
import {ArenaSeries,ExperimentSeries} from './ExperimentSeries'
import type {Series} from './ExperimentSeries'

export function ObservationSeries({series,flies}:{series:Series;flies:Fly[]}){return <ExperimentSeries series={series} flies={flies} observation/>}
export function ArenaObservations({observationId='',identity,flies}:{observationId?:string;identity:Identity|null;flies:Fly[]}){return <ArenaSeries seriesId={observationId} identity={identity} flies={flies} observation/>}
