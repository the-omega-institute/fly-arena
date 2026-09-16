import {createContext,useContext,useEffect,useState} from 'react'
import type {ReactNode} from 'react'
import {catalog} from './messages'
export type Locale='en'|'zh-CN'
export type Theme='system'|'light'|'dark'
const I18nContext=createContext<{locale:Locale;theme:Theme;resolved:'light'|'dark';setLocale:(value:Locale)=>void;setTheme:(value:Theme)=>void;t:(key:string)=>string}>({locale:'en',theme:'system',resolved:'light',setLocale:()=>{},setTheme:()=>{},t:key=>key})
const read=(key:string,fallback:string)=>{try{return localStorage.getItem(key)||fallback}catch{return fallback}}
export function I18nProvider({children}:{children:ReactNode}){
 const [locale,setLocale]=useState<Locale>(()=>read('flyarena.locale',navigator.language.startsWith('zh')?'zh-CN':'en')==='zh-CN'?'zh-CN':'en');const [theme,setTheme]=useState<Theme>(()=>{const v=read('flyarena.theme','system');return v==='dark'||v==='light'?v:'system'});const [systemDark,setSystemDark]=useState(()=>matchMedia('(prefers-color-scheme: dark)').matches);const resolved=theme==='system'?(systemDark?'dark':'light'):theme;
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const change=()=>setSystemDark(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[]);
 useEffect(()=>{document.documentElement.lang=locale;document.documentElement.dataset.theme=resolved;document.documentElement.style.colorScheme=resolved;try{localStorage.setItem('flyarena.locale',locale);localStorage.setItem('flyarena.theme',theme)}catch{}},[locale,theme,resolved]);
 const t=(key:string)=>catalog[key as keyof typeof catalog]?.[locale]||key;
 return <I18nContext.Provider value={{locale,theme,resolved,setLocale,setTheme,t}}>{children}</I18nContext.Provider>
}
export const useI18n=()=>useContext(I18nContext)
export function Preferences(){const {locale,setLocale,theme,setTheme,t}=useI18n();return <div className="preferences"><select aria-label={t('Language')} value={locale} onChange={e=>setLocale(e.target.value as Locale)}><option value="en">English</option><option value="zh-CN">简体中文</option></select><select aria-label={t('Appearance')} value={theme} onChange={e=>setTheme(e.target.value as Theme)}><option value="system">{t('System')}</option><option value="light">{t('Light')}</option><option value="dark">{t('Dark')}</option></select></div>}
