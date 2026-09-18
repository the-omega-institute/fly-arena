import test from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import fs from 'node:fs'
async function moduleAt(path){const source=fs.readFileSync(new URL(path,import.meta.url),'utf8');const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}});return import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'))}
const {parseSeeds,alignment,sampleAt,metricUnit,validateHorizon,designRoleLabel,plotTransform}=await moduleAt('../src/shared/research.ts');
const {assertSpec,composeSpec}=await moduleAt('../src/features/design/spec.ts');
const {catalog}=await moduleAt('../src/shared/messages.ts');
const subjects=['wildtype','official','design'].map((role,i)=>({role,fly_id:`f${i}`,artifact_id:`a${i}`}));
const reports=subjects.map(s=>({...s,status:'complete',condition_key:'same-condition',receipt_sha256:'receipt',duration_seconds:3,trajectory:[{time:0,x:0,y:0,yaw:0},{time:3,x:6,y:3,yaw:0}]}));
test('seed admission matches strict API limits: at most eight distinct nonnegative int32 seeds',()=>{assert.deepEqual(parseSeeds('0, 42 2147483647'),[0,42,2147483647]);assert.equal(parseSeeds('1,2,3,4,5,6,7,8').length,8);for(const v of ['', '-1','1.2','2147483648','42,42','1,2,3,4,5,6,7,8,9'])assert.throws(()=>parseSeeds(v))});
test('horizon enforces integer seconds from 1 to 30',()=>{for(const v of [1,30])assert.equal(validateHorizon(v),v);for(const v of [0,31,1.5,NaN,Infinity])assert.throws(()=>validateHorizon(v))});
test('ownership labels require a known authenticated viewer matching experiment owner',()=>{assert.equal(designRoleLabel('a','a'),'Your design');for(const pair of [['a','b'],['a',undefined],[undefined,undefined]])assert.equal(designRoleLabel(...pair),'Submitted design')});
test('physical plot uses equal x/y scale and includes all recorded points outside scene boundaries',()=>{const p=plotTransform([{x:120,y:-53}],{size:80,food:[{position:[7,5],id:'food',initial:10}],obstacles:[]});assert.ok(Math.abs((p.sx(10)-p.sx(0))-(p.sy(0)-p.sy(10)))<1e-10);assert.ok(p.x1>=120&&p.y0<=-53);assert.ok(p.sx(120)<=670&&p.sy(-53)<=395)});
const {readRoute,routeHash}=await moduleAt('../src/shared/navigation.ts');
test('deep links round trip experiment/match and preserve scientific IDs',()=>{for(const tab of ['design','arena','lab','code']){const r=readRoute(routeHash(tab,'trial + 1','match&2'));assert.equal(r.tab,tab);if(tab==='lab')assert.equal(r.experiment,'trial + 1');if(tab==='arena')assert.equal(r.match,'match&2')}assert.equal(readRoute('#experiment=historical').tab,'lab');assert.equal(readRoute('#tab=invalid').tab,'design')});
const {defaultMatchProfile,recordedMatchProfile}=await moduleAt('../src/types.ts');
test('v2 defaults only when ready; historical absence stays legacy regardless of current default',()=>{const profiles=[{id:'legacy-v1',ready:true},{id:'sensorimotor-research-v2',ready:true}];assert.equal(defaultMatchProfile({match_profiles:profiles,default_bridge_profile:'legacy-v1'}),'sensorimotor-research-v2');assert.equal(defaultMatchProfile({match_profiles:profiles.map(p=>({...p,ready:p.id==='legacy-v1'})),default_bridge_profile:'legacy-v1'}),'legacy-v1');assert.equal(defaultMatchProfile({}),'');assert.equal(recordedMatchProfile({request:{}}),'legacy-v1');assert.equal(recordedMatchProfile({request:{bridge_profile:'sensorimotor-research-v2'}}),'sensorimotor-research-v2')});
test('alignment requires frozen artifact identity and every subject',()=>{assert.equal(alignment(reports,subjects),'matched');assert.equal(alignment(reports.slice(1),subjects),'pending');assert.equal(alignment(reports.map((r,i)=>i? r:{...r,artifact_id:'other'}),subjects),'pending')});
test('alignment fails closed for absent receipts, partial runs, grids and conditions',()=>{for(const [patch,expected] of [[{receipt_sha256:''},'pending'],[{status:'failed'},'pending'],[{condition_key:'other'},'mismatch'],[{duration_seconds:4},'mismatch'],[{trajectory:[{time:1,x:0,y:0}]},'mismatch']])assert.equal(alignment(reports.map((r,i)=>i?r:{...r,...patch}),subjects),expected)});
test('scrubber interpolates recorded positions without extrapolating missing time',()=>{assert.equal(sampleAt([],1),null);assert.equal(sampleAt(reports[0].trajectory,-1),null);assert.equal(sampleAt(reports[0].trajectory,4),null);assert.deepEqual(sampleAt(reports[0].trajectory,1.5),{time:1.5,x:3,y:1.5,yaw:0})});
test('metric units distinguish latency duration from censor flags',()=>{assert.equal(metricUnit('food_latency_s'),'s');assert.equal(metricUnit('food_latency_censored'),'—');assert.equal(metricUnit('mean_speed_mm_s'),'mm/s');assert.equal(metricUnit('path_length_mm'),'mm');assert.equal(metricUnit('unknown_metric'),'—')});
test('editing retains advanced interventions, legacy extras, canonical IDs and nested parameters',()=>{const base={schema_version:'flyspec/v1',name:'original',weight_mutations:[],edge_deltas:[{edge:7,log_delta:0.2}],neuron_parameters:{tau_scale:1,threshold_shift_mv:0,future_parameter:5},interventions:[{selector:{pre:{ids:['720575940123456789']}},scale:1.2}],future_field:{preserve:true}};assertSpec(base);const edited=composeSpec(base,{name:'edited',neuron_parameters:{tau_scale:1.1,threshold_shift_mv:0}});assert.deepEqual(edited.interventions,base.interventions);assert.deepEqual(edited.edge_deltas,base.edge_deltas);assert.deepEqual(edited.future_field,{preserve:true});assert.equal(edited.neuron_parameters.future_parameter,5);assert.equal(edited.neuron_parameters.tau_scale,1.1)});
test('old specs without interventions remain supported; malformed imports rejected',()=>{assert.doesNotThrow(()=>assertSpec({schema_version:'flyspec/v1',name:'old',weight_mutations:[],neuron_parameters:{}}));assert.throws(()=>assertSpec({schema_version:'bad'}));assert.throws(()=>assertSpec({schema_version:'flyspec/v1',name:'bad',weight_mutations:[],neuron_parameters:{},interventions:[{scale:1}]}))});
test('all static translated call keys have complete en and zh-CN catalogs',()=>{let keys=[];function scan(path){for(const f of fs.readdirSync(path,{withFileTypes:true})){const full=path+'/'+f.name;if(f.isDirectory())scan(full);else if(/\.tsx$/.test(f.name)){const sf=ts.createSourceFile(full,fs.readFileSync(full,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);function visit(n){if(ts.isCallExpression(n)&&n.expression.getText(sf)==='t'&&ts.isStringLiteral(n.arguments[0]))keys.push(n.arguments[0].text);ts.forEachChild(n,visit)}visit(sf)}}}scan(new URL('../src',import.meta.url).pathname);for(const key of keys){assert.ok(catalog[key]?.en,`Missing en: ${key}`);assert.ok(catalog[key]?.['zh-CN'],`Missing zh: ${key}`)}assert.ok(Object.keys(catalog).length>300)});
test('API retains credential cookies, Bearer auth, CSRF and expiration signal',async()=>{const original=globalThis.fetch;let options;globalThis.fetch=async(url,opts)=>{options=opts;return {ok:true,json:async()=>({ok:true})}};const {api,setCsrfToken}=await moduleAt('../src/api.ts');setCsrfToken('csrf-test');await api('/test',{method:'POST'});assert.equal(options.credentials,'same-origin');assert.equal(options.headers['X-Arena-CSRF'],'csrf-test');await api('/test',{}, {id:'test',name:'test',token:'bearer-test'});assert.equal(options.headers.Authorization,'Bearer bearer-test');assert.equal(options.headers['X-Arena-CSRF'],undefined);let event;globalThis.window={dispatchEvent:e=>event=e.type};globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({detail:'Expired'})});await assert.rejects(()=>api('/test'),/Expired/);assert.equal(event,'arena:session-expired');globalThis.fetch=original;delete globalThis.window});

