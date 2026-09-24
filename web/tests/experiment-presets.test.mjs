import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
const out=fs.mkdtempSync(path.join(os.tmpdir(),'experiment-presets-'))
fs.writeFileSync(path.join(out,'package.json'),'{}')
for(const name of ['types','features/arena/experimentSetup','features/arena/experimentPresets','shared/messages/maps']){
 const dest=path.join(out,name+'.js');fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,ts.transpileModule(fs.readFileSync(new URL('../src/'+name+'.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)
}
const require=createRequire(path.join(out,'package.json'))
const {experimentPresets,applyExperimentPreset,presetAvailable}=require('./features/arena/experimentPresets.js')
const {buildExperimentPlan}=require('./features/arena/experimentSetup.js')
const {mapsMessages}=require('./shared/messages/maps.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))
const spec={connectome_sha256:'c'.repeat(64),model_profile:'malecns-lif-cpu-v1'}
const subject={id:'a'.repeat(32),spec},wt={id:'b'.repeat(32),spec,reference_kind:'wildtype'},spoof={id:'c'.repeat(32),name:'WT',spec,reference_kind:'user'}
const setup={selected:subject.id,opponent:spoof.id,mapId:'orchard',mode:'forage',seedText:'9',duration:2,bridgeProfile:'legacy-v1',sensoryProfile:'odor-only-v1'}
const maps=[{id:'scarcity',modes:['forage','contest']},{id:'duel',modes:['duel']},{id:'labyrinth',modes:['forage']}]
const season={match_profiles:[{id:'legacy-v1',ready:true}]}
test('questions create editable plans with exact map, schedule and existing submission paths',()=>{
 const snapshot=JSON.stringify(setup),plans=experimentPresets.map(p=>{
  assert.ok(presetAvailable(p,maps))
  const next=applyExperimentPreset(p,setup,[subject,wt,spoof])
  assert.equal(next.selected,subject.id);assert.equal(next.bridgeProfile,setup.bridgeProfile);assert.equal(next.sensoryProfile,setup.sensoryProfile)
  return buildExperimentPlan(next,[subject,wt,spoof],maps,season).plan
 })
 assert.equal(JSON.stringify(setup),snapshot)
 assert.deepEqual(plans.map(p=>p.submissions[0].endpoint),['/tournaments','/observation-series','/observation-series'])
 assert.deepEqual(plans.map(p=>p.matches.length),[4,4,3])
 assert.equal(plans[0].setup.opponent,wt.id);assert.equal(plans[1].setup.opponent,spoof.id);assert.equal(plans[2].setup.opponent,'')
 assert.ok(plans[2].matches.every(m=>m.fly_ids.length===1&&m.map_id==='labyrinth'))
 const edited=buildExperimentPlan({...plans[2].setup,duration:60,seedText:'7'},[subject],maps,season).plan
 assert.equal(edited.matches.length,1);assert.equal(edited.matches[0].seed,7);assert.equal(edited.matches[0].duration_seconds,60)
})
test('WT preset requires server provenance and compatible graph/model; missing WT stays explicit',()=>{
 const preset=experimentPresets[0]
 for(const flies of [[subject,spoof],[subject,{...wt,spec:{...spec,connectome_sha256:'other'}}],[subject,{...wt,spec:{...spec,model_profile:'other'}}]]){
  const next=applyExperimentPreset(preset,setup,flies)
  assert.equal(next.opponent,'');assert.equal(buildExperimentPlan(next,flies,maps,season).plan,null)
 }
 assert.equal(presetAvailable(preset,[]),false)
 assert.equal(presetAvailable(preset,[{...maps[0],metadata:{competition_eligible:false}}]),false)
})
test('every question states its evidence and limitations in both languages',()=>{
 for(const preset of experimentPresets)for(const suffix of ['question','scope']){
  const message=mapsMessages['presets.'+preset.id+'.'+suffix];assert.ok(message.en);assert.ok(message['zh-CN'])
 }
 assert.match(mapsMessages['presets.maze.scope'].en,/#82.*not validated navigation.*passes through walls.*not the preregistered/)
 assert.match(mapsMessages['presets.center.scope'].en,/No natural aggression/)
 assert.match(mapsMessages['presets.scarcity.scope'].en,/not general superiority/)
})
