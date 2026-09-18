import type {Fly} from '../../types'

/** Reference status comes from the server, never the display name or owner. */
export function matchingWildType(flies:Fly[], subject?:Fly):Fly|undefined {
  return flies.find(f=>f.reference_kind==='wildtype'&&(!subject||
    (f.spec.model_profile===subject.spec.model_profile&&f.spec.connectome_sha256===subject.spec.connectome_sha256)))
}

export function wildTypeChallenge(flies:Fly[], selected:string) {
  const subject=flies.find(f=>f.id===selected)
  const reference=matchingWildType(flies,subject)
  if(!subject||!reference||subject.id===reference.id)return null
  return {subject,reference,map_id:'orchard',mode:'contest',duration_seconds:2,seed:42} as const
}
