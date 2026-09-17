// Node/V8 transport and helper measurement, not browser visual QA or 30s physics.
// Usage: node tests/replay-cost.mjs <actual-pair-dir> <output.json>
import fs from 'node:fs'
import path from 'node:path'
import {performance} from 'node:perf_hooks'
import ts from 'typescript'
const {outputText}=ts.transpileModule(fs.readFileSync(new URL('../src/features/arena/replayFrames.ts',import.meta.url),'utf8'),
  {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}})
const {selectReplayFrames}=await import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'))
const [pair,output]=process.argv.slice(2)
if(!pair||!output) throw new Error('Actual pair directory and output JSON required')
function benchmark(text) {
  const frames=JSON.parse(text),parse=[],selection=[]
  for(let warm=0;warm<5;warm++) JSON.parse(text)
  let checksum=0
  for(let repeat=0;repeat<15;repeat++) {
    let start=performance.now()
    checksum+=JSON.parse(text).length
    parse.push(performance.now()-start)
    start=performance.now()
    for(let i=0;i<10000;i++) checksum+=selectReplayFrames(frames,frames.at(-1).time*((i*7919)%10000)/10000).alpha
    selection.push((performance.now()-start)/10000)
  }
  const median=a=>a.sort((a,b)=>a-b)[Math.floor(a.length/2)]
  return {payload_bytes:Buffer.byteLength(text),frames:frames.length,median_parse_ms:median(parse),
    median_selection_us:median(selection)*1000,parse_repetitions:15,selections_per_repetition:10000,checksum}
}
const report={scope:'Node/V8 JSON parse and timestamp helper only; no browser render or GPU timings',node:process.version,actual_1s:{},constructed_30s:{}}
for(const version of ['old','new']) {
  const text=fs.readFileSync(path.join(pair,version,'frames.json'),'utf8')
  report.actual_1s[version]=benchmark(text)
  const actual=JSON.parse(text),cadence=actual[1].tick-actual[0].tick
  // Reuse observed pose payloads, alter ONLY synthetic timestamps. Explicitly
  // a size/cost projection; it cannot predict longer-run geometry/compression.
  const projection=Array.from({length:300000/cadence+1},(_,i)=>({
    ...actual[i%(actual.length-1)],tick:i*cadence,time:i*cadence*.0001,
  }))
  report.constructed_30s[version]={label:'Synthetic repeated 1s payload, 30s timestamp grid; not simulated 30s movement',...benchmark(JSON.stringify(projection))}
}
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n')
console.log(JSON.stringify(report,null,2))
