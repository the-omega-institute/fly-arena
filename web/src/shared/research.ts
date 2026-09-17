import type {Fly} from '../types'
export type CellSelector={class?:string;type?:string;side?:'L'|'R';ids?:string[]}
export type InterventionSpec={selector:{pre?:CellSelector;post?:CellSelector};scale:number}
export type SubjectRole='wildtype'|'official'|'design'
export type ExperimentSubject={role:SubjectRole;fly_id:string;name:string;artifact_id:string;parent_id?:string|null;reference_kind?:Fly['reference_kind'];submission_channel?:Fly['submission_channel'];release_id?:string|null}
export type ScenarioSpec={id?:string;geometry?:{size?:number;bounds?:number[];obstacles?:{position:number[];size:number[]}[]};stimulus?:unknown;task?:unknown;probe?:unknown;[key:string]:unknown}
export type BackendProfile={id:string;backend_id:string;model_id:string;sensor_id:string;readout_id:string;embodiment_id:string;ready:boolean;reason?:string;reduced_mode?:boolean;limitations?:string[];unavailable?:string[];motor_id?:string;protocol_id?:string;hashes:Record<string,string>;capabilities:Record<string,unknown>|string[]}
export type Probe={id:string;name:string;description:string;capabilities:Record<string,unknown>|string[];scenario?:ScenarioSpec;scenario_spec?:ScenarioSpec;[key:string]:unknown}
export type ResearchCatalog={schema_version:string;probes:Probe[];profile:BackendProfile;references:{wildtype:Fly|null;official:Fly|null};backends:unknown[];integrations:unknown[]}
export type ExperimentSpec={fly_id:string;probe_id:string;seeds:number[];duration_seconds:number}
export type TrajectoryPoint={time:number;x:number;y:number;yaw:number}
export type NeuralPoint={time:number;drive_left?:number;drive_right?:number;[key:string]:unknown}
export type ProbeReport={schema_version:string;fly_id:string;artifact_id:string;condition_key:string;probe_id:string;seed:number;duration_seconds:number;status:string;trajectory:TrajectoryPoint[];metrics:Record<string,number|null>;neural_trace:NeuralPoint[];receipt_sha256:string;profile:BackendProfile;scenario?:ScenarioSpec;geometry?:ScenarioSpec['geometry'];scene?:ResearchScene;error?:string|null;[key:string]:unknown}
export type ComparisonReport={schema_version:string;paired:{seed:number;fly_id:string;reference_fly_id:string;deltas:Record<string,number|null>;trajectory_divergence_mm:number|null}[];conditions:unknown[];summary?:unknown}
export type Experiment={id:string;owner:string;status:'queued'|'running'|'complete'|'failed';error:string|null;spec:ExperimentSpec;subjects:ExperimentSubject[];reports:ProbeReport[];comparison:ComparisonReport|null;created:number}
export const roleStyles:Record<SubjectRole,{color:string;dash:string;symbol:string}>={wildtype:{color:'#ffffff',dash:'',symbol:'○'},official:{color:'#e8b45d',dash:'9 5',symbol:'△'},design:{color:'#8ee0ba',dash:'3 4',symbol:'◇'}}
export function finite(value:unknown):value is number{return typeof value==='number'&&Number.isFinite(value)}
export function metricUnit(key:string){if(/(?:censored|choice|success|count|intake|energy)/.test(key))return '—';if(/(?:_mm_s|speed)/.test(key))return 'mm/s';if(/(?:_rad_s|angular_velocity)/.test(key))return 'rad/s';if(/(?:_rad|turning)/.test(key))return 'rad';if(/(?:_mm|path_length|distance|divergence)/.test(key))return 'mm';if(/(?:_seconds|_s$|latency|contact_time)/.test(key))return 's';if(/(?:_hz|rate)/.test(key))return 'Hz';return '—'}
export function validateHorizon(value:number){if(!Number.isInteger(value)||value<1||value>30)throw new Error('Horizon must be an integer from 1 to 30 seconds.');return value}
export function designRoleLabel(owner:string|undefined,viewer:string|undefined){return viewer&&owner===viewer?'Your design':'Submitted design'}
export type ResearchScene={size:number;spawns?:number[][];obstacles:{position:number[];size:number[]}[];food:{id:string;position:number[];initial:number}[]}
export function plotTransform(points:{x:number;y:number}[],scene?:ResearchScene){
 const half=scene?.size?scene.size/2:0;const xs=points.map(p=>p.x),ys=points.map(p=>p.y);
 for(const f of scene?.food||[]){xs.push(f.position[0]);ys.push(f.position[1])}
 for(const o of scene?.obstacles||[]){xs.push(o.position[0]-o.size[0]/2,o.position[0]+o.size[0]/2);ys.push(o.position[1]-o.size[1]/2,o.position[1]+o.size[1]/2)}
 const x0=Math.min(...xs,half?-half:Infinity)-1,x1=Math.max(...xs,half||-Infinity)+1,y0=Math.min(...ys,half?-half:Infinity)-1,y1=Math.max(...ys,half||-Infinity)+1;
 const scale=Math.min(620/Math.max(x1-x0,1),350/Math.max(y1-y0,1));
 return {x0,x1,y0,y1,scale,sx:(x:number)=>360+(x-(x0+x1)/2)*scale,sy:(y:number)=>220-(y-(y0+y1)/2)*scale}
}
export function parseSeeds(value:string){const tokens=value.split(/[,\s]+/).filter(Boolean);if(!tokens.length||tokens.length>8)throw new Error('Enter between 1 and 8 distinct seeds.');const seeds=tokens.map(Number);if(seeds.some(n=>!Number.isSafeInteger(n)||n<0||n>2147483647))throw new Error('Seeds must be integers from 0 to 2147483647.');if(new Set(seeds).size!==seeds.length)throw new Error('Seeds must be distinct.');return seeds}
/** Refuse alignment claims if any frozen subject is absent or the reported grids differ. */
export function alignment(reports:ProbeReport[],subjects:ExperimentSubject[]){if(!subjects.length||subjects.some(s=>!reports.some(r=>r.fly_id===s.fly_id&&r.artifact_id===s.artifact_id)))return 'pending';if(reports.some(r=>r.status!=='complete'||!r.receipt_sha256||!r.condition_key||!r.trajectory?.length))return 'pending';if(reports.some(r=>r.trajectory.some((p,i)=>!finite(p.time)||!finite(p.x)||!finite(p.y)||!finite(p.yaw)||p.time<0||p.time>r.duration_seconds||(i>0&&p.time<=r.trajectory[i-1].time))))return 'mismatch';const first=reports[0];return reports.every(r=>r.condition_key===first.condition_key&&r.duration_seconds===first.duration_seconds&&r.trajectory.length===first.trajectory.length&&r.trajectory.every((p,i)=>finite(p.time)&&p.time===first.trajectory[i].time))?'matched':'mismatch'}
export function sampleAt(points:TrajectoryPoint[],time:number){const valid=points.filter(p=>finite(p.time)&&finite(p.x)&&finite(p.y));if(!valid.length||time<valid[0].time||time>valid[valid.length-1].time)return null;let i=valid.findIndex(p=>p.time>=time);if(i<1)return valid[0];const a=valid[i-1],b=valid[i],f=(time-a.time)/(b.time-a.time||1);return {...a,time,x:a.x+(b.x-a.x)*f,y:a.y+(b.y-a.y)*f}}
