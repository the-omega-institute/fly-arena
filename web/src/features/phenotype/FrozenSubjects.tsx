import type {ExperimentSubject,SubjectRole} from '../../shared/research'
import {roleStyles,designRoleLabel} from '../../shared/research'
import {useI18n} from '../../shared/i18n'

/** Frozen details deliberately accept no live fly records. */
export function FrozenSubjects({subjects,owner,viewer}:{subjects:ExperimentSubject[];owner?:string;viewer?:string}){
 const {t}=useI18n();
 const value=(subject:ExperimentSubject|undefined,key:keyof ExperimentSubject)=>{
  if(!subject||subject[key]===undefined)return t('Not recorded in this experiment');
  if(subject[key]===null)return t(key==='reference_kind'||key==='submission_channel'?'Unknown':'Not supplied');
  return String(subject[key]);
 };
 return <div className="subject-grid">{(['wildtype','official','design'] as SubjectRole[]).map(role=>{
  const subject=subjects.find(s=>s.role===role);
  return <article className={'panel subject-card '+role} key={role}>
   <span className="role-badge"><span>{roleStyles[role].symbol}</span>{t(role==='wildtype'?'Wild Type':role==='official'?'Official release':designRoleLabel(owner,viewer))} · {t('Frozen')}</span>
   <h3>{subject?.name||t('Unavailable')}</h3>
   {subject&&(!subject.reference_kind||!subject.submission_channel)&&<p>{t('Provenance not recorded')}</p>}
   <dl><dt>{t('Artifact')}</dt><dd>{value(subject,'artifact_id')}</dd><dt>{t('Subject')}</dt><dd>{value(subject,'fly_id')}</dd>
    <dt>{t('Parent lineage')}</dt><dd>{value(subject,'parent_id')}</dd><dt>{t('Reference kind')}</dt><dd>{value(subject,'reference_kind')}</dd>
    <dt>{t('Submission channel')}</dt><dd>{value(subject,'submission_channel')}</dd><dt>{t('Release')}</dt><dd>{value(subject,'release_id')}</dd></dl>
  </article>;
 })}</div>;
}
