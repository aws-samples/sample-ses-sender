"use client";
import React, { useState, useCallback, useEffect } from "react";
import { API } from "../components/shared";

function useServerCaptcha() {
  const [image, setImage] = useState("");
  const [captchaId, setCaptchaId] = useState("");
  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/auth/captcha`);
      const d = await r.json();
      setImage(d.image || "");
      setCaptchaId(d.captcha_id || "");
    } catch {
      setImage("");
      setCaptchaId("");
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return { image, captchaId, refresh };
}

export default function LoginPage({onLogin,onSsoLogin}:{onLogin:(un:string,pw:string,captchaId?:string,captchaCode?:string)=>Promise<void>;onSsoLogin?:(token:string,user:any)=>void}) {
  const [u,setU]=useState("");const [p,setP]=useState("");const [captchaInput,setCaptchaInput]=useState("");
  const [err,setErr]=useState("");const [ld,setLd]=useState(false);
  const [ssoProviders,setSsoProviders]=useState<{id:string;name:string;icon:string}[]>([]);
  const captcha=useServerCaptcha();
  let t:(k:string)=>string = (k)=>k, locale="zh", setLocale:(l:any)=>void = ()=>{};
  try { const i18n = require("../i18n"); t=i18n.useT(); const lc=i18n.useLocale(); locale=lc.locale; setLocale=lc.setLocale; } catch {}

  useEffect(()=>{
    fetch("/api/sso/providers").then(r=>r.json()).then(d=>{if(Array.isArray(d))setSsoProviders(d);}).catch(()=>{});
    const params=new URLSearchParams(window.location.search);
    const ssoToken=params.get("sso_token");
    const ssoUser=params.get("sso_user");
    if(ssoToken&&ssoUser&&onSsoLogin){
      try{onSsoLogin(ssoToken,JSON.parse(decodeURIComponent(ssoUser)));}catch{}
      window.history.replaceState({},"","/");
    }
  },[]);

  const ssoLogin=(providerId:string)=>{
    const base=window.location.origin;
    const callbackUrl=`${base}/api/sso/${providerId}/callback`;
    window.location.href=`/api/sso/${providerId}/login?redirect_uri=${encodeURIComponent(callbackUrl)}`;
  };

  const ssoIcons:{[k:string]:string}={github:"M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z",google:"M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"};

  const go=async(e:React.FormEvent)=>{
    e.preventDefault(); setErr("");
    if(!captchaInput.trim()){setErr(t("login.captchaError"));return;}
    setLd(true);
    try{
      await onLogin(u,p,captcha.captchaId,captchaInput);
    }catch(e:any){
      setErr(e.message);captcha.refresh();setCaptchaInput("");
    }finally{setLd(false);}
  };

  return <div className="min-h-screen flex items-center justify-center" style={{background:"linear-gradient(135deg,#3C50E0 0%,#6366F1 50%,#8B5CF6 100%)"}}>
    <div className="bg-white rounded-2xl shadow-2xl p-8 w-full relative" style={{maxWidth:400}}>
      <button onClick={()=>setLocale(locale==="zh"?"en":"zh")} className="absolute top-4 right-4 text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-1">{locale==="zh"?"EN":"中文"}</button>
      <div className="text-center mb-8"><div className="w-12 h-12 rounded-xl bg-indigo-600 flex items-center justify-center mx-auto mb-3"><span className="text-white text-xl font-bold">S</span></div><h1 className="text-2xl font-bold text-gray-800">{t("login.title")}</h1><p className="text-gray-400 text-sm mt-1">{t("login.subtitle")}</p></div>
      <form onSubmit={go} className="space-y-4">
        {err&&<div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg p-3">{err}</div>}
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("login.username")}</label><input className="w-full h-11 px-4 border border-gray-200 rounded-lg text-gray-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition" value={u} onChange={e=>setU(e.target.value)}/></div>
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("login.password")}</label><input type="password" className="w-full h-11 px-4 border border-gray-200 rounded-lg text-gray-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition" value={p} onChange={e=>setP(e.target.value)}/></div>
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("login.captcha")}</label>
          <div className="flex gap-3">
            <input className="flex-1 h-11 px-4 border border-gray-200 rounded-lg text-gray-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition tracking-widest" placeholder={t("login.captchaPlaceholder")} value={captchaInput} onChange={e=>setCaptchaInput(e.target.value)} autoComplete="off"/>
            {captcha.image
              ? <img src={captcha.image} width={120} height={40} onClick={()=>{captcha.refresh();setCaptchaInput("");}} className="rounded-lg cursor-pointer border border-gray-200 flex-shrink-0 hover:opacity-80 transition" title={t("login.captchaRefresh")} alt="captcha"/>
              : <div onClick={()=>{captcha.refresh();setCaptchaInput("");}} style={{width:120,height:40}} className="rounded-lg cursor-pointer border border-gray-200 flex-shrink-0 bg-gray-50 flex items-center justify-center text-xs text-gray-400 hover:opacity-80 transition">···</div>}
          </div>
          <p className="text-xs text-gray-400 mt-1">{t("login.captchaRefresh")}</p>
        </div>
        <button type="submit" disabled={ld} className="w-full h-11 rounded-lg bg-indigo-600 text-white font-semibold hover:bg-indigo-700 disabled:opacity-50 transition">{ld?t("login.loggingIn"):t("login.loginBtn")}</button>
      </form>
      {ssoProviders.length>0&&<>
        <div className="flex items-center gap-3 my-5"><div className="flex-1 h-px bg-gray-200"/><span className="text-xs text-gray-400">{t("login.ssoOr")}</span><div className="flex-1 h-px bg-gray-200"/></div>
        <div className="flex gap-3">{ssoProviders.map(sp=>(
          <button key={sp.id} onClick={()=>ssoLogin(sp.id)} className="flex-1 h-11 flex items-center justify-center gap-2 border border-gray-200 rounded-lg hover:bg-gray-50 transition text-sm text-gray-700 font-medium">
            {ssoIcons[sp.icon]?<svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d={ssoIcons[sp.icon]}/></svg>:<span>🔐</span>}
            {sp.name}
          </button>
        ))}</div>
      </>}
    </div>
  </div>;
}
