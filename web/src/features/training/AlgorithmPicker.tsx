import {useI18n} from '../../shared/i18n'
import {algorithms} from './algorithms'
import type {Strategy} from './algorithms'
export function AlgorithmPicker({value,onChange,name,onName}:{value:Strategy;onChange:(s:Strategy)=>void;name:string;onName:(n:string)=>void}){
  const {t}=useI18n()
  return <fieldset className="algorithm-picker"><legend>{t('Choose an optimizer')}</legend>
    <div className="algorithm-options">{algorithms.map(a=><label key={a.id} className={value===a.id?'selected':''}><input type="radio" name="optimizer" value={a.id} checked={value===a.id} onChange={()=>onChange(a.id)}/><span><strong>{t(a.name)}</strong><small>{t(a.description)}</small></span></label>)}</div>
    {value==='external'&&<label>{t('Algorithm / model name')}<input value={name} maxLength={64} placeholder="My PyTorch surrogate" onChange={e=>onName(e.target.value)}/></label>}
    <p className="training-hint">{t('The optimizer designs weights between evaluations. Each candidate keeps its founder’s selected brain model; within-match plasticity is currently off.')}</p>
  </fieldset>
}
