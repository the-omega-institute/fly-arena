/* Execute actual generated script; minimal DOM contract validation, not browser QA. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'var/presentation-correction-v8/viewer-r3.html'), 'utf8');
const old = fs.readFileSync(path.join(root, 'var/contact-v8/viewer-r2.html'), 'utf8');
const extract = h => h.match(/<script>([\s\S]*?)<\/script>/)[1];
const payload = h => extract(h).split('const data=')[1].split(';\nconst legs=')[0];
assert.equal(payload(html), payload(old));
const nodes = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], {value:'', innerHTML:'', textContent:''}]));
const options = {};
for (const m of html.matchAll(/<select id="([^"]+)">([\s\S]*?)<\/select>/g)) {
  options[m[1]] = [...m[2].matchAll(/<option(?: value="([^"]*)")?>([^<]*)<\/option>/g)].map(o=>o[1]??o[2]);
  nodes[m[1]].value = options[m[1]][0];
}
const sandbox = {document:{getElementById:id=>{assert.ok(nodes[id],id);return nodes[id];}}, console};
vm.createContext(sandbox);
vm.runInContext(extract(html), sandbox);
// Wrap the generated draw function, recording series and its actual SVG result.
vm.runInContext(`globalThis.captures=[]; const originalDraw=draw;
draw=function(title,unit,series){const svg=originalDraw(title,unit,series);captures.push({title,unit,series,svg});return svg;};
globalThis.scientificData=data;globalThis.actualHeldInput=heldInput;`, sandbox);
const data = sandbox.scientificData;
const before = JSON.stringify(data);
const legs = ['LF','LM','LH','RF','RM','RH'];
const fields = ['q','mn','current','afferent_spikes','applied_command','motor_spikes'];
let selectors = 0, seriesChecked = 0, intervalsChecked = 0;
const neutralPhenotypes = {};
for (const leg of options.leg) for (const state of options.state)
for (const context of options.context) for (const channel of options.channel)
for (const contrast of options.contrast) {
  for (const [id,value] of Object.entries({leg,state,context,channel,contrast})) nodes[id].value=value;
  sandbox.captures.length=0;
  // Exercise the actual context event handler, not a duplicate renderer.
  nodes.context.onchange();
  selectors++;
  assert.equal(sandbox.captures.length,7);
  assert.ok(!/NaN|Infinity|undefined/.test(nodes.plots.innerHTML));
  const ch=legs.indexOf(channel), [ac,bc]=contrast.split('|');
  const roles=data.subjects.filter(s=>context==='neutral'||s.role==='wildtype');
  for (let fieldIndex=0;fieldIndex<fields.length;fieldIndex++) {
    const key=fields[fieldIndex], cap=sandbox.captures[fieldIndex];
    assert.equal(cap.series.length,roles.length);
    cap.series.forEach((series,j)=>{
      const prefix=`${roles[j].role}-${leg}-${state}-${context}-`;
      const a=data.records[prefix+ac],b=bc?data.records[prefix+bc]:null;
      const offset=key==='current'?1:0;
      assert.equal(series.y.length,101-offset);
      for(let k=0;k<series.y.length;k++) {
        assert.equal(series.y[k],a[key][k+offset][ch]-(b?b[key][k+offset][ch]:0));
        assert.equal(series.t[k],key==='current'?a.input_time[k]:a.time[k]);
        if(key==='current') {
          assert.equal(series.end[k],a.time[k+1]);
          assert.equal(a.input_time[k],a.time[k]);
          assert.ok(Math.abs(series.end[k]-series.t[k]-.01)<1e-14);
          if(b) {assert.equal(series.t[k],b.input_time[k]);assert.equal(series.end[k],b.time[k+1]);}
          intervalsChecked++;
        }
      }
      seriesChecked++;
    });
    if(key==='current') {
      assert.equal(cap.title,'Engineered held input (voltage-equivalent)');
      assert.equal(cap.unit,'mV');
      const paths=[...cap.svg.matchAll(/<path d="([^"]+)" fill="none"/g)].map(m=>m[1]);
      assert.equal(paths.length,roles.length);
      paths.forEach((d,j)=>{
        const segments=[...d.matchAll(/M([\d.-]+),([\d.-]+)H([\d.-]+)/g)];
        assert.equal(segments.map(m=>m[0]).join(' '),d); // Only horizontal, disconnected holds.
        assert.equal(segments.length,100);
        const series=cap.series[j];
        segments.forEach((m,k)=>{
          assert.equal(Number(m[1]),Number((58+480*series.t[k]).toFixed(3)));
          assert.equal(Number(m[3]),Number((58+480*series.end[k]).toFixed(3)));
          if(k && series.y[k]===series.y[k-1])assert.equal(m[2],segments[k-1][2]);
          if(k && series.y[k]!==series.y[k-1])assert.notEqual(m[2],segments[k-1][2]);
        });
      });
    }
  }
  const expected=Object.fromEntries(Object.entries(data.verified.phenotypes).filter(([k])=>k.endsWith('-'+leg)));
  assert.ok(Object.keys(expected).length===3);
  if(context==='neutral')neutralPhenotypes[leg]=nodes.phenotypes.innerHTML;
  else {
    assert.equal(nodes.phenotypes.innerHTML,neutralPhenotypes[leg]);
    assert.match(nodes.status.textContent,/Official\/submitted OFF NOT RUN/);
    assert.equal((nodes.metrics.innerHTML.match(/NOT RUN in this context/g)||[]).length,2);
  }
}
assert.equal(selectors,576);
assert.match(html,/<h2>Neutral-only paired subject phenotypes · odor \(\.55,\.55\), both states<\/h2><p>Independent of selected plot context/);
assert.match(nodes.coverage.textContent,/Official\/submitted odor OFF NOT RUN/);
// Known causal timing, taken from the actual held series and generated SVG.
Object.assign(nodes.leg,{value:'RF'});nodes.leg.onchange();
nodes.state.value='42';nodes.context.value='neutral';nodes.contrast.value='intact|tactilezero';
sandbox.captures.length=0;nodes.context.onchange();
const cap=sandbox.captures[2],wt=cap.series[0],first=wt.y.findIndex(v=>v===48);
assert.equal(wt.t[first],2100*.0001);assert.equal(wt.end[first],2200*.0001);
const spike=sandbox.captures[3].series[0];assert.equal(spike.t[spike.y.findIndex(v=>v>0)],2200*.0001);
const firstPath=[...cap.svg.matchAll(/<path d="([^"]+)" fill="none"/g)][0][1];
const firstSegments=[...firstPath.matchAll(/M([\d.-]+),([\d.-]+)H([\d.-]+)/g)];
assert.equal(Number(firstSegments[first][1]),158.8); // x(.21)
assert.equal(Number(firstSegments[first][3]),163.6); // x(.22)
assert.notEqual(firstSegments[first][2],firstSegments[first-1][2]);
// Invalid paired clocks fail closed in the generated function.
const a=data.records['wildtype-RF-42-neutral-intact'];
const b=JSON.parse(JSON.stringify(data.records['wildtype-RF-42-neutral-tactilezero']));
b.input_time[21]+=.001;
assert.throws(()=>sandbox.actualHeldInput(a,b,0,3),/Paired clock mismatch/);
assert.equal(JSON.stringify(data),before);
for(const link of ['../contact-v8/joint-phenotype-r2.png','../contact-v8/verification.json','../contact-v8/registration.json']) {
  assert.ok(html.includes(`href="${link}"`));
  assert.ok(fs.existsSync(path.resolve(root,'var/presentation-correction-v8',link)));
}
console.log(JSON.stringify({selectors,series_checked:seriesChecked,held_intervals_checked:intervalsChecked,
  known_RF42_neutral:{held_onset_s:.21,first_differential_spike_endpoint_s:.22},
  paired_clock_mismatch_rejected:true,neutral_only_context_heading:true,
  data_unmutated:true,payload_byte_identical:true,
  payload_sha256:crypto.createHash('sha256').update(payload(html)).digest('hex'),
  browser_qa:'NOT RUN; actual generated JavaScript/SVG with minimal DOM only'},null,2));
