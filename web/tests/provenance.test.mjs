import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'

// Compile the real components with the declared TypeScript dependency. React SSR
// renders their actual markup; no DOM, component mocks, browser or service is used.
const web = new URL('../', import.meta.url).pathname
const output = fs.mkdtempSync(path.join(process.env.FLY_TEST_SCRATCH || os.tmpdir(), 'provenance-render-'))
fs.writeFileSync(path.join(output, 'package.json'), '{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web, 'node_modules')), path.join(output, 'node_modules'))
function compile(folder) {
  for (const entry of fs.readdirSync(path.join(web, folder), {withFileTypes:true})) {
    const relative = path.join(folder, entry.name)
    if (entry.isDirectory()) compile(relative)
    else if (/\.tsx?$/.test(entry.name)) {
      const result = ts.transpileModule(fs.readFileSync(path.join(web, relative), 'utf8'), {
        compilerOptions:{target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX, esModuleInterop:true},
      })
      const dest = path.join(output, relative.replace(/\.tsx?$/, '.js'))
      fs.mkdirSync(path.dirname(dest), {recursive:true})
      fs.writeFileSync(dest, result.outputText)
    }
  }
}
compile('src')
const require = createRequire(path.join(output, 'package.json'))
const {SavedFlyCard} = require('./src/features/design/SavedFlyCard.js')
const {ArenaFeature} = require('./src/features/arena/ArenaFeature.js')
const {ArenaWorldLabel} = require('./src/features/arena/ArenaWorldLabel.js')
const {PhenotypeLab} = require('./src/features/phenotype/PhenotypeLab.js')
const {FrozenSubjects} = require('./src/features/phenotype/FrozenSubjects.js')
const {I18nProvider} = require('./src/shared/i18n.js')
const {TrainingComparison} = require('./src/features/training/TrainingComparison.js')
const {ConditionResults} = require('./src/features/training/ConditionResults.js')
test.after(() => fs.rmSync(output, {recursive:true, force:true}))
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))
const noop = () => {}
test('brain overview distinguishes recorded silence, missing activity and design mutations',()=>{
  const {BrainActivityOverview}=require('./src/features/arena/BrainActivityOverview.js')
  const circuits=['olfactory','visual','motor'].map(id=>({id,label:id,name:id,color:'#98dbc0',neuron_count:100,edge_count:10}))
  const props={circuits,activity:{olfactory:0,visual:4},scale:10,time:1.25,
    mutations:[{selector:'visual',scale:1.1}],onOpen:noop}
  const html=render(BrainActivityOverview,props)
  assert.match(html,/aria-label="olfactory: 0.00 Hz"/)
  assert.match(html,/aria-label="motor: Not recorded"/)
  assert.match(html,/aria-label="visual: 4.00 Hz · ×1.10"/)
  assert.match(html,/data-activity-glow="0.4"/)
  assert.match(textOnly(html),/1.25 s/)
  assert.match(textOnly(html),/Positions are schematic/)
  assert.equal((html.match(/role="button"/g)||[]).length,3)
  assert.equal((html.match(/tabindex="0"/g)||[]).length,3)
  const later=render(BrainActivityOverview,{...props,time:2.5,activity:{olfactory:0,visual:8}})
  assert.match(later,/data-activity-glow="0.8"/)
  assert.match(textOnly(later),/0–10.00 Hz/)
  assert.match(later,/aria-label="motor: Not recorded"/)
})

