"use client";
import React, { useState, useEffect, useRef, createContext, useContext, useCallback } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL || "/api";
export const authH = (t: string) => ({ Authorization: `Bearer ${t}`, "Content-Type": "application/json" });

// 全局 401 处理：token 失效时自动跳转登录
export function handle401(response: Response) {
  if (response.status === 401) {
    localStorage.removeItem("ses_token");
    localStorage.removeItem("ses_user");
    window.location.href = "/";
  }
  return response;
}

export async function authFetch(url: string, token: string, options: RequestInit = {}) {
  const res = await fetch(url, { ...options, headers: { ...authH(token), ...(options.headers || {}) } });
  if (res.status === 401) {
    localStorage.removeItem("ses_token");
    localStorage.removeItem("ses_user");
    window.location.href = "/";
    throw new Error("Session expired");
  }
  return res;
}

// ===== Toast =====
type TT = "success"|"error"|"info"|"warning";
const ToastCtx = createContext<{toast:(t:TT,title:string,msg?:string)=>void}>({toast:()=>{}});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({children}:{children:React.ReactNode}) {
  const [list,setList]=useState<{id:number;type:TT;title:string;msg:string}[]>([]);
  const toast=useCallback((type:TT,title:string,msg="")=>{
    const id=Date.now(); setList(p=>[...p,{id,type,title,msg}]); setTimeout(()=>setList(p=>p.filter(t=>t.id!==id)),4000);
  },[]);
  const colors={success:"#10B981",error:"#EF4444",info:"#3B82F6",warning:"#F59E0B"};
  const icons={success:"✓",error:"✕",info:"i",warning:"!"};
  return <ToastCtx.Provider value={{toast}}>{children}
    <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-3" style={{width:380}}>
      {list.map(t=><div key={t.id} className="animate-slide-in bg-white rounded-xl shadow-lg border border-gray-100 p-4 flex gap-3">
        <span className="w-6 h-6 rounded-full flex items-center justify-center text-white text-xs flex-shrink-0" style={{background:colors[t.type]}}>{icons[t.type]}</span>
        <div className="flex-1 min-w-0"><p className="text-sm font-semibold text-gray-800">{t.title}</p>{t.msg&&<p className="text-xs text-gray-500 mt-0.5 whitespace-pre-line">{t.msg}</p>}</div>
        <button onClick={()=>setList(p=>p.filter(x=>x.id!==t.id))} className="text-gray-400 hover:text-gray-600 text-lg leading-none">&times;</button>
      </div>)}
    </div>
  </ToastCtx.Provider>;
}

// ===== Confirm =====
const ConfirmCtx = createContext<{confirm:(t:string,m:string,btn?:string)=>Promise<boolean>}>({confirm:async()=>false});
export const useConfirm = () => useContext(ConfirmCtx);

export function ConfirmProvider({children}:{children:React.ReactNode}) {
  const [s,setS]=useState({open:false,title:"",msg:"",btn:"确认"}); const ref=React.useRef<(v:boolean)=>void>(undefined);
  const confirm=useCallback((title:string,msg:string,btn="确认"):Promise<boolean>=>new Promise(r=>{ref.current=r;setS({open:true,title,msg,btn});}),[]);
  const yes=()=>{ref.current?.(true);setS(s=>({...s,open:false}));}; const no=()=>{ref.current?.(false);setS(s=>({...s,open:false}));};
  return <ConfirmCtx.Provider value={{confirm}}>{children}
    {s.open&&<div className="fixed inset-0 z-[9999] flex items-center justify-center animate-fade-in">
      <div className="absolute inset-0 bg-black/50" onClick={no}/>
      <div className="relative bg-white rounded-2xl shadow-2xl animate-scale-in" style={{width:420,maxWidth:"90vw"}}>
        <div className="p-6"><h3 className="text-lg font-bold text-gray-800">{s.title}</h3><p className="text-sm text-gray-500 mt-2 whitespace-pre-line">{s.msg}</p></div>
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-100">
          <button onClick={no} className="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50">取消</button>
          <button onClick={yes} className="px-4 py-2 text-sm rounded-lg bg-red-500 text-white hover:bg-red-600">{s.btn}</button>
        </div>
      </div>
    </div>}
  </ConfirmCtx.Provider>;
}

// ===== Auth =====
const AuthCtx = createContext<any>(null);
export const useAuth = () => useContext(AuthCtx);
export const AuthProvider = AuthCtx.Provider;

