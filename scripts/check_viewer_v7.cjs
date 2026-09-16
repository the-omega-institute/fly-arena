// Execute this standalone viewer with a minimal DOM; this is not browser visual QA.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root='/tmp/fly-arena-embodied-v7', html=fs.readFileSync(root+'/var/embodied-v7/viewer.html','utf8');
const payload=html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const js=html.match(/<\/script><script>([\s\S]*?)<\/script>/)[1];
class Element{constructor(){this.children=[];this.textContent='';this.value='';this.attrs={}}appendChild(v){this.children.push(v);return v}insertRow(){return this.appendChild(new Element())}insertCell(){return this.appendChild(new Element())}add(v){this.children.push(v);if(this.children.length===1)this.value=v.value}replaceChildren(){this.children=[]}setAttribute(k,v){assert(!/NaN|Infinity|undefined/.test(String(v)));this.attrs[k]=v}}
const els={}; for(const x of html.matchAll(/id="([^"]+)"/g))els[x[1]]=new Element();els.data.textContent=payload;
const context={document:{getElementById:id=>{assert(els[id],id);return els[id]},createElement:()=>new Element(),createElementNS:()=>new Element()},Option:function(text,value){return {text,value}},console};vm.createContext(context);vm.runInContext(js,context);
const data=JSON.parse(payload);let count=0;for(const k of Object.keys(data.records))for(let i=0;i<6;i++){els.trial.value=k;els.leg.value=String(i);els.trial.onchange();assert(els.angle.children.some(x=>x.attrs.points));assert(els.neural.children.some(x=>x.attrs.points));count++}
assert(!/https?:\/\//.test(html.replace('http://www.w3.org/2000/svg','')));
const result={pass:true,selections:count,records:Object.keys(data.records).length,svg_panels:6,external_dependencies:0,browser_visual_QA:'unavailable: browser tool reports unsupported Codex auth method apikey',scope:'JS execution, selectors and finite SVG coordinates checked in minimal DOM; browser layout/render not verified'};
fs.writeFileSync(root+'/var/embodied-v7/viewer-check.json',JSON.stringify(result,null,2)+'\n');console.log(result);
