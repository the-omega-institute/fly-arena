export type Circuit = {id: string; label: string; name: string; color: string; neuron_count: number; edge_count: number}
export type Spec = {schema_version: 'flyspec/v1'; name: string; description: string; color: string; parent_id: string|null; connectome_sha256: string; model_profile: string; weight_mutations: {selector:string;scale:number}[]; edge_deltas: {edge:number;log_delta:number}[]; neuron_parameters:{tau_scale:number;threshold_shift_mv:number};plasticity:string}
export type Report = {artifact_id:string;budget_used:number;budget_limit:number;changed_edges:number;weight_points:number;intrinsic_points:number;neuron_count:number;edge_count:number}
export type Fly = {id:string;owner:string;designer:string;name:string;color:string;artifact_id:string;created:number;spec:Spec;report:Report}
export type Season = {id:string;name:string;connectome:{sha256:string;neuron_count:number;edge_count:number;synaptic_contacts:number;circuits:Circuit[]};budget:{points:number};invite_required:boolean;runtime_sha256:string}
export type ArenaMap = {id:string;name:string;english:string;description:string;size:number;color:string;obstacles:{position:number[];size:number[]}[];food:number[][];modes:string[];ring_radius?:number}
export type Match = {tournament?:string|null;id:string;status:string;progress:number;attempt:number;created:number;error:string|null;request:{fly_ids:string[];map_id:string;mode:string;seed:number;duration_seconds:number};result:{winner_slot:number|null;scores:number[];outcome:string;receipt_sha256:string}|null}
export type BodyModel = {meshes:Record<string,{vertices:number[];faces:number[]}>;geoms:{id:number;slot:number;name:string;mesh:string}[]}
export type Frame = {tick:number;time:number;poses:number[][];positions:number[][];scores?:number[];food?:number[];energy?:number[];drives?:number[][];traces?:Record<string,number>[]}
export type Scene = {body:BodyModel;size:number;obstacles:{position:number[];size:number[]}[];food:{position:number[];initial:number;id:string}[];flies:{id:string;name:string;color:string}[];ring_radius?:number}
export type Preview = {body:BodyModel;frame:Frame}
export type Identity = {id:string;name:string;token?:string}

export const colors:Record<string,string> = {mint:'#91bca5',amber:'#dca85c',violet:'#aaa1cf',rose:'#d69493',blue:'#88aecd'}
export const modes:Record<string,string> = {forage:'单蝇觅食',contest:'双蝇抢食',sumo:'擂台争夺'}
export const num = (n:number) => Intl.NumberFormat('en-US').format(n)

export type AuthSettings = {mode:"local"|"nyxid";nyxid_enabled:boolean;login_url:string|null;local_registration_enabled:boolean}
