import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
const out=fs.mkdtempSync(path.join(os.tmpdir(),'experiment-setup-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
for(const name of ['types','features/arena/experimentSetup']){
 const source=fs.readFileSync(new URL(`../src/${name}.ts`,import.meta.url),'utf8'),dest=path.join(out,name+'.js')
 fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)
}
const require=createRequire(path.join(out,'package.json'))
const {buildExperimentPlan,parseExperimentSeeds,intentMode,opponentReason,opponentGroup,experimentScore}=require('./features/arena/experimentSetup.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
const spec={model_profile:'malecns-lif-cpu-v1',connectome_sha256:'c'.repeat(64)}
const subject={id:'a'.repeat(32),name:'Subject',owner:'me',spec,reference_kind:'user'},wt={id:'b'.repeat(32),name:'WT',owner:'server',spec,reference_kind:'wildtype'}
const maps=[{id:'orchard',modes:['forage','contest']},{id:'ring',modes:['forage','contest','sumo']},{id:'blank',modes:['forage']},{id:'labyrinth',modes:['forage']},{id:'duel',modes:['duel']}]
const season={match_profiles:[{id:'legacy-v1',ready:true},{id:'sensorimotor-research-v2',ready:false,sandbox_ready:true,sensory_profiles:['odor-only-v1','engineered-kernel-contact-v1']}],sensory_profiles:[{id:'engineered-kernel-contact-v1',ready:true}]}
const setup={selected:subject.id,opponent:wt.id,mapId:'orchard',mode:'contest',seedText:'42',duration:2,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'}
const build=(patch={},flies=[subject,wt],catalog=season)=>buildExperimentPlan({...setup,...patch},flies,maps,catalog)

test('seed parsing rejects empty, fractional, duplicate, negative, overflow and excessive inputs',()=>{
 for(const text of ['',',','42,','-1','1.2','NaN','Infinity','1e2','0x10','1 01','2147483648','1,2,3,4'])assert.equal(parseExperimentSeeds(text),null,text)
 assert.deepEqual(parseExperimentSeeds('0, 42\n2147483647'),[0,42,2147483647])
 assert.equal(build({seedText:'42,42'}).plan,null)
})
test('intent maps cannot silently turn solo, food or territory into another mode',()=>{
 assert.deepEqual(maps.filter(m=>intentMode('forage',m)).map(m=>m.id),['orchard','ring','blank','labyrinth'])
 assert.deepEqual(maps.filter(m=>intentMode('contest',m)).map(m=>m.id),['orchard','ring'])
 assert.deepEqual(maps.filter(m=>intentMode('contact',m)).map(m=>[m.id,intentMode('contact',m)]),[['ring','sumo'],['duel','duel']])
 for(const [mapId,mode] of [['duel','contest'],['orchard','sumo'],['blank','contest'],['labyrinth','contest'],['ring','duel'],['missing','forage'],['orchard','invented']])assert.equal(build({mapId,mode}).plan,null)
})
test('WT and official groups depend on server provenance; owner and spoofed names confer no reference status',()=>{
 assert.equal(opponentGroup(wt,'me'),'WT reference')
 assert.equal(opponentGroup({...wt,reference_kind:'official'},'me'),'Official reference')
 assert.equal(opponentGroup({...subject,name:'WT',reference_kind:null},'me'),'Your other saved designs')
 assert.equal(opponentGroup({...subject,owner:'other',name:'Official reference'},'me'),'Public designs')
 assert.equal(opponentGroup(subject),'Public designs')
})
test('ineligible opponents stay explicit and do not get replaced by a reference',()=>{
 assert.match(opponentReason(subject,subject,'legacy-v1'),/different opponent/)
 for(const [field,value,reason] of [['model_profile','malecns-rate-cpu-v1',/neural model/],['connectome_sha256','other',/connectome/]]){
  const rival={...wt,spec:{...spec,[field]:value}},result=build({},[subject,rival])
  assert.equal(result.plan,null);assert.ok(result.errors.some(e=>reason.test(e)))
 }
 assert.equal(build({opponent:'missing'}).plan,null)
 assert.equal(build({selected:'missing'}).plan,null)
 assert.equal(build({opponent:subject.id}).plan,null)
})
test('food series uses the existing tournament request and exactly reverses slots with identical seeds',()=>{
 const {plan,errors}=build({seedText:'0,42,2147483647'})
 assert.deepEqual(errors,[]);assert.equal(plan.matches.length,6);assert.equal(plan.matches.reduce((sum,m)=>sum+m.duration_seconds,0),12)
 assert.deepEqual(plan.submissions,[{endpoint:'/tournaments',body:{sandbox:true,bridge_profile:'legacy-v1',sensory_profile:'odor-only-v1',map_id:'orchard',mode:'contest',duration_seconds:2,fly_ids:[subject.id,wt.id],seeds:[0,42,2147483647],name:'Arena contest · aaaaaaaa'}}])
 for(let i=0;i<6;i+=2){assert.deepEqual(plan.matches[i+1],{...plan.matches[i],fly_ids:[wt.id,subject.id]})}
 assert.equal(setup.seedText,'42');assert.equal(setup.mode,'contest')
})
test('contact territory uses explicit reversed match requests without substituting contest or using unsupported tournament mode',()=>{
 const {plan}=build({mapId:'duel',mode:'duel',duration:180,seedText:'42 43'})
 assert.equal(plan.matches.length,4);assert.equal(plan.submissions.length,4)
 assert.deepEqual(plan.submissions.map(s=>s.endpoint),Array(4).fill('/matches'))
 assert.deepEqual(plan.submissions.map(s=>s.body),plan.matches)
 assert.deepEqual(plan.matches.map(m=>[m.mode,m.map_id,m.seed,m.fly_ids]),[['duel','duel',42,[subject.id,wt.id]],['duel','duel',42,[wt.id,subject.id]],['duel','duel',43,[subject.id,wt.id]],['duel','duel',43,[wt.id,subject.id]]])
 assert.ok(plan.matches.every(m=>m.sandbox&&m.duration_seconds===180))
})
test('solo submits one fly per seed even when an incompatible or missing opponent was previously selected',()=>{
 const {plan}=build({mode:'forage',mapId:'labyrinth',opponent:'missing',seedText:'42,43',duration:300})
 assert.equal(plan.matches.length,2);assert.ok(plan.matches.every(m=>m.fly_ids.length===1&&m.fly_ids[0]===subject.id&&m.mode==='forage'))
 assert.ok(plan.submissions.every(s=>s.endpoint==='/matches'))
})
test('contract duration bounds and ring scoring remain mode-specific',()=>{
 for(const duration of [0,1.5,31,300])assert.equal(build({duration}).plan,null)
 for(const duration of [1,30])assert.ok(build({duration}).plan)
 for(const duration of [0,301,NaN])assert.equal(build({duration,mode:'duel',mapId:'duel'}).plan,null)
 const {plan}=build({mapId:'ring',mode:'sumo'})
 assert.equal(plan.submissions[0].body.mode,'sumo');assert.equal(plan.matches.length,2)
 assert.match(experimentScore('sumo','ring'),/food is not the winning metric/)
 assert.match(experimentScore('duel','duel'),/exclusive center/)
 assert.match(experimentScore('forage','blank'),/no food/)
 assert.match(experimentScore('forage','labyrinth'),/Failure to arrive/)
})
test('profile admission preserves chosen senses, supports sandbox readiness and rejects unavailable or incompatible combinations',()=>{
 const kernel={bridgeProfile:'sensorimotor-research-v2',sensoryProfile:'engineered-kernel-contact-v1'}
 const {plan}=build(kernel);assert.ok(plan);assert.ok(plan.matches.every(m=>m.sensory_profile===kernel.sensoryProfile))
 assert.equal(build({},[subject,wt],null).plan,null)
 assert.equal(build({bridgeProfile:'unknown'}).plan,null)
 assert.equal(build({...kernel,sensoryProfile:'missing'}).plan,null)
 assert.equal(build(kernel,[subject,wt],{...season,sensory_profiles:[{id:kernel.sensoryProfile,ready:false}]}).plan,null)
 assert.equal(build(kernel,[subject,wt],{...season,match_profiles:[{id:kernel.bridgeProfile,ready:false,sandbox_ready:false}]}).plan,null)
 const rate=[subject,wt].map(f=>({...f,spec:{...spec,model_profile:'malecns-rate-cpu-v1'}}))
 assert.equal(build(kernel,rate).plan,null);assert.ok(build({},rate).plan)
})

test('issue 82 maps are solo observations and never paired food comparisons',()=>{
 for(const id of ['maze','switchback','labyrinth']){
  const map={id,modes:['forage','contest']}
  assert.equal(intentMode('contest',map),undefined)
  assert.equal(intentMode('forage',map),'forage')
  for(const mode of ['contest','forage']){
   const {plan}=buildExperimentPlan({...setup,mapId:id,mode},[subject,wt],[map],season)
   assert.equal(!!plan,mode==='forage')
  }
  assert.match(experimentScore('forage',id),/Observation only.*not a scored outcome yet.*#82/)
 }
 const metadata={competition_eligible:false}
 assert.equal(intentMode('contest',{id:'orchard',modes:['forage','contest'],metadata}),undefined)
 assert.match(experimentScore('forage','orchard',metadata),/Observation only/)
})
