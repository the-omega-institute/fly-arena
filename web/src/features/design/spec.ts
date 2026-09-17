import type {Spec} from '../../types'
const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value)
export function assertSpec(value:unknown):asserts value is Spec {
 const invalid=()=>{throw Error('Choose a valid FlySpec v1 JSON file.')}
 if(!object(value))return invalid()
 if(value.schema_version!=='flyspec/v1'||typeof value.name!=='string'||!Array.isArray(value.weight_mutations)||!object(value.neuron_parameters)||!Array.isArray(value.edge_deltas??[])||!Array.isArray(value.interventions??[]))return invalid()
 for(const mutation of value.weight_mutations)if(!object(mutation)||typeof mutation.selector!=='string'||typeof mutation.scale!=='number'||!Number.isFinite(mutation.scale))invalid()
 for(const item of (value.interventions??[]) as unknown[]){
  if(!object(item)||!object(item.selector)||typeof item.scale!=='number'||!Number.isFinite(item.scale))return invalid()
  for(const side of ['pre','post']){const cell=item.selector[side];if(cell===undefined)continue;if(!object(cell))return invalid();if(cell.ids!==undefined&&(!Array.isArray(cell.ids)||cell.ids.some(id=>typeof id!=='string')))return invalid();if(cell.side!==undefined&&cell.side!=='L'&&cell.side!=='R')return invalid();for(const field of ['class','type'])if(cell[field]!==undefined&&typeof cell[field]!=='string')return invalid()}
 }
}
/** Keep all imported fields, including future server fields and interventions. */
export function composeSpec(base:Partial<Spec>,edits:Partial<Spec>):Spec{return {...base,...edits,neuron_parameters:{...base.neuron_parameters,...edits.neuron_parameters}} as Spec}
