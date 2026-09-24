import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createRequire} from 'node:module'
import ts from 'typescript'
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {JSDOM} from 'jsdom'

const web=new URL('../',import.meta.url).pathname
const out=fs.mkdtempSync(path.join(os.tmpdir(),'guide-content-'))
fs.writeFileSync(path.join(out,'package.json'),'{"type":"commonjs"}')
fs.symlinkSync(fs.realpathSync(path.join(web,'node_modules')),path.join(out,'node_modules'))
function compile(folder){
 for(const entry of fs.readdirSync(path.join(web,folder),{withFileTypes:true})){
  const relative=path.join(folder,entry.name)
  if(entry.isDirectory())compile(relative)
  else if(/\.tsx?$/.test(entry.name)){
   const output=ts.transpileModule(fs.readFileSync(path.join(web,relative),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}})
   const dest=path.join(out,relative.replace(/\.tsx?$/,'.js'));fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,output.outputText)
  }else if(entry.name.endsWith('.css')){const dest=path.join(out,relative);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,'')}
 }
}
compile('src/features/guide');compile('src/shared')
const require=createRequire(path.join(out,'package.json'));require.extensions['.css']=()=>{}
const {guideSections,journeySteps}=require('./src/features/guide/content.js')
const {guideMessages}=require('./src/shared/messages/guide.js')
const {catalog}=require('./src/shared/messages.js')
const {PlaygroundGuide}=require('./src/features/guide/PlaygroundGuide.js')
const {I18nProvider}=require('./src/shared/i18n.js')
test.after(()=>fs.rmSync(out,{recursive:true,force:true}))

test('every guide message has English and Chinese and is available in the catalog',()=>{
 assert.ok(Object.keys(guideMessages).length>0)
 for(const [key,message]of Object.entries(guideMessages)){
  assert.deepEqual(Object.keys(message).sort(),['en','zh-CN'])
  for(const locale of ['en','zh-CN']){
   assert.ok(message[locale].trim(),`${key} missing ${locale}`)
   assert.equal(catalog[key][locale],message[locale])
  }
 }
 const keys=[...guideSections.flatMap(s=>[s.title,s.summary,...s.details,...(s.links||[]).map(l=>l.label)]),...journeySteps.flatMap(s=>[s.title,s.summary,s.detail,...(s.label?[s.label]:[])])]
 for(const key of keys)assert.ok(guideMessages[key],`Untranslated content key: ${key}`)
})

test('onboarding covers the requested topics and the six journey steps in order',()=>{
 assert.deepEqual(guideSections.map(s=>s.id),['basis','value','meaning','data','journey'])
 assert.deepEqual(journeySteps.map(s=>s.id),['clone','edit','save','compare','evolve','compete'])
 for(const section of guideSections)assert.ok(section.details.length>0)
 // Saving is an explicit editor action, never a hidden side effect of guide navigation.
 assert.equal(journeySteps.find(s=>s.id==='save').action,undefined)
 assert.deepEqual(journeySteps.filter(s=>s.action).map(s=>s.action),['clone','design','compare','train','compete'])
})

test('source counts agree with README and prospective data use stays qualified in both languages',()=>{
 const readme=fs.readFileSync(new URL('../../README.md',import.meta.url),'utf8')
 for(const count of ['165,122','25,563,197','124,025,046']){
  assert.ok(readme.includes(count))
  for(const locale of ['en','zh-CN'])assert.ok(guideMessages['guide.basis.anatomy'][locale].includes(count))
 }
 assert.match(guideMessages['guide.data.summary'].en,/Potential uses, not established results/)
 assert.match(guideMessages['guide.data.summary']['zh-CN'],/潜在用途，而非已确立的成果/)
 assert.match(guideMessages['guide.basis.limits'].en,/no biological retina or online plasticity/)
 assert.match(guideMessages['guide.basis.limits']['zh-CN'],/尚无生物视网膜或在线可塑性/)
})

for(const locale of ['en','zh-CN'])test(`guide renders ordered summaries, working disclosure and navigation in ${locale}`,async()=>{
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://arena.example/'})
 const names=['window','document','navigator','localStorage','matchMedia','IS_REACT_ACT_ENVIRONMENT','fetch']
 const originals=Object.fromEntries(names.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const key of ['window','document','navigator','localStorage'])Object.defineProperty(globalThis,key,{configurable:true,value:dom.window[key]})
 globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
 globalThis.IS_REACT_ACT_ENVIRONMENT=true
 globalThis.fetch=()=>{throw Error('Guide must not launch work')}
 localStorage.setItem('flyarena.locale',locale)
 const root=createRoot(document.getElementById('root')),calls=[]
 const props={canCompare:true,onCompare:()=>calls.push('compare'),canCloneWT:false,hasSavedDesign:true,onCloneWT:()=>calls.push('clone'),onDesign:()=>calls.push('design'),onArena:()=>calls.push('arena'),onTrain:()=>calls.push('train'),onAI:()=>calls.push('ai')}
 try{
  await act(async()=>root.render(React.createElement(I18nProvider,null,React.createElement(PlaygroundGuide,props))))
  const library=document.querySelector('.playground-guide__library')
  assert.equal(library.open,false)
  await act(async()=>library.querySelector('summary').click())
  assert.equal(library.open,true)
  assert.ok(library.textContent.includes(guideMessages['guide.workspaces'][locale]))
  assert.deepEqual([...document.querySelectorAll('[data-guide-section]')].map(el=>el.dataset.guideSection),guideSections.map(s=>s.id))
  assert.deepEqual([...document.querySelectorAll('[data-guide-step]')].map(el=>el.dataset.guideStep),journeySteps.map(s=>s.id))
  for(const section of guideSections){
   const el=document.querySelector(`[data-guide-section="${section.id}"]`)
   assert.equal(el.querySelector('h3').textContent,guideMessages[section.title][locale])
   assert.equal(el.querySelector('.playground-guide__details>p').textContent,guideMessages[section.summary][locale])
   const details=el.querySelector('details')
   assert.equal(details.open,false)
   await act(async()=>details.querySelector('summary').click())
   assert.equal(details.open,true)
   for(const key of section.details)assert.ok(details.textContent.includes(guideMessages[key][locale]))
  }
  const clone=document.querySelector('[data-guide-step="clone"] button');assert.equal(clone.disabled,true)
  await act(async()=>clone.click());assert.deepEqual(calls,[])
  for(const step of ['edit','compare','evolve','compete'])await act(async()=>document.querySelector(`[data-guide-step="${step}"] button`).click())
  assert.deepEqual(calls,['design','compare','train','arena'])
  assert.equal(document.querySelector('[data-guide-step="edit"] button').textContent,guideMessages['guide.action.edit'][locale])
  assert.doesNotMatch(document.body.textContent,/guide\.[a-z]/)
 }finally{
  await act(async()=>root.unmount());dom.window.close()
  for(const [key,descriptor]of Object.entries(originals)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key]}
 }
})
