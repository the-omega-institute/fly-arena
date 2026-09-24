// Synthetic UI contract fixtures only; these are not simulation evidence.
export function replayInspectionFixture(profile,subjects){
 const frame=(time)=>({time,tick:time*10000,poses:[],positions:[[time,0,1],[0,time,1]],scores:[time*.2,0],energy:[100-time,100-time],traces:[{olfactory:1},{olfactory:0}],drives:[[.4,.5],[.3,.4]],senses:subjects.map(()=>({odor:[.2,.2],visual:[0,0],touch:1,contact_food:['food-0'],nearest_food:1}))})
 const frames=[frame(0),frame(.5),frame(1)]
 return {scene:{flies:subjects,food:[]},frames,frame:frames[0],flies:subjects,selectedId:subjects[0].id,season:{connectome:{circuits:[]}},
  events:profile==='legacy-v1'?[]:[{type:'food_contact',tick:2500,slot:0,objects:['food-0']},{type:'environment_contact',tick:5000,slot:1,objects:['wall-0']}],
  match:{id:'fixture-'+profile,status:'verified',request:{bridge_profile:profile,fly_ids:subjects.map(f=>f.id),map_id:'orchard',mode:'contest',seed:42,duration_seconds:1},participants:subjects,result:{outcome:'draw',scores:[.2,0]}}}
}
