export type PlanLimits={population:number;generations:number;budget:number;duration:number;seed:number;circuits:string[];name:string;mode:'forage'|'contest';founder:string;opponent:string}
export function planProblem(p:PlanLimits):string|null{
  if(!p.name.trim())return 'Enter a session name.'
  if(!p.founder)return 'Choose a starting fly.'
  if(p.mode==='contest'&&!p.opponent)return 'Choose a fixed opponent.'
  if(!p.circuits.length)return 'Choose at least one circuit.'
  for(const [value,min,max] of [[p.population,2,6],[p.generations,1,8],[p.budget,2,96],[p.duration,1,10],[p.seed,0,2147483647]]){
    if(!Number.isInteger(value)||value<min||value>max)return 'Use whole numbers within the displayed limits.'
  }
  if(p.population*p.generations*(p.mode==='contest'?2:1)>p.budget)return 'This plan exceeds your evaluation budget.'
  return null
}
