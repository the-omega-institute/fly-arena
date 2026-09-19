import type {Frame,Scene} from '../../types'

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
