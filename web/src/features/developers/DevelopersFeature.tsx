import {useState} from 'react'
import type {Dispatch,SetStateAction,RefObject} from 'react'
import {ArrowDownToLine,ArrowRight,ArrowUpRight,Code2,Copy,ExternalLink,Terminal} from 'lucide-react'
import type {Identity,Spec} from '../../types'
import {useI18n} from '../../shared/i18n'
import {buildContributionPrompt,contributionCopy,type ContributionLocale} from './contribution'
import './developers.css'
type Set<T>=Dispatch<SetStateAction<T>>

type Props={jsonEditor:string;setJsonEditor:Set<string>;spec:Spec;download:(name:string,value:unknown)=>void;fileInput:RefObject<HTMLInputElement|null>;loadSpec:(value:Spec)=>void;setError:Set<string>;identity:Identity|null;setShowToken:Set<boolean>;setLogin:Set<boolean>}
export function DevelopersFeature({jsonEditor,setJsonEditor,spec,download,fileInput,loadSpec,setError,identity,setShowToken,setLogin}:Props){
  const {t,locale}=useI18n()
  const contributionLocale:ContributionLocale=locale==='zh-CN'?'zh':'en'
  const [copyStatus,setCopyStatus]=useState<'idle'|'copied'|'error'>('idle')
  const copy=contributionCopy[contributionLocale]
  const origin=typeof window==='undefined'?'':window.location.origin
  const prompt=buildContributionPrompt(origin,contributionLocale)
  async function copyPrompt(){
    try{
      await navigator.clipboard.writeText(prompt)
      setCopyStatus('copied')
    }catch{
      setCopyStatus('error')
    }
  }
  return <>
    <section className="developers-contribution" aria-label={copy.heading}>
      <header className="contribution-header"><div><span className="eyebrow">{copy.eyebrow}</span><h3>{copy.heading}</h3><p>{copy.intro}</p></div></header>
      <div className="contribution-grid">{copy.cards.map(card=><article className="contribution-card" key={card.label}><span className="card-label">{card.label}</span><h4>{card.title}</h4><p>{card.body}</p><small>{card.detail}</small></article>)}</div>
      <article className="prompt-card"><header><div><h4>{copy.promptTitle}</h4><p>{copy.promptIntro}</p></div><button className="secondary copy-button" onClick={copyPrompt}><Copy size={14}/>{copy.copyPrompt}</button></header><textarea readOnly value={prompt} aria-label={copy.promptTitle} onFocus={event=>event.currentTarget.select()}/><div className={'copy-status '+(copyStatus==='error'?'error':'')} aria-live="polite">{copyStatus==='copied'?copy.copied:copyStatus==='error'?copy.copyFailed:''}</div></article>
      <div className="contribution-foot"><p><strong>{copy.bounds}:</strong> {copy.boundsBody}</p><div className="contribution-links"><a href="/api/v1/agent-guide" target="_blank" rel="noreferrer">{copy.docs}<ExternalLink size={13}/></a><button onClick={()=>identity?setShowToken(true):setLogin(true)}>{copy.token}<ArrowUpRight size={13}/></button></div></div>
    </section>
    <div className="code-layout"><section className="panel code-main"><div className="panel-heading"><span><Code2 size={17}/> {t("FlySpec 编辑器")}</span><div><button className="text-link" onClick={()=>setJsonEditor(JSON.stringify(spec,null,2))}><Copy size={14}/>{t("载入当前设计")}</button><button className="text-link" onClick={()=>(()=>{try{download('flyspec.json',JSON.parse(jsonEditor||JSON.stringify(spec)))}catch(e){setError(String(e))}})()}><ArrowDownToLine size={14}/>{t("导出")}</button></div></div><textarea aria-label={t("FlySpec JSON 编辑器")} spellCheck={false} value={jsonEditor||JSON.stringify(spec,null,2)} onChange={e=>setJsonEditor(e.target.value)}/><div className="code-actions"><input type="file" accept=".json,application/json" hidden ref={fileInput} onChange={async e=>{const f=e.target.files?.[0];if(f)try{loadSpec(JSON.parse(await f.text()))}catch(err){setError(String(err))}}}/><button className="secondary" onClick={()=>fileInput.current?.click()}>{t("导入 JSON")}</button><button className="primary" onClick={()=>{try{loadSpec(JSON.parse(jsonEditor||JSON.stringify(spec)))}catch(e){setError(String(e))}}}>{t("在工坊中打开")}<ArrowRight size={15}/></button></div></section><aside className="api-guide"><div className="api-guide-card"><Terminal size={25}/><span className="eyebrow">{t("AGENT-NATIVE BY DESIGN")}</span><h2>{t("同一格式。")}<br/>{t("无限设计师。")}</h2><p>{t("AI 与网页玩家使用相同的图谱、预算和验证流程。设计完成后，上传 FlySpec 并请求一次评测。")}</p><ol><li><span>01</span><div>{t("读取当前规则")}<code>GET /api/v1/season</code></div></li><li><span>02</span><div>{t("验证并保存设计")}<code>POST /api/v1/flies/validate</code></div></li><li><span>03</span><div>{t("提交比赛、轮询结果")}<code>POST /api/v1/matches</code></div></li></ol><a className="primary wide" href="/docs" target="_blank" rel="noreferrer">{t("交互式 API 文档")}<ExternalLink size={15}/></a><button className="secondary wide" onClick={()=>identity?setShowToken(true):setLogin(true)}>{t("获取我的 API 身份")}<ArrowUpRight size={15}/></button></div><p className="small-print">{t("支持任意 AI agent。所有提交是声明式数据，比赛运行期间不会执行玩家上传的代码。")}</p></aside></div>
  </>
}
