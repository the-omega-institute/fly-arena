import type {Fly} from '../types'

/** Ownership is independent of recorded provenance; channels do not attest authorship. */
export function flyIdentity(fly:Fly|undefined,viewer:string|undefined,t:(key:string)=>string){
 const role=fly?.reference_kind==='wildtype'?'Trusted Wild Type':fly?.reference_kind==='official'?'Trusted official release':fly&&viewer&&fly.owner===viewer?'Your saved design':fly?'Saved design':'Participant';
 const unknown=!fly?.reference_kind||!fly?.submission_channel;
 return t(role)+(unknown?' · '+t('Provenance not recorded'):'');
}
export function savedFlyLabel(fly:Fly,viewer:string|undefined,t:(key:string)=>string){
 return `${fly.name} · ${flyIdentity(fly,viewer,t)} · ${fly.id.slice(0,8)}`;
}