const {planProblem}=await moduleAt('../src/features/training/plan.ts');
const trainingPlan={population:2,generations:2,budget:4,duration:1,seed:42,circuits:['olfactory'],name:'First generations',mode:'forage',founder:'fly',opponent:''};
test('training plan admits finite solo work and charges both mirrored positions',()=>{
 assert.equal(planProblem(trainingPlan),null);
 assert.ok(planProblem({...trainingPlan,mode:'contest',opponent:'rival'}));
 assert.equal(planProblem({...trainingPlan,mode:'contest',opponent:'rival',budget:8}),null);
 for(const edit of [{population:0},{population:2.5},{generations:9},{budget:97},{duration:NaN},{seed:Infinity},{seed:-1},{circuits:[]},{name:'  '},{founder:''},{mode:'contest'}])assert.ok(planProblem({...trainingPlan,...edit}),JSON.stringify(edit));
});
test('training navigation can be bookmarked without becoming a lab or match route',()=>{
 assert.equal(readRoute(routeHash('train')).tab,'train');
});
const {memberRole,trainingFocus,trainingHash}=await moduleAt('../src/features/training/plan.ts');
test('custom optimizer plans skip built-in circuit controls but keep numeric and match budgets',()=>{
 assert.equal(planProblem({...trainingPlan,strategy:'external',circuits:[]}),null);
 assert.ok(planProblem({...trainingPlan,strategy:'external',circuits:[],budget:3}));
 assert.equal(memberRole('external',0,0),'Baseline');
 assert.equal(memberRole('external',1,0),'Optimizer proposal');
 assert.equal(memberRole('external',0,1),'Optimizer proposal');
 assert.equal(memberRole('evolution',1,0),'Retained parent');
});
test('training bookmarks round-trip and reject malformed session IDs',()=>{
 const id='a'.repeat(32);assert.equal(trainingFocus(trainingHash(id)),id);
 assert.equal(readRoute(trainingHash(id)).tab,'train');
 assert.equal(trainingFocus('#tab=train&training=bad'), '');
 assert.equal(trainingFocus(trainingHash('')), '');
});

