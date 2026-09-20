import type {InterventionSpec} from './shared/research'
export type {InterventionSpec,CellSelector,Experiment,ExperimentSpec,ExperimentSubject,ProbeReport,ComparisonReport,BackendProfile,ScenarioSpec,ResearchCatalog} from './shared/research'
export type Circuit = {id: string; label: string; name: string; color: string; neuron_count: number; edge_count: number}
export type Spec = {schema_version: 'flyspec/v1'; name: string; description: string; color: string; parent_id: string|null; connectome_sha256: string; model_profile: string; weight_mutations: {selector:string;scale:number}[]; edge_deltas: {edge:number;log_delta:number}[]; neuron_parameters:{tau_scale:number;threshold_shift_mv:number};plasticity:string;interventions?:InterventionSpec[];[key:string]:unknown}
export type Report = {artifact_id:string;budget_used:number;budget_limit:number;changed_edges:number;weight_points:number;intrinsic_points:number;neuron_count:number;edge_count:number;effective_changed_edges?:number;affected_neurons?:number;synaptic_contacts?:number;interventions?:unknown[];[key:string]:unknown}
export type Fly = {source?:{kind:string;run_id:string};id:string;owner:string;designer:string;name:string;color:string;artifact_id:string;created:number;spec:Spec;report:Report;reference_kind?:'wildtype'|'official'|'user'|'ai'|null;release_id?:string|null;submission_channel?:'web'|'api'|'seed'|null;experiment_id?:string|null;experiment_error?:string|null}
export type SensoryProfile = {id:string;name?:string;ready:boolean;reason?:string;qualification?:string;bridge_profiles?:string[];profile?:Record<string,unknown>}
export type TrainingBridge = {id:string;name?:string;ready:boolean;models?:string[];sensory_profiles?:string[];reason?:string}
export type Season = {id:string;name:string;connectome:{sha256:string;neuron_count:number;edge_count:number;synaptic_contacts:number;circuits:Circuit[]};budget:{points:number};invite_required:boolean;runtime_sha256:string;default_bridge_profile?:string;match_profiles?:MatchProfile[];sensory_profiles?:SensoryProfile[];training_sensory_profiles?:SensoryProfile[];training_bridge_profiles?:TrainingBridge[];training_fitness_objectives?:{id:string;name:string;ready:boolean}[];gallery_copy_available?:boolean}
export type ArenaObstacle = {position:number[];size:number[];shape?:'box'|'ellipsoid';quaternion?:number[];color?:string;material?:'leaf'|'rock'|'fruit'}
export type ArenaMap = {id:string;name:string;english:string;description:string;size:number;color:string;obstacles:ArenaObstacle[];food:number[][];modes:string[];ring_radius?:number;habitat?:string}
export type NeuralGraph = {neurons:{id:string;type?:string|null;class?:string|null;side?:string|null;nt?:string|null;position?:number[]|null}[];edges:{pre:string;post:string;edge:number;count:number;baseline_weight?:number;weight?:number;multiplier?:number}[];anchors?:string[]}
export type BrainDesignGraph = {schema:'brain-neighborhood/v1';artifact_id:string;connectome_sha256:string;weights_sha256:string;selection:string;circuits:Record<string,NeuralGraph>;display_groups?:Circuit[]}
export type ReplayParticipant = Pick<Fly,'id'|'name'|'color'|'artifact_id'|'spec'> & {report?:Pick<Report,'budget_used'|'budget_limit'>;brain_graph?:BrainDesignGraph}
export type Match = {queue?:{position:number;estimated_wait_seconds:number|null;estimated_remaining_seconds:number|null;estimate_samples:number;kind:string;backend:string;research_running:boolean};source?:{featured?:boolean;description?:{en?:string;'zh-CN'?:string};comparison_match?:string;comparison_links?:{match_id:string;label:{en:string;'zh-CN':string}}[]};participants?:ReplayParticipant[];tournament?:string|null;id:string;status:string;progress:number;attempt:number;created:number;error:string|null;request:{fly_ids:string[];map_id:string;mode:string;seed:number;duration_seconds:number;bridge_profile?:string;sensory_profile?:string};result:{behavior?:(BehaviorMetric|null)[];winner_slot:number|null;scores:number[];outcome:string;receipt_sha256:string}|null}
export type BodyModel = {meshes:Record<string,{vertices:number[];faces:number[]}>;geoms:{id:number;slot:number;name:string;mesh:string}[];food_geoms?:{id:number;food_id:string}[];contact_probes?:{slot:number;id:number;observation:string}[]}
export type ReplayEvent = {type:string;tick:number;slot?:number;food?:number|string[];amount?:number;values?:number[];mouth_distance?:number;slots?:number[];objects?:string[]}
export type BrainSample = {population?:{neuron_count:number;mean_hz:number;active_count:number;above_400hz_count:number};circuits:Record<string,number>;top_nodes?:{id:string;activity:number}[];sampled_nodes?:{id:string;activity:number}[];sampling?:{kind:string;count:number;sensory_groups?:Record<string,string[]>}}
export type SensorySample = {odor:number[];visual:number[];visual_status?:string;touch:number;touch_status?:string;sensory_profile?:string;contact_food?:string[];contact_environment?:string[];contact_support?:string[];tactile_activity?:number|null;taste?:number;touch_left?:number;touch_right?:number;contact_activity?:Record<string,number|null>;contact_environment_sides?:Record<string,string[]>;nearest_food:number|null;mouth_distance:number|null}
export type Frame = {tick:number;time:number;poses:number[][];positions:number[][];scores?:number[];food?:number[];energy?:number[];drives?:number[][];traces?:Record<string,number>[];brain?:BrainSample[];senses?:SensorySample[]}
export type Scene = {body:BodyModel;size:number;obstacles:ArenaObstacle[];food:{position:number[];initial:number;id:string}[];flies:{id:string;name:string;color:string}[];ring_radius?:number;habitat?:string}
export type Preview = {body:BodyModel;frame:Frame}
export type Identity = {id:string;name:string;token?:string}