test('brain overview uses unique gradient identities when participants are compared',()=>{
  const {BrainActivityOverview}=require('./src/features/arena/BrainActivityOverview.js')
  const props={circuits:[{id:'olfactory',label:'Olfactory',color:'#98dbc0',neuron_count:100}],activity:{olfactory:1},scale:2,onOpen:noop}
  const html=renderToStaticMarkup(React.createElement('div',null,
    React.createElement(BrainActivityOverview,props),React.createElement(BrainActivityOverview,props)))
  const ids=[...html.matchAll(/<radialGradient id="([^"]+)"/g)].map(match=>match[1])
  assert.equal(ids.length,2)
  assert.equal(new Set(ids).size,2)
})
test('actual training comparison shows negative results, condition differences and incomplete status',()=>{
  const run={id:'first',status:'stopped',evaluation_context:'runtime-a',spec:{name:'Run A',strategy:'evolution',founder_id:'ancestor',opponent_id:'opponent',map_id:'ring',mode:'contest',duration_seconds:2,seed:42,bridge_profile:'legacy-v1',population:2,generations:2,max_evaluations:8,circuits:['olfactory'],mutation_strength:.08},baseline_fitness:-2,evaluations_started:2,evaluations_completed:2,evaluations_total:8,members:[{generation:0,slot:0,fitness:-2},{generation:0,slot:1,fitness:null}]};
  const second={...run,id:'second',spec:{...run.spec,name:'Run B',seed:7}};
  const html=render(TrainingComparison,{runs:[run,second],maps:[],flies:[],onOpen:noop});
  assert.match(textOnly(html),/Different evaluation conditions:.*Seed/);
  assert.match(textOnly(html),/Incomplete session/);
  assert.match(textOnly(html),/-2\.000/);
  assert.match(html,/stroke-dasharray|fill="var\(--paper\)"/);
  assert.doesNotMatch(textOnly(html),/Same recorded evaluation conditions/);
  assert.match(textOnly(html),/Time budget is completed evaluations/);
});
test('actual comparison safely handles an account without sessions',()=>{
  assert.match(textOnly(render(TrainingComparison,{runs:[],maps:[],flies:[],onOpen:noop})),/Your training sessions will appear here/);
});
test('condition cards keep zero scores, missing means and each recorded replay distinct',()=>{
 const results=[{condition:{map_id:'orchard',seed:42},fitness:0,evaluations_completed:2,evaluations_total:2,matches:[{id:'a',status:'verified',progress:1},{id:'b',status:'verified',progress:1}]},{condition:{map_id:'scarcity',seed:7},fitness:null,evaluations_completed:1,evaluations_total:2,matches:[{id:'c',status:'verified',progress:1},{id:'d',status:'running',progress:.5}]}];
 const html=render(ConditionResults,{results,maps:[],onReplay:noop});
 assert.match(textOnly(html),/Condition 1 · orchard0\.000/);
 assert.match(textOnly(html),/Condition 2 · scarcity—/);
 assert.match(textOnly(html),/Seed 7 · 1\/2 evaluated · Awaiting complete condition/);
 assert.equal((html.match(/<button/g)||[]).length,4);
 assert.equal((html.match(/disabled=""/g)||[]).length,1);
 assert.match(textOnly(html),/Behavior and neural replay 2 · 50%/);
});
const fly = (id, patch={}) => ({id, owner:'owner', designer:'Arena Lab', name:'Wild Type / 原型', color:'mint',
  artifact_id:'same-artifact', spec:{parent_id:null}, report:{}, reference_kind:null, submission_channel:null, release_id:null, ...patch})
const legacy = fly('legacy01-full-id')
const wt = fly('trusted1-full-id', {reference_kind:'wildtype', submission_channel:'seed', release_id:'release-1'})
const official = fly('official-full-id', {reference_kind:'official', submission_channel:'seed', release_id:'release-1'})
const flies = [legacy, wt, official, fly('clone001-full-id', {reference_kind:'user', submission_channel:'web'}),
  fly('agent001-full-id', {reference_kind:'ai', submission_channel:'api'})]
function arena(identity, extra={}) {
  return render(ArenaFeature, {replayStatus:'idle', replayError:'', bridgeProfile:'', scene:null, focused:'', preview:null,
    selected:legacy.id, identity, flies, frames:[], play:false, playtime:0, playbackSpeed:1, season:null, matches:[], maps:[],
    mapId:'orchard', mode:'contest', opponent:wt.id, duration:5, seed:42, busy:'', ...extra})
}
const options = html => [...html.matchAll(/<option\b[^>]*value="([^"]+)"[^>]*>(.*?)<\/option>/g)]
const textOnly = html => html.replace(/<[^>]*>/g, '')

test('actual Studio cards distinguish identical names/artifacts and ownership without invented authorship', () => {
  for (const viewer of [undefined, 'owner', 'other']) {
    const html = render(SavedFlyCard, {fly:legacy, viewer, selected:true, onClone:noop})
    assert.match(textOnly(html), /Wild Type \/ 原型/)
    assert.match(textOnly(html), /Provenance not recorded/)
    assert.match(textOnly(html), viewer==='owner' ? /Your saved design/ : /Saved design/)
    assert.match(html, /title="Wild Type \/ 原型 · legacy01-full-id"/)
    assert.match(textOnly(html), /legacy01/)
    assert.doesNotMatch(textOnly(html), /Trusted|Arena Lab|web|AI authored|Human/)
  }
  for (const [record, label] of [[wt, 'Trusted Wild Type'], [official, 'Trusted official release']]) {
    const html = render(SavedFlyCard, {fly:record, viewer:'owner', selected:false, onClone:noop})
    assert.ok(textOnly(html).includes(label))
    assert.doesNotMatch(textOnly(html), /Your saved design|Provenance not recorded/)
  }
  for (const record of flies.slice(3)) {
    const html = render(SavedFlyCard, {fly:record, viewer:'owner', selected:false, onClone:noop})
    assert.match(textOnly(html), /Your saved design/)
    assert.doesNotMatch(textOnly(html), /Trusted|Provenance not recorded|AI|Human/)
  }
})

