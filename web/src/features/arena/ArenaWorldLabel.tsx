import {flyIdentity} from '../../shared/flyIdentity'
import {useI18n} from '../../shared/i18n'
import type {Scene} from '../../types'

export function ArenaWorldLabel({fly,slot,selected,identity}:{fly:Scene['flies'][number];slot:number;selected:boolean;identity?:string}){
 const {t}=useI18n();
 return <div className={'fly-world-label '+(selected?'selected':'')} title={`${fly.name} · ${fly.id}`}>
  <b>{selected?'▣':'○'} {t('Slot')} {slot+1} · {fly.name}</b>
  <small>{identity||flyIdentity(undefined,undefined,t)} · {fly.id.slice(0,8)}</small>
 </div>;
}
