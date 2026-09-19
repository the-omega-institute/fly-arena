import type {Frame,ReplayEvent,Scene} from '../../types'

export const finiteResource=(value:unknown):number|null=>typeof value==='number'&&Number.isFinite(value)&&value>=0?value:null
export function resourceTotal(values:unknown[]|undefined,count:number):number|null{
  if(!values||values.length!==count)return null
  const amounts=values.map(finiteResource)
  return amounts.some(v=>v===null)?null:amounts.reduce<number>((sum,v)=>sum+v!,0)
}

/** Observed transitions, never inferred from missing values or nominal ticks. */
export function resourceMoments(scene:Scene,frames:Frame[]){
  const depletions:{food:number;time:number}[]=[],firstIntake:(number|null)[]=scene.flies.map(()=>null)
  let priorFood:(number|null)[]=scene.food.map(()=>null),priorScores:(number|null)[]=scene.flies.map(()=>null)
  const depleted=new Set<number>()
  for(const f of frames){
    const food=scene.food.map((_,i)=>finiteResource(f.food?.[i])),scores=scene.flies.map((_,i)=>finiteResource(f.scores?.[i]))
    food.forEach((value,i)=>{if(value===0&&priorFood[i]!==null&&priorFood[i]! > 0&&!depleted.has(i)){depletions.push({food:i,time:f.time});depleted.add(i)}})
    scores.forEach((value,i)=>{if(value!==null&&priorScores[i]!==null&&value>priorScores[i]!&&firstIntake[i]===null)firstIntake[i]=f.time})
    priorFood=food;priorScores=scores
  }
  return {depletions,firstIntake}
}

export function resourcePath(frames:Frame[],read:(f:Frame)=>number|null,total:number){
  if(frames.length<2||total<=0)return ''
  const start=frames[0].time,end=frames.at(-1)!.time
  if(end<=start)return ''
  let connected=false
  return frames.map(f=>{const value=read(f);if(value===null){connected=false;return ''}
    const point=`${((f.time-start)/(end-start)*600).toFixed(2)},${(96-value/total*88).toFixed(2)}`
    const part=(connected?'L':'M')+point;connected=true;return part
  }).join(' ')
}

/** Attribute intake only when the event ledger accounts for the final scores.
 * Missing food/slot metadata must not become invented per-patch zeroes. */
export function resourceShares(scene:Scene,frames:Frame[],events:ReplayEvent[]|undefined,tick:number){
  const last=frames.at(-1)
  if(!events||!last||!Number.isFinite(tick)||!Number.isFinite(last.tick))return null
  const intake=events.filter(e=>e.type==='intake')
  if(intake.some(e=>!Number.isInteger(e.tick)||e.tick<0||e.tick>last.tick||
    !Number.isInteger(e.slot)||e.slot!<0||e.slot!>=scene.flies.length||
    typeof e.food!=='number'||!Number.isInteger(e.food)||e.food<0||e.food>=scene.food.length||finiteResource(e.amount)===null))return null
  const finalScores=scene.flies.map(()=>0),finalFood=scene.food.map(()=>0)
  const shares=scene.food.map(()=>({amounts:scene.flies.map(()=>0),firstTicks:scene.flies.map<number|null>(()=>null)}))
  for(const e of intake){
    const food=e.food as number,slot=e.slot!,amount=e.amount!
    finalScores[slot]+=amount;finalFood[food]+=amount
    if(e.tick>tick)continue
    shares[food].amounts[slot]+=amount
    if(amount>0)shares[food].firstTicks[slot]=Math.min(shares[food].firstTicks[slot]??e.tick,e.tick)
  }
  if(finalScores.some((v,i)=>finiteResource(last.scores?.[i])===null||Math.abs(v-last.scores![i])>1e-5)||
    finalFood.some((v,i)=>finiteResource(scene.food[i].initial)===null||finiteResource(last.food?.[i])===null||Math.abs(scene.food[i].initial-last.food![i]-v)>1e-5))return null
  return shares.map(row=>({...row,firstTimes:row.firstTicks.map(t=>t===null?null:frames.find(f=>f.tick>=t)?.time??null)}))
}
