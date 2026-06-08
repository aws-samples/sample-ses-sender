"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, Card, Badge, Btn, Input, Select, Textarea } from "../../components/shared";
import { useT } from "../../i18n";

export default function AdminTestEmail() {
  const {token}=useAuth(); const {toast}=useToast(); const t=useT();
  const [ids,setIds]=useState<any[]>([]); const [f,setF]=useState({source:"",to:"",subject:"",html_body:""}); const [ld,setLd]=useState(false);
  useEffect(()=>{fetch(`${API}/admin/identities`,{headers:authH(token)}).then(r=>r.json()).then(d=>setIds(Array.isArray(d)?d.filter((x:any)=>x.verification_status==="Success"):[]));} ,[]);
  const send=async()=>{if(!f.source||!f.to||!f.subject||!f.html_body)return toast("warning",t("admin.test.fillComplete"));setLd(true);try{const r=await fetch(`${API}/admin/test-email`,{method:"POST",headers:authH(token),body:JSON.stringify(f)});const d=await r.json();if(r.ok)toast("success",t("admin.test.sent"),`MessageId: ${d.message_id}`);else toast("error",t("common.failed"),d.detail);}catch{toast("error",t("common.networkError"));}finally{setLd(false);}};

  return <div style={{maxWidth:640}}><Card title={t("admin.test.title")}>
    <div className="space-y-4">
      <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("admin.test.from")}</label>
        <div className="flex gap-2"><Select style={{flex:1}} onChange={(e:any)=>{if(e.target.value)setF({...f,source:e.target.value});}}><option value="">{t("admin.test.selectIdentity")}</option>{ids.map((i:any)=><option key={i.identity} value={i.identity}>{i.identity}</option>)}</Select><Input style={{flex:1}} placeholder={t("admin.test.manualInput")} value={f.source} onChange={(e:any)=>setF({...f,source:e.target.value})}/></div>
        <p className="text-xs text-gray-400 mt-1">{t("admin.identities.domainHint")}</p></div>
      <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("admin.test.to")}</label><Input placeholder={t("admin.test.recipientPlaceholder")} value={f.to} onChange={(e:any)=>setF({...f,to:e.target.value})}/></div>
      <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("admin.test.subject")}</label><Input placeholder={t("admin.test.subjectPlaceholder")} value={f.subject} onChange={(e:any)=>setF({...f,subject:e.target.value})}/></div>
      <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("admin.test.content")}</label><Textarea placeholder={t("admin.test.contentPlaceholder")} value={f.html_body} onChange={(e:any)=>setF({...f,html_body:e.target.value})}/></div>
      <Btn onClick={send} disabled={ld} className="w-full" size="lg">{ld?t("admin.test.sending"):t("admin.test.sendBtn")}</Btn>
    </div>
  </Card></div>;
}
