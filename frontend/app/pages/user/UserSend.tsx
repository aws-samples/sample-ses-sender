"use client";
import React, { useState, useEffect, useRef } from "react";
import { API, authH, useAuth, useToast, Card, Badge, Btn, Select } from "../../components/shared";
import { useT } from "../../i18n";

export default function UserSend() {
  const {token,user}=useAuth(); const {toast}=useToast();
  const t = useT();
  const [ts,setTs]=useState<any[]>([]); const [gs,setGs]=useState<any[]>([]); const [f,setF]=useState({templateId:"",groupId:""}); const [ld,setLd]=useState(false);
  const [progress,setProgress]=useState<any>(null);
  const [quota,setQuota]=useState<{daily_limit:number;today_sent:number;remaining:number}|null>(null);
  const [contactEmail,setContactEmail]=useState("");
  const [editingContact,setEditingContact]=useState(false);
  const [savingContact,setSavingContact]=useState(false);
  const [senderName,setSenderName]=useState("");
  const [editingSender,setEditingSender]=useState(false);
  const [savingSender,setSavingSender]=useState(false);
  const pollRef=useRef<any>(null);

  const loadQuota=async()=>{try{const r=await fetch(`${API}/user/daily-quota`,{headers:authH(token)});if(r.ok)setQuota(await r.json());}catch{}};
  const loadContactEmail=async()=>{try{const r=await fetch(`${API}/auth/me`,{headers:authH(token)});if(r.ok){const d=await r.json();setContactEmail(d.contact_email||d.email||"");setSenderName(d.sender_name||"");}}catch{}};
  const saveContactEmail=async()=>{
    setSavingContact(true);
    try{const r=await fetch(`${API}/user/contact-email`,{method:"PUT",headers:authH(token),body:JSON.stringify({contact_email:contactEmail})});if(r.ok){toast("success","收件邮箱已更新");setEditingContact(false);}else{const e=await r.json();toast("error","更新失败",e.detail);}}catch{toast("error","网络错误");}
    finally{setSavingContact(false);}
  };
  const saveSenderName=async()=>{
    setSavingSender(true);
    try{const r=await fetch(`${API}/user/sender-name`,{method:"PUT",headers:authH(token),body:JSON.stringify({sender_name:senderName})});if(r.ok){toast("success",t("send.senderNameUpdated"));setEditingSender(false);}else{const e=await r.json();toast("error",t("common.failed"),e.detail);}}catch{toast("error",t("common.networkError"));}
    finally{setSavingSender(false);}
  };

  useEffect(()=>{Promise.all([fetch(`${API}/user/templates`,{headers:authH(token)}).then(r=>r.json()),fetch(`${API}/groups`,{headers:authH(token)}).then(r=>r.json())]).then(([t,g])=>{setTs(Array.isArray(t)?t:[]);setGs(Array.isArray(g?.items)?g.items:Array.isArray(g)?g:[]);});loadQuota();loadContactEmail();},[]);
  useEffect(()=>()=>{if(pollRef.current)clearInterval(pollRef.current);},[]);

  const pollProgress=(batchId:string)=>{
    if(pollRef.current)clearInterval(pollRef.current);
    pollRef.current=setInterval(async()=>{
      try{
        const r=await fetch(`${API}/sending-jobs/${batchId}/progress`,{headers:authH(token)});
        if(!r.ok)return;
        const d=await r.json();
        setProgress(d);
        if(d.status==="success"||d.status==="failed"||d.status==="partial"){
          clearInterval(pollRef.current);pollRef.current=null;setLd(false);
          if(d.status==="success")toast("success",t("send.done"),t("send.doneMsg",{sent:d.sent_count,total:d.total_contacts}));
          else if(d.status==="partial")toast("warning",t("send.partialMsg"),d.error_message||"");
          else toast("error",t("send.failedMsg"),d.error_message||"");
          loadQuota();
        }
      }catch{}
    },1500);
  };

  const send=async()=>{
    if(!f.templateId||!f.groupId)return toast("warning",t("send.selectBoth"));
    if(!user.email)return toast("warning",t("send.noEmailConfig"),t("send.contactAdmin"));
    setLd(true);setProgress(null);
    try{
      const r=await fetch(`${API}/send-bulk`,{method:"POST",headers:authH(token),body:JSON.stringify({TemplateId:parseInt(f.templateId),GroupId:parseInt(f.groupId)})});
      const d=await r.json();
      if(r.ok){
        // 后端为异步发送：提交成功即返回，立即解锁。后台由 Sender Engine 处理，关闭页面不影响发送。
        toast("success",t("send.taskCreated"),t("send.sendingBg",{count:d.total_contacts}));
        setProgress({batch_id:d.batch_id,status:"queued",total_contacts:d.total_contacts,sent_count:0,progress:0});
        setLd(false);
        pollProgress(d.batch_id);
      }else{toast("error",t("common.failed"),d.detail);setLd(false);}
    }catch{toast("error",t("common.networkError"));setLd(false);}
  };

  const stText=(s:string)=>({"queued":t("status.queued"),"sending":t("status.sending"),"success":t("send.done"),"partial":t("send.partialMsg"),"failed":t("send.failedMsg")}[s]||s);
  const stColor=(s:string)=>({"queued":"#6B7280","sending":"#3B82F6","success":"#10B981","partial":"#F59E0B","failed":"#EF4444"}[s]||"#6B7280");

  return <div className="w-full flex justify-center"><div className="w-full" style={{maxWidth:640}}><Card title={t("send.title")}>
    <div className="space-y-4">
      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4"><span className="text-sm text-indigo-700">{t("send.fromEmail",{email:user.email||t("send.noEmail")})}</span></div>
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600">收件邮箱：</span>
          {!editingContact?<div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800">{contactEmail||"未设置"}</span>
            <button onClick={()=>setEditingContact(true)} className="text-xs text-indigo-600 hover:text-indigo-800">修改</button>
          </div>:<div className="flex items-center gap-2">
            <input value={contactEmail} onChange={e=>setContactEmail(e.target.value)} className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-indigo-400 w-60" placeholder="your@email.com"/>
            <Btn size="sm" onClick={saveContactEmail} disabled={savingContact}>{savingContact?"保存中":"保存"}</Btn>
            <button onClick={()=>setEditingContact(false)} className="text-xs text-gray-400">取消</button>
          </div>}
        </div>
        <p className="text-xs text-gray-400 mt-1">用于接收发送结果通知等系统邮件</p>
      </div>
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600">{t("send.senderName")}</span>
          {!editingSender?<div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800">{senderName||t("send.senderNameUnset")}</span>
            <button onClick={()=>setEditingSender(true)} className="text-xs text-indigo-600 hover:text-indigo-800">{t("common.edit")}</button>
          </div>:<div className="flex items-center gap-2">
            <input value={senderName} onChange={e=>setSenderName(e.target.value)} className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-indigo-400 w-60"/>
            <Btn size="sm" onClick={saveSenderName} disabled={savingSender}>{savingSender?t("common.savingMsg"):t("common.save")}</Btn>
            <button onClick={()=>setEditingSender(false)} className="text-xs text-gray-400">{t("common.cancel")}</button>
          </div>}
        </div>
        <p className="text-xs text-gray-400 mt-1">{t("send.senderNameHint")}{user.email?`：${senderName?`${senderName} <${user.email}>`:user.email}`:""}</p>
      </div>
      {quota&&<div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600">{t("send.dailyQuota")}</span>
          <span className={`text-sm font-semibold ${quota.remaining<=0?"text-red-500":quota.remaining<100?"text-amber-500":"text-green-600"}`}>
            {t("send.remaining",{count:quota.remaining})}
          </span>
        </div>
        <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-300" style={{
            width:`${Math.min(100,quota.daily_limit>0?(quota.today_sent/quota.daily_limit*100):100)}%`,
            background:quota.remaining<=0?"#EF4444":quota.remaining<100?"#F59E0B":"#10B981"
          }}/>
        </div>
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>{t("send.used",{count:quota.today_sent})}</span>
          <span>{t("send.totalLimit",{limit:quota.daily_limit})}</span>
        </div>
      </div>}
      <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("send.emailTemplate")}</label><Select value={f.templateId} onChange={(e:any)=>setF({...f,templateId:e.target.value})}><option value="">{t("send.selectTemplate")}</option>{ts.map((t:any)=><option key={t.id} value={t.id}>{t.name} - {t.subject}</option>)}</Select></div>
      <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("send.targetGroup")}</label><Select value={f.groupId} onChange={(e:any)=>setF({...f,groupId:e.target.value})}><option value="">{t("send.selectGroup")}</option>{gs.map((g:any)=><option key={g.id} value={g.id}>{g.name}</option>)}</Select></div>
      <Btn onClick={send} disabled={ld||!user.email} className="w-full" size="lg">{ld?t("send.sending"):t("send.startSend")}</Btn>
      {progress&&<div className="bg-gray-50 border border-gray-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium" style={{color:stColor(progress.status)}}>{stText(progress.status)}</span>
          <span className="text-xs text-gray-400 font-mono">{progress.batch_id}</span>
        </div>
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{t("send.progress",{sent:progress.sent_count,total:progress.total_contacts})}</span>
            <span className="font-medium">{progress.progress}%</span>
          </div>
          <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-500" style={{width:`${progress.progress}%`,background:progress.status==="failed"?"#EF4444":progress.status==="success"?"#10B981":"#6366F1"}}/>
          </div>
        </div>
        {(progress.status==="queued"||progress.status==="sending")&&<div className="flex items-center gap-2 text-xs text-gray-400"><span className="inline-block w-3 h-3 border-2 border-gray-300 border-t-transparent rounded-full animate-spin"/>{t("send.bgHint")}</div>}
        {progress.error_message&&<p className="text-xs text-red-500">{progress.error_message}</p>}
      </div>}
    </div>
  </Card></div></div>;
}
