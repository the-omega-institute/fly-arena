import type {Fly} from '../../types'
import type {Series} from '../arena/ExperimentSeries'
import {opponentReason} from '../arena/experimentSetup'

/** Public alternatives must be real user/agent designs, not our own or references. */
export function publicComparisonFlies(flies:Fly[],subject:Fly){
 return flies.filter(f=>!!f.owner&&f.owner!==subject.owner&&f.id!==subject.id&&
  f.reference_kind!=='wildtype'&&f.reference_kind!=='official'&&!opponentReason(subject,f,'legacy-v1'))
}

/** Only summarize a complete server-verified pair, joining outcomes by fly identity. */
export function comparisonResult(series:Series,subjectId:string){
 if(series.status!=='complete'||series.issues.length||series.unexpected_match_ids.length||
  series.expected_matches!==2||series.verified_matches!==2||series.schedule.length!==2)return null
 const rivalId=series.spec.fly_ids.find(id=>id!==subjectId)
 if(!rivalId||series.spec.fly_ids.length!==2||!series.spec.fly_ids.includes(subjectId))return null
 const own:number[]=[],rival:number[]=[]
 for(const leg of series.schedule){
  if(leg.status!=='verified'||leg.issues.length||!leg.outcomes)return null
  const a=leg.outcomes.find(o=>o.fly_id===subjectId),b=leg.outcomes.find(o=>o.fly_id===rivalId)
  if(!a||!b||!Number.isFinite(a.score)||!Number.isFinite(b.score))return null
  own.push(a.score);rival.push(b.score)
 }
 return {own:(own[0]+own[1])/2,rival:(rival[0]+rival[1])/2,
  wins:series.schedule.filter(leg=>leg.outcomes?.find(o=>o.fly_id===subjectId)?.outcome==='win').length,
  draws:series.schedule.filter(leg=>leg.outcomes?.find(o=>o.fly_id===subjectId)?.outcome==='draw').length}
}
