"use client";
import React, { useState, useEffect } from "react";
import { API, ToastProvider, ConfirmProvider, AuthProvider } from "./components/shared";
import { LocaleProvider } from "./i18n";
import LoginPage from "./pages/LoginPage";
import AdminApp from "./pages/admin/AdminApp";
import UserApp from "./pages/user/UserApp";

export default function Home() {
  const [user,setUser]=useState<any>(null); const [token,setToken]=useState("");
  useEffect(()=>{
    const t=localStorage.getItem("ses_token"),u=localStorage.getItem("ses_user");
    if(t&&u){setToken(t);setUser(JSON.parse(u));}
    // 全局拦截 401：覆盖 fetch，token 失效自动登出
    const origFetch = window.fetch;
    window.fetch = async (...args) => {
      const res = await origFetch(...args);
      if (res.status === 401 && localStorage.getItem("ses_token")) {
        localStorage.removeItem("ses_token");
        localStorage.removeItem("ses_user");
        window.location.href = "/";
      }
      return res;
    };
  },[]);
  const login=async(un:string,pw:string,captchaId?:string,captchaCode?:string)=>{const r=await fetch(`${API}/auth/login`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:un,password:pw,captcha_id:captchaId,captcha_code:captchaCode})});if(!r.ok){const e=await r.json();throw new Error(e.detail||"Login failed");}const d=await r.json();setToken(d.access_token);setUser(d.user);localStorage.setItem("ses_token",d.access_token);localStorage.setItem("ses_user",JSON.stringify(d.user));};
  const logout=()=>{setToken("");setUser(null);localStorage.removeItem("ses_token");localStorage.removeItem("ses_user");};
  const ssoLogin=(ssoToken:string,ssoUser:any)=>{setToken(ssoToken);setUser(ssoUser);localStorage.setItem("ses_token",ssoToken);localStorage.setItem("ses_user",JSON.stringify(ssoUser));};
  if(!user) return <LocaleProvider><ToastProvider><LoginPage onLogin={login} onSsoLogin={ssoLogin}/></ToastProvider></LocaleProvider>;
  return <LocaleProvider><ToastProvider><ConfirmProvider><AuthProvider value={{user,token,logout}}>{user.is_admin?<AdminApp/>:<UserApp/>}</AuthProvider></ConfirmProvider></ToastProvider></LocaleProvider>;
}