test('both actual Arena selectors retain saved IDs and show distinct visible identities for all viewers', () => {
  for (const identity of [null, {id:'owner'}, {id:'other'}]) {
    const html = arena(identity)
    for (const record of flies) {
      const choices = options(html).filter(o => o[1]===record.id)
      assert.equal(choices.length, 2)
      for (const choice of choices) {
        assert.ok(choice[2].includes(record.name))
        assert.ok(choice[2].includes(record.id.slice(0,8)))
        if (record===legacy) {
          assert.match(choice[2], /Provenance not recorded/)
          assert.match(choice[2], identity?.id==='owner' ? /Your saved design/ : /Saved design/)
        }
        if (record===wt) assert.match(choice[2], /Trusted Wild Type/)
        if (record===official) assert.match(choice[2], /Trusted official release/)
      }
      assert.ok(html.includes(`title="${record.name} · ${record.id}"`))
    }
  }
})

test('actual replay score and world labels keep identity and treat a missing record as participant', () => {
  const absent = fly('missing1-full-id')
  const participants = [legacy, wt, official, absent]
  const scene = {flies:participants, body:{meshes:{}, geoms:[]}, size:80, food:[], obstacles:[]}
  const html = arena({id:'owner'}, {scene, frame:{positions:[], poses:[], time:0, tick:0, scores:[1,2,3,4]}, replayStatus:'ready'})
  const scores = html.match(/<div class="score-overlay">([\s\S]*?)<div class="playback">/)[1]
  assert.match(textOnly(scores), /Your saved design · Provenance not recorded · legacy01/)
  assert.match(textOnly(scores), /Trusted Wild Type · trusted1/)
  assert.match(textOnly(scores), /Trusted official release · official/)
  assert.match(textOnly(scores), /Participant · Provenance not recorded · missing1/)
  const world = render(ArenaWorldLabel, {fly:absent, slot:3, selected:true})
  assert.match(textOnly(world), /Slot 4 · Wild Type \/ 原型/)
  assert.match(textOnly(world), /Participant · Provenance not recorded · missing1/)
  assert.match(world, /missing1-full-id/)
  assert.doesNotMatch(textOnly(world), /Trusted|Your saved design/)
})

test('actual Lab selector retains an owned legacy design and excludes nonowners', () => {
  for (const identity of [null, {id:'owner'}, {id:'other'}]) {
    const html = render(PhenotypeLab, {flies, identity, selected:legacy.id, experimentId:'', onExperiment:noop, onLogin:noop})
    const choices = options(html).filter(o => flies.some(f => f.id===o[1]))
    assert.equal(choices.length, identity?.id==='owner' ? flies.length : 0)
    if (choices.length) assert.match(choices.find(o=>o[1]===legacy.id)[2], /Your saved design · Provenance not recorded · legacy01/)
  }
})

test('actual Frozen cards distinguish absent fields, explicit nulls and recorded metadata without live fallback', () => {
  const base = {role:'design', fly_id:legacy.id, artifact_id:legacy.artifact_id, name:legacy.name}
  const live = fly(legacy.id, {reference_kind:'ai', submission_channel:'api', release_id:'LIVE-RELEASE', spec:{parent_id:'LIVE-PARENT'}})
  const props = {owner:'owner', viewer:'owner', flies:[live]}
  const card = subjects => render(FrozenSubjects, {...props, subjects}).match(/<article class="panel subject-card design">([\s\S]*?)<\/article>/)[1]
  const missing = card([base])
  assert.equal((missing.match(/Not recorded in this experiment/g)||[]).length, 4)
  const explicit = card([{...base, parent_id:null, reference_kind:null, submission_channel:null, release_id:null}])
  assert.equal((explicit.match(/<dd>Unknown<\/dd>/g)||[]).length, 2)
  assert.equal((explicit.match(/<dd>Not supplied<\/dd>/g)||[]).length, 2)
  assert.doesNotMatch(explicit, /Not recorded in this experiment/)
  for (const html of [missing, explicit]) {
    assert.match(html, /Provenance not recorded/)
    assert.doesNotMatch(html, /LIVE-|<dd>api<\/dd>|<dd>ai<\/dd>/)
  }
  const recorded = card([{...base, parent_id:'frozen-parent', reference_kind:'user', submission_channel:'web', release_id:'frozen-release'}])
  for (const value of ['frozen-parent', 'user', 'web', 'frozen-release']) assert.ok(recorded.includes(`<dd>${value}</dd>`))
  assert.doesNotMatch(recorded, /Not recorded|Provenance not recorded|LIVE-/)
})

