"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, Card, Badge, Btn, Pager, Modal } from "../../components/shared";
import { useT } from "../../i18n";

export default function SendingHistory() {
  const {token,user}=useAuth();
  const t = useT();
  const fmtTime=(v:string|null)=>{if(!v) return "-";const s=v.includes("T")&&!v.endsWith("Z")&&!v.includes("+")&&!v.includes("-",11)?v+"Z":v;return new Date(s).toLocaleString(undefined,{hour12:false});};
  const [jobs,setJobs]=useState<any[]>([]); const [page,setPage]=useState(1); const [total,setTotal]=useState(0); const [totalPages,setTotalPages]=useState(1);
  const [showMetrics,setShowMetrics]=useState(false);
  const [metricsJob,setMetricsJob]=useState<any>(null);
  const [metrics,setMetrics]=useState<any>(null);
  const [metricsLoading,setMetricsLoading]=useState(false);
  const [contactEmail,setContactEmail]=useState("");

  const load=async(p=page)=>{
    try{const d=await(await fetch(`${API}/sending-jobs?page=${p}&page_size=10`,{headers:authH(token)})).json();setJobs(d.items||[]);setTotal(d.total||0);setTotalPages(d.total_pages||1);setPage(d.page||1);}catch{setJobs([]);}
  };
  useEffect(()=>{
    load(1);
    fetch(`${API}/auth/me`,{headers:authH(token)}).then(r=>r.json()).then(d=>{setContactEmail(d.contact_email||d.email||"");}).catch(()=>{});
  },[]);

  const openMetrics=async(job:any)=>{
    setMetricsJob(job);setMetrics(null);setShowMetrics(true);setMetricsLoading(true);
    try{
      const mRes=await fetch(`${API}/sending-jobs/${job.batch_id}/metrics`,{headers:authH(token)});
      const mData=await mRes.json(); setMetrics(mData);
    }catch{setMetrics(null);}
    finally{setMetricsLoading(false);}
  };

  const statusBadge=(s:string)=>{
    if(s==="success") return <Badge color="green">{t("status.success")}</Badge>;
    if(s==="partial") return <Badge color="orange">{t("status.partial")}</Badge>;
    if(s==="queued") return <Badge color="gray">{t("status.queued")}</Badge>;
    if(s==="sending") return <Badge color="blue">{t("status.sending")}</Badge>;
    return <Badge color="red">{t("status.failed")}</Badge>;
  };

  const metricCard=(label:string,value:any,rate:number|undefined,color:string)=>(
    <div className="bg-white border border-gray-100 rounded-xl p-4 text-center">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className="text-2xl font-bold" style={{color}}>{value}</p>
      {rate!==undefined&&<p className="text-xs mt-1" style={{color}}>{rate}%</p>}
    </div>
  );

  return <>
    <Modal open={showMetrics} onClose={()=>setShowMetrics(false)} title={t("history.metricsTitle",{batchId:metricsJob?.batch_id||""})} width={720}>
      {metricsLoading?<div className="text-center py-12 text-gray-400">{t("common.loading")}</div>:<div>
        <div className="grid grid-cols-2 gap-3 text-sm mb-4">
          <div><span className="text-gray-400">{t("history.template")}:{" "}</span><span className="text-gray-800">{metricsJob?.template_name}</span></div>
          <div><span className="text-gray-400">{t("history.group")}:{" "}</span><span className="text-gray-800">{metricsJob?.group_name}</span></div>
          <div><span className="text-gray-400">{t("history.sendEmail")}:{" "}</span><span className="text-gray-800">{metricsJob?.source_email}</span></div>
          <div><span className="text-gray-400">{t("history.sendTime")}:{" "}</span><span className="text-gray-800">{fmtTime(metricsJob?.created_at)}</span></div>
        </div>

        {metrics?<div className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              {metricCard(t("history.metricsSend"),metrics.send,undefined,"#3C50E0")}
              {metricCard(t("history.metricsDelivery"),metrics.delivery,metrics.delivery_rate,"#10B981")}
              {metricCard(t("history.metricsOpen"),metrics.open,metrics.open_rate,"#8B5CF6")}
            </div>
            <div className="grid grid-cols-4 gap-3">
              {metricCard(t("history.metricsBounce"),metrics.bounce,metrics.bounce_rate,"#EF4444")}
              {metricCard(t("history.metricsComplaint"),metrics.complaint,undefined,"#F59E0B")}
              {metricCard(t("history.metricsClick"),metrics.click,undefined,"#3B82F6")}
              {metricCard(t("history.metricsReject"),metrics.reject,undefined,"#6B7280")}
            </div>
            <div className="space-y-2">
              <div><div className="flex justify-between text-xs mb-1"><span className="text-gray-500">{t("dashboard.deliveryRate")}</span><span className="font-medium" style={{color:"#10B981"}}>{metrics.delivery_rate}%</span></div><div className="h-2 bg-gray-100 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{width:`${metrics.delivery_rate}%`,background:"#10B981"}}/></div></div>
              <div><div className="flex justify-between text-xs mb-1"><span className="text-gray-500">{t("dashboard.openRate")}</span><span className="font-medium" style={{color:"#8B5CF6"}}>{metrics.open_rate}%</span></div><div className="h-2 bg-gray-100 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{width:`${metrics.open_rate}%`,background:"#8B5CF6"}}/></div></div>
              <div><div className="flex justify-between text-xs mb-1"><span className="text-gray-500">{t("dashboard.bounceRate")}</span><span className="font-medium" style={{color:"#EF4444"}}>{metrics.bounce_rate}%</span></div><div className="h-2 bg-gray-100 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{width:`${metrics.bounce_rate}%`,background:"#EF4444"}}/></div></div>
            </div>
            <p className="text-xs text-gray-400">{t("history.metricsDelay")}</p>
          </div>:<div className="text-center py-12 text-gray-400">{t("history.metricsNoData")}</div>}
      </div>}
    </Modal>

    <Card title={t("history.title")} extra={<Btn variant="outline" size="sm" onClick={()=>load(1)}>{t("common.refresh")}</Btn>}>
      <div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b border-gray-100">{[t("history.batchId"),t("history.template"),t("history.group"),t("history.sendEmail"),"收件邮箱",t("history.contactCount"),t("history.status"),t("history.sendTime"),t("history.actions")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider py-3 px-3 whitespace-nowrap">{h}</th>)}</tr></thead>
        <tbody>{jobs.map((j:any)=>{
          const isSending=j.status==="queued"||j.status==="sending";
          const prog=j.total_contacts>0?Math.round((j.sent_count||0)/j.total_contacts*100):0;
          return <tr key={j.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
          <td className="py-3 px-3 text-xs text-gray-500 font-mono">{j.batch_id}</td>
          <td className="py-3 px-3 text-sm text-gray-800">{j.template_name}</td>
          <td className="py-3 px-3 text-sm text-gray-800">{j.group_name}</td>
          <td className="py-3 px-3 text-sm text-gray-500">{j.source_email}</td>
          <td className="py-3 px-3 text-sm text-gray-500">{j.reply_to||j.source_email}</td>
          <td className="py-3 px-3 text-sm text-gray-600 text-center">{isSending?<span>{j.sent_count||0}/{j.total_contacts}</span>:j.total_contacts}</td>
          <td className="py-3 px-3">
            <div className="flex flex-col gap-1">
              {statusBadge(j.status)}
              {isSending&&<div className="w-24"><div className="h-1.5 bg-gray-200 rounded-full overflow-hidden"><div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{width:`${prog}%`}}/></div><span className="text-[10px] text-gray-400">{prog}%</span></div>}
            </div>
          </td>
          <td className="py-3 px-3 text-xs text-gray-400 whitespace-nowrap">{fmtTime(j.created_at)}</td>
          <td className="py-3 px-3"><Btn variant="primary" size="sm" onClick={()=>openMetrics(j)} disabled={isSending}>{t("history.viewMetrics")}</Btn></td>
        </tr>})}</tbody>
      </table></div>
      {jobs.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t("history.noRecords")}</p>}
      <Pager page={page} totalPages={totalPages} total={total} onPageChange={p=>load(p)}/>
    </Card>
  </>;
}
