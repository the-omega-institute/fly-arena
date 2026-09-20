export type NeuronMorphology={id:string;type:string|null;class:string|null;superclass:string|null;side:string|null;positions:number[];radii:number[];edges:number[]}
export type Morphology={schema:'connectome-morphology/v1';connectome_sha256:string;source:string;coordinate_unit_nm:number;neurons:NeuronMorphology[];missing_ids:string[]}
const cache=new Map<string,Morphology>()
export function validateMorphology(value:Morphology,expected:string):Morphology{
 if(value?.schema!=='connectome-morphology/v1'||value.connectome_sha256!==expected||value.coordinate_unit_nm!==8||!Array.isArray(value.neurons)||value.neurons.length>2048)throw Error('Morphology does not match this connectome')
 const ids=new Set<string>()
 for(const n of value.neurons){
  if(!/^\d+$/.test(n.id)||ids.has(n.id)||!Array.isArray(n.positions)||n.positions.length%3||!n.positions.every(Number.isFinite)||!Array.isArray(n.edges)||n.edges.length%2||!n.edges.every(v=>Number.isSafeInteger(v)&&v>=0&&v<n.positions.length/3))throw Error('Invalid neuron skeleton')
  ids.add(n.id)
 }
 return value
}
export async function loadMorphology(expected:string,signal:AbortSignal):Promise<Morphology>{
 const cached=cache.get(expected);if(cached)return cached
 const response=await fetch('/api/v1/connectome/morphology',{signal,credentials:'same-origin'})
 if(!response.ok)throw Error('Morphology unavailable')
 const data=validateMorphology(await response.json(),expected)
 if(signal.aborted)throw new DOMException('Aborted','AbortError')
 if(cache.size>=2)cache.delete(cache.keys().next().value!)
 cache.set(expected,data);return data
}
export function morphologyActivity(neurons:NeuronMorphology[],activity:Map<string,number>,scale:number,focus:string|null):Uint8Array{
 const bytes=new Uint8Array(neurons.length*4)
 neurons.forEach((n,i)=>{const value=activity.get(n.id),recorded=value!==undefined&&Number.isFinite(value)
  bytes[4*i]=recorded?Math.round(255*Math.log1p(Math.max(0,value))/Math.log1p(Math.max(1,scale,Math.max(0,value)))):0
  bytes[4*i+1]=recorded?255:0;bytes[4*i+2]=n.id===focus?255:0;bytes[4*i+3]=255
 });return bytes
}
export function morphologyBounds(data:Morphology,wholeCns:boolean){
 const low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity]
 const brain=data.neurons.filter(n=>/^(cb_|ol_|visual)/.test(n.superclass||''))
 for(const n of wholeCns||!brain.length?data.neurons:brain)for(let i=0;i<n.positions.length;i++){const a=i%3;low[a]=Math.min(low[a],n.positions[i]);high[a]=Math.max(high[a],n.positions[i])}
 const center=low.map((v,i)=>(v+high[i])/2) as [number,number,number]
 return {center,extent:Math.max(1,...high.map((v,i)=>v-low[i]))/2}
}
