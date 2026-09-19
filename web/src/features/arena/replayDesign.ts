import type {ReplayParticipant,Spec} from '../../types'
import {assertSpec} from '../design/spec'

export type ReplayDesignOrigin={matchId:string;flyId:string;name:string}

/** A new editable child of the recorded participant. Never mutate the replay. */
export function draftFromReplay(participant:ReplayParticipant):Spec{
 assertSpec(participant.spec)
 if(!participant.id)throw Error('Recorded participant identity is missing.')
 const spec=JSON.parse(JSON.stringify(participant.spec)) as Spec
 return {...spec,name:spec.name.slice(0,58)+' child',parent_id:participant.id}
}