const {summarizeRun,comparisonDifferences,curveScale}=await moduleAt('../src/features/training/comparison.ts');
const comparisonRun={id:'a',status:'complete',evaluation_context:'engine-a',spec:{name:'Evolution',strategy:'evolution',founder_id:'fly',opponent_id:null,map_id:'scarcity',mode:'forage',duration_seconds:2,seed:42,bridge_profile:'legacy-v1',population:2,generations:3,max_evaluations:6,circuits:['olfactory'],mutation_strength:.08},baseline_fitness:0,evaluations_started:5,evaluations_completed:4,evaluations_total:6,members:[{generation:0,slot:0,fitness:0},{generation:0,slot:1,fitness:.3},{generation:1,slot:0,fitness:.3},{generation:1,slot:1,fitness:null}]};
test('training comparison preserves incomplete generations, zero baselines and actual evaluation costs',()=>{
 const result=summarizeRun(comparisonRun);
 assert.equal(result.best,.3);assert.equal(result.gain,.3);assert.equal(result.budgetedSeconds,8);
 assert.deepEqual(result.history.map(g=>[g.best,g.complete,g.evaluated]),[[.3,true,2],[.3,false,1],[null,false,0]]);
 assert.equal(summarizeRun({...comparisonRun,baseline_fitness:null}).gain,null);
 assert.equal(summarizeRun({...comparisonRun,members:[]}).best,null);
});
test('negative contest fitness and declining generations are never clamped into success',()=>{
 const run={...comparisonRun,baseline_fitness:-1,members:[{generation:0,slot:0,fitness:-1},{generation:0,slot:1,fitness:-2},{generation:1,slot:0,fitness:-3},{generation:1,slot:1,fitness:-4}]};
 const result=summarizeRun(run);assert.equal(result.best,-1);assert.equal(result.gain,0);assert.equal(result.history[1].best,-3);
 const scale=curveScale([run]);assert.ok(scale.min< -3);assert.ok(scale.y(-3)>scale.y(-1));
 assert.ok(Number.isFinite(curveScale([{...run,members:[]}]).y(0)));
});
test('strategy comparisons distinguish seeds, maps, founders, opponents and engine versions',()=>{
 const other={...comparisonRun,id:'b',spec:{...comparisonRun.spec,strategy:'random_search'}};
 assert.deepEqual(comparisonDifferences([comparisonRun,other]),[]);
 for(const edit of [{seed:7},{map_id:'maze'},{founder_id:'other'},{duration_seconds:3},{bridge_profile:'sensorimotor-research-v2'},{mode:'contest',opponent_id:'rival'}])assert.ok(comparisonDifferences([comparisonRun,{...other,spec:{...other.spec,...edit}}]).length);
 assert.ok(comparisonDifferences([comparisonRun,{...other,evaluation_context:'engine-b'}]).includes('Evaluation version'));
 assert.ok(comparisonDifferences([comparisonRun,{...other,evaluation_context:undefined}]).includes('Evaluation version unavailable'));
});