test('actual translated cards and frozen details render Chinese via the existing catalog', () => {
  const saved = Object.fromEntries(['navigator','localStorage','matchMedia'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
  // Preference inputs only; SSR creates no document or DOM.
  Object.defineProperty(globalThis, 'navigator', {configurable:true, value:{language:'zh-CN'}})
  globalThis.localStorage = {getItem:()=>null}
  globalThis.matchMedia = ()=>({matches:false})
  try {
    const html = renderToStaticMarkup(React.createElement(I18nProvider, null,
      React.createElement(SavedFlyCard, {fly:legacy, viewer:'owner', selected:false, onClone:noop}),
      React.createElement(FrozenSubjects, {subjects:[{role:'design', fly_id:legacy.id, name:legacy.name, artifact_id:legacy.artifact_id, reference_kind:null}]})))
    for (const phrase of ['你保存的设计','来源未记录','本实验未记录','未知','参考类型']) assert.ok(html.includes(phrase))
  } finally {
    for (const [key, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})

test('observations follow the selected second fly and show its real parent and zero values', () => {
  const {MatchObservations}=require('./src/features/arena/MatchObservations.js')
  const parent=fly('parent01',{name:'Ancestor'})
  const child=fly('child001',{name:'Descendant',spec:{parent_id:parent.id},report:{budget_used:12,budget_limit:100}})
  const frame={time:.1,tick:1000,poses:[],positions:[],scores:[99,0],energy:[88,0],drives:[[1,1],[0,0]],traces:[{olfactory:123},{olfactory:0}]}
  const html=render(MatchObservations,{scene:{flies:[parent,child]},frame,frames:[frame],flies:[parent,child],selectedId:child.id,
    season:{connectome:{circuits:[{id:'olfactory',label:'olfactory',color:'#abc'}]}}})
  const text=textOnly(html)
  assert.match(text,/Ancestor · parent01/)
  assert.match(text,/Food collected0.00/)
  assert.match(text,/Energy reserve0.0/)
  assert.match(text,/Left \/ right motor drive0.00 \/ 0.00/)
  assert.doesNotMatch(text,/olfactory123\.0 Hz|Food collected99\.00|Energy reserve88\.0/)
  assert.match(html,/aria-label="olfactory: 0.00 Hz"/)
  assert.match(text,/Activity brightness 0–123.00 Hz/) // Shared scale includes both subjects, not their displayed values.
  assert.match(text,/Compare participants/)
  assert.doesNotMatch(html,/NaN|Infinity/)
  assert.match(html,/aria-pressed="true"[^>]*>.*Slot 2 · Descendant/)
})

test('portable replay shows the recorded design without a library and prefers it over a live copy', () => {
  const {MatchObservations}=require('./src/features/arena/MatchObservations.js')
  const recorded={id:'portable',name:'Nectar',color:'mint',artifact_id:'frozen-artifact',
    spec:{parent_id:'parent-recorded',connectome_sha256:'frozen-connectome',model_profile:'malecns-lif-cpu-v1',
      weight_mutations:[{selector:'olfactory',scale:1.1}],edge_deltas:[],neuron_parameters:{tau_scale:1.05,threshold_shift_mv:0.1}},
    report:{budget_used:12,budget_limit:100}}
  const live=fly(recorded.id,{spec:{...recorded.spec,weight_mutations:[{selector:'olfactory',scale:1.9}]}})
  for(const library of [[],[live]]){
    const html=render(MatchObservations,{scene:{flies:[recorded]},frames:[],flies:library,selectedId:recorded.id,
      season:null,match:{id:'match',participants:[recorded]}})
    const text=textOnly(html)
    assert.match(text,/olfactory ×1.100/)
    assert.match(text,/τ ×1.050/)
    assert.match(text,/12.0 \/ 100/)
    assert.match(text,/parent-r/)
    assert.doesNotMatch(text,/×1.900|No saved FlySpec|NaN/)
  }
})
