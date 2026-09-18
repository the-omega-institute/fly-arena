export type PlanLimits={population:number;generations:number;budget:number;duration:number;seed:number;circuits:string[];name:string;mode:'forage'|'contest';founder:string;opponent:string;strategy?:string;conditions?:{map_id:string;seed:number}[]}
export function evaluationCount(p:Pick<PlanLimits,'population'|'generations'|'mode'|'conditions'>){
  return p.population*p.generations*(p.mode==='contest'?2:1)*(p.conditions?.length??1)
}
export function planProblem(p:PlanLimits):string|null{
  if(!p.name.trim())return 'Enter a session name.'
  if(!p.founder)return 'Choose a starting fly.'
  if(p.mode==='contest'&&!p.opponent)return 'Choose a fixed opponent.'
  if(p.strategy!=='external'&&!p.circuits.length)return 'Choose at least one circuit.'
  for(const [value,min,max] of [[p.population,2,6],[p.generations,1,8],[p.budget,2,96],[p.duration,1,10],[p.seed,0,2147483647]]){
    if(!Number.isInteger(value)||value<min||value>max)return 'Use whole numbers within the displayed limits.'
  }
  if(p.conditions){
    if(p.conditions.length<1||p.conditions.length>4)return 'Choose one to four evaluation conditions.'
    if(p.conditions.some(c=>!['orchard','maze','scarcity','ring'].includes(c.map_id)||!Number.isInteger(c.seed)||c.seed<0||c.seed>2147483647))return 'Use a valid map and whole-number seed for every condition.'
    if(new Set(p.conditions.map(c=>c.map_id+':'+c.seed)).size!==p.conditions.length)return 'Choose distinct map/seed conditions.'
  }
  if(evaluationCount(p)>p.budget)return 'This plan exceeds your evaluation budget.'
  return null
}

export function memberRole(strategy:string,generation:number,slot:number):string{
  if(generation===0&&slot===0)return 'Baseline'
  if(strategy==='external')return 'Optimizer proposal'
  return slot===0?'Retained parent':'Mutation'
}
export function trainingFocus(hash:string):string{
  const value=new URLSearchParams(hash.replace(/^#/, '')).get('training')||''
  return /^[a-f0-9]{32}$/.test(value)?value:''
}
export function trainingHash(id:string):string{
  const p=new URLSearchParams({tab:'train'});if(id)p.set('training',id);return '#'+p.toString()
}
