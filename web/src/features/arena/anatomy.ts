import {serviceUrl} from '../../api'
import type {NeuralGraph} from '../../types'

export type Anatomy={schema:'connectome-anatomy/v1';connectome_sha256:string;neuron_count:number;position_count:number;missing_position_count:number;positions:number[]}
export type AnatomySpace={positions:Float32Array;center:[number,number,number];extent:number}
export type SpatialNode={id:string;position:[number,number,number]|null;activity:number|null}
const cache=new Map<string,Anatomy>()

export function mergeNeighborhoods(circuits:Record<string,NeuralGraph>):NeuralGraph{
  const neurons=new Map<string,NeuralGraph['neurons'][number]>(),edges=new Map<number,NeuralGraph['edges'][number]>()
  for(const graph of Object.values(circuits)){
    for(const node of graph.neurons)neurons.set(node.id,node)
    for(const edge of graph.edges)edges.set(edge.edge,edge)
  }
  return {neurons:[...neurons.values()],edges:[...edges.values()]}
}

export function validateAnatomy(value:Anatomy,expected:string):Anatomy{
  if(!value||value.schema!=='connectome-anatomy/v1'||value.connectome_sha256!==expected
    ||![value.neuron_count,value.position_count,value.missing_position_count].every(n=>Number.isSafeInteger(n)&&n>=0)
    ||value.position_count+value.missing_position_count!==value.neuron_count
    ||!Array.isArray(value.positions)||value.positions.length!==value.position_count*3
    ||!value.positions.every(n=>typeof n==='number'&&Number.isFinite(n)))throw Error('Anatomical coordinates do not match this replay')
  return value
}

export async function loadAnatomy(expected:string,signal:AbortSignal):Promise<Anatomy>{
  if(!/^[a-f0-9]{64}$/.test(expected))throw Error('Connectome identity unavailable')
  const saved=cache.get(expected);if(saved)return saved
  for(const path of [serviceUrl('/api/v1/connectome/anatomy'),'/examples/anatomy/'+expected+'.json']){
    try{
      const response=await fetch(path,{signal,credentials:'same-origin'})
      if(!response.ok)throw Error('Anatomical coordinates unavailable')
      const value=validateAnatomy(await response.json(),expected)
      if(cache.size>=2)cache.delete(cache.keys().next().value!)
      cache.set(expected,value);return value
    }catch(error){if(signal.aborted)throw error}
  }
  throw Error('Anatomical coordinates unavailable for this connectome')
}

/** One uniform display transform; never deform the source anatomy by axis. */
export function anatomySpace(data:Anatomy):AnatomySpace{
  const low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity]
  for(let i=0;i<data.positions.length;i++){const axis=i%3,v=data.positions[i];low[axis]=Math.min(low[axis],v);high[axis]=Math.max(high[axis],v)}
  const center=(data.position_count?low.map((v,i)=>(v+high[i])/2):[0,0,0]) as [number,number,number]
  const extent=data.position_count?Math.max(1,...high.map((v,i)=>v-low[i]))/2:1
  const positions=Float32Array.from(data.positions,(v,i)=>(v-center[i%3])/extent)
  return {positions,center,extent}
}

export function spatialNodes(graph:NeuralGraph,space:AnatomySpace,activity:Map<string,number>):SpatialNode[]{
  return graph.neurons.map(node=>{
    const p=node.position,value=activity.get(node.id)
    return {id:node.id,position:Array.isArray(p)&&p.length===3&&p.every(v=>typeof v==='number'&&Number.isFinite(v))?p.map((v,i)=>(v-space.center[i])/space.extent) as [number,number,number]:null,
      activity:value!==undefined&&Number.isFinite(value)?value:null}
  })
}