// ===== Sidebar =====
export function Sidebar({menus,active,setActive,title="SES Sender"}:{menus:{id:string;icon:string;label:string}[];active:string;setActive:(id:string)=>void;title?:string}) {
  const {user,logout}=useAuth();
  let t:(k:string)=>string = (k)=>k;
  let locale="zh", setLocale:(l:any)=>void = ()=>{};
  try { const i18n = require("../i18n"); t=i18n.useT(); const lc=i18n.useLocale(); locale=lc.locale; setLocale=lc.setLocale; } catch {}
  return <aside className="w-64 flex-shrink-0 flex flex-col h-screen sticky top-0 overflow-y-auto" style={{background:"#1C2434"}}>
    <div className="h-16 flex items-center px-6 gap-3 flex-shrink-0"><div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center"><span className="text-white font-bold text-sm">S</span></div><span className="text-white text-lg font-bold">{title}</span></div>
    <div className="px-5 mt-4 mb-2"><p className="text-xs font-semibold uppercase tracking-wider" style={{color:"#8A99AF"}}>{t("sidebar.menu")}</p></div>
    <nav className="flex-1">{menus.map(m=><div key={m.id} onClick={()=>setActive(m.id)} className={`sidebar-link ${active===m.id?"active":""}`}><span className="text-lg">{m.icon}</span><span>{m.label}</span></div>)}</nav>
    <div className="p-5 border-t" style={{borderColor:"#333A48"}}>
      <div className="flex items-center gap-3"><div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center"><span className="text-white text-sm font-bold">{(user.display_name||user.username)[0]?.toUpperCase()}</span></div>
        <div className="flex-1 min-w-0"><p className="text-sm font-medium text-white truncate">{user.display_name||user.username}</p><p className="text-xs truncate" style={{color:"#8A99AF"}}>{user.email||t("sidebar.admin")}</p></div>
      </div>
      <div className="flex items-center gap-2 mt-3">
        <button onClick={()=>setLocale(locale==="zh"?"en":"zh")} className="flex-shrink-0 px-2 py-1.5 rounded-lg text-xs font-medium transition border" style={{borderColor:"#333A48",color:"#8A99AF"}} title="Switch language">
          {locale==="zh"?"EN":"中"}
        </button>
        <button onClick={logout} className="flex-1 flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-sm transition hover:bg-red-500/20 text-red-400 hover:text-red-300 border border-red-500/20 hover:border-red-500/40">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
          {t("sidebar.logout")}
        </button>
      </div>
    </div>
  </aside>;
}

// ===== UI Components =====
export function Card({title,extra,children}:{title?:string;extra?:React.ReactNode;children:React.ReactNode}) {
  return <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
    {title&&<div className="flex items-center justify-between px-6 py-4 border-b border-gray-100"><h3 className="text-base font-semibold text-gray-800">{title}</h3>{extra}</div>}
    <div className="p-6">{children}</div>
  </div>;
}

export function Badge({color,children}:{color:"green"|"blue"|"red"|"orange"|"gray";children:React.ReactNode}) {
  const cls={green:"bg-emerald-50 text-emerald-600",blue:"bg-blue-50 text-blue-600",red:"bg-red-50 text-red-600",orange:"bg-amber-50 text-amber-600",gray:"bg-gray-100 text-gray-500"};
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cls[color]}`}>{children}</span>;
}

export function Input({className="",...props}:any) { return <input className={`w-full h-10 px-3.5 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition ${className}`} {...props}/>; }
export function Textarea(props:any) { return <textarea className="w-full min-h-[100px] px-3.5 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition resize-y" {...props}/>; }
export function Select(props:any) { return <select className="w-full h-10 px-3.5 border border-gray-200 rounded-lg text-sm text-gray-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition bg-white cursor-pointer" {...props}/>; }

export function Btn({variant="primary",size="md",className="",...props}:any) {
  const base="inline-flex items-center justify-center font-medium rounded-lg transition";
  const vs:Record<string,string>={primary:"bg-indigo-600 text-white hover:bg-indigo-700",success:"bg-emerald-500 text-white hover:bg-emerald-600",danger:"bg-red-500 text-white hover:bg-red-600",warning:"bg-amber-500 text-white hover:bg-amber-600",outline:"border border-gray-200 text-gray-600 hover:bg-gray-50 bg-white"};
  const ss:Record<string,string>={sm:"h-8 px-3 text-xs",md:"h-10 px-4 text-sm",lg:"h-11 px-5 text-sm"};
  return <button className={`${base} ${vs[variant]||vs.primary} ${ss[size]||ss.md} ${className} disabled:opacity-50`} {...props}/>;
}

export function Pager({page,totalPages,total,onPageChange}:{page:number;totalPages:number;total:number;onPageChange:(p:number)=>void}) {
  if(total===0) return null;
  let t:(k:string,p?:any)=>string;
  try { t = require("../i18n").useT(); } catch { t = (k:string)=>k; }
  const pages:number[]=[]; for(let i=Math.max(1,page-2);i<=Math.min(totalPages,page+2);i++) pages.push(i);
  return <div className="flex items-center justify-between pt-4 border-t border-gray-100 mt-4">
    <span className="text-xs text-gray-400">{t("common.pageInfo",{total:String(total),page:String(page),totalPages:String(totalPages)})}</span>
    {totalPages>1&&<div className="flex gap-1">
      <Btn key="prev" variant="outline" size="sm" disabled={page<=1} onClick={()=>onPageChange(page-1)}>{t("common.prevPage")}</Btn>
      {pages.map(p=><Btn key={p} variant={p===page?"primary":"outline"} size="sm" onClick={()=>onPageChange(p)}>{p}</Btn>)}
      <Btn key="next" variant="outline" size="sm" disabled={page>=totalPages} onClick={()=>onPageChange(page+1)}>{t("common.nextPage")}</Btn>
    </div>}
  </div>;
}

// ===== Modal =====
export function Modal({open,onClose,title,width=480,children}:{open:boolean;onClose:()=>void;title:string;width?:number;children:React.ReactNode}) {
  if(!open) return null;
  return <div className="fixed inset-0 z-[9998] flex items-center justify-center animate-fade-in">
    <div className="absolute inset-0 bg-black/50" onClick={onClose}/>
    <div className="relative bg-white rounded-2xl shadow-2xl animate-scale-in flex flex-col" style={{width,maxWidth:"90vw",maxHeight:"85vh"}}>
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
        <h3 className="text-base font-semibold text-gray-800">{title}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
      </div>
      <div className="p-6 overflow-y-auto flex-1">{children}</div>
    </div>
  </div>;
}
