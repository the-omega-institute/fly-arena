export type EvaluationCondition={map_id:string;seed:number}
export function evaluationConditions(spec:{map_id:string;seed:number;evaluation_conditions?:EvaluationCondition[]|null}):EvaluationCondition[]{
  return spec.evaluation_conditions??[{map_id:spec.map_id,seed:spec.seed}]
}
export type ComparableRun = {
  id:string; status:string; evaluation_context?:string;
  spec:{name:string;strategy:string;founder_id:string;opponent_id:string|null;map_id:string;
    mode:string;duration_seconds:number;seed:number;bridge_profile:string;population:number;
    generations:number;max_evaluations:number;circuits:string[];mutation_strength:number;evaluation_conditions?:EvaluationCondition[]|null};
  baseline_fitness:number|null; evaluations_started:number; evaluations_completed:number;
  evaluations_total:number; members:{generation:number;slot:number;fitness:number|null}[];
}

const finite = (value:number|null):value is number => value !== null && Number.isFinite(value)

export function summarizeRun(run:ComparableRun){
  const scores=run.members.map(m=>m.fitness).filter(finite)
  const best=scores.length?Math.max(...scores):null
  const baseline=finite(run.baseline_fitness)?run.baseline_fitness:null
  const history=Array.from({length:run.spec.generations},(_,generation)=>{
    const scores=run.members.filter(m=>m.generation===generation).map(m=>m.fitness).filter(finite)
    return {generation,best:scores.length?Math.max(...scores):null,
      evaluated:scores.length,complete:scores.length===run.spec.population}
  })
  return {best,baseline,gain:best===null||baseline===null?null:best-baseline,history,
    budgetedSeconds:run.evaluations_completed*run.spec.duration_seconds}
}

export function comparisonDifferences(runs:ComparableRun[]):string[]{
  if(runs.length<2)return []
  const fields=[['founder_id','Starting fly'],['mode','Objective'],
    ['duration_seconds','Seconds per evaluation'],['seed','Seed'],['bridge_profile','Match scientific profile']] as const
  const differences:string[]=fields.filter(([field])=>new Set(runs.map(r=>r.spec[field])).size>1).map(([,label])=>label)
  if(new Set(runs.map(r=>JSON.stringify(evaluationConditions(r.spec).map(c=>[c.map_id,c.seed]).sort()))).size>1)differences.push('Evaluation conditions')
  if(runs.some(r=>r.spec.mode==='contest')&&new Set(runs.map(r=>r.spec.opponent_id)).size>1)differences.push('Fixed opponent')
  if(runs.some(r=>!r.evaluation_context))differences.push('Evaluation version unavailable')
  else if(new Set(runs.map(r=>r.evaluation_context)).size>1)differences.push('Evaluation version')
  return differences
}

export function curveScale(runs:ComparableRun[]){
  const values=runs.flatMap(run=>summarizeRun(run).history.map(g=>g.best).filter(finite))
  const low=Math.min(0,...values),high=Math.max(0,...values)
  const padding=Math.max((high-low)*.12,.05)
  const min=low-padding,max=high+padding
  return {min,max,y:(value:number)=>170-(value-min)/(max-min)*140,
    x:(generation:number)=>60+generation/Math.max(1,...runs.map(r=>r.spec.generations-1))*580}
}
