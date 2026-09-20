import {flyIdentity} from '../../shared/flyIdentity'
import {useI18n} from '../../shared/i18n'
import type {Scene} from '../../types'

export function ArenaWorldLabel({fly,slot,selected,identity,compact=false}:{fly:Scene['flies'][number];slot:number;selected:boolean;identity?:string;compact?:boolean}){
 const {t}=useI18n();
 return <div className={'fly-world-label '+(selected?'selected':'')+(compact?' compact':'')} title={`${fly.name} · ${fly.id}`}>
  <b>{selected?'▣':'○'} {t('Slot')} {slot+1}{!compact&&` · ${fly.name}`}</b>
  {!compact&&<small>{identity||flyIdentity(undefined,undefined,t)} · {fly.id.slice(0,8)}</small>}
 </div>;
}