export const colors:Record<string,string> = {mint:'#91bca5',amber:'#dca85c',violet:'#aaa1cf',rose:'#d69493',blue:'#88aecd'}
export const modes:Record<string,string> = {forage:'单蝇觅食',contest:'双蝇抢食',sumo:'擂台争夺'}
export const num = (n:number) => Intl.NumberFormat('en-US').format(n)

export type AuthSettings = {mode:"local"|"nyxid";nyxid_enabled:boolean;login_url:string|null;local_registration_enabled:boolean}

export type MatchProfile={id:string;name:string;ready:boolean;sandbox_ready?:boolean;sensory_profiles?:string[];reason?:string}
export function playableProfile(p:MatchProfile|undefined){return !!p&&(p.ready||p.sandbox_ready===true)}
export function compatibleSensory(season:Season|null,bridge:string,senses:string){
 const profile=season?.match_profiles?.find(p=>p.id===bridge)
 return profile?.sensory_profiles?profile.sensory_profiles.includes(senses):senses==='odor-only-v1'||bridge==='legacy-v1'
}
export function defaultMatchProfile(season:Season){return season.match_profiles?.find(p=>p.id==='sensorimotor-research-v2'&&playableProfile(p))?.id||season.default_bridge_profile||''}
export function recordedMatchProfile(match:Match){return match.request.bridge_profile||'legacy-v1'}

/** Prefer a complete multimodal life sample for the first Arena view.
 * The match log remains chronological; this only chooses the initial focus.
 */
export function preferredReplay(matches:Match[]){
 const verified=matches.filter(match=>match.status==='verified')
 return verified.filter(match=>match.source?.featured).sort((a,b)=>b.created-a.created)[0]
   ||verified.find(match=>match.request.duration_seconds>=30&&match.request.sensory_profile==='engineered-multimodal-v1'&&match.result?.scores?.some(score=>score>0))
   ||verified.find(match=>match.result?.scores?.some(score=>score>0))
   ||verified[0]
}

export type ArenaLayout = {id:string;size:number;obstacles:ArenaObstacle[];food:{position:number[];initial:number;id:string}[];spawns:number[][];ring_radius?:number;habitat?:string}

export type BehaviorMetric={schema:"sustained-foraging-v1";food:number;latter_half_food:number;upright_fraction:number;recorded_seconds:number;first_inversion_s:number|null;fitness:number}
