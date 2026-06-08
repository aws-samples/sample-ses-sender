"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, Card } from "../../components/shared";
import { useT } from "../../i18n";

export default function UserDashboard() {
  const {token}=useAuth();
  const t = useT();
  const fmtTime=(v:string|null)=>{if(!v) return "-";const s=v.includes("T")&&!v.endsWith("Z")&&!v.includes("+")&&!v.includes("-",11)?v+"Z":v;return new Date(s).toLocaleString(undefined,{hour12:false});};
  const [data,setData]=useState<any>(null);
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    (async()=>{
      try{
        const r=await fetch(`${API}/user/dashboard`,{headers:authH(token)});
        if(r.ok) setData(await r.json());
      }catch{}
      finally{setLoading(false);}
    })();
  },[]);

  if(loading) return <div className="flex items-center justify-center h-64 text-gray-400">{t("common.loading")}</div>;
  if(!data) return <div className="flex items-center justify-center h-64 text-gray-400">{t("common.noData")}</div>;

  const {summary:s, delivery:d, daily_trend:trend, recent_jobs:recent}=data;
  const pct=(v:number,total:number)=>total>0?(v/total*100).toFixed(1):"0.0";
  const quotaPct=s.daily_limit>0?Math.min(100,s.today_sent/s.daily_limit*100):0;
  const quotaColor=quotaPct>=100?"#EF4444":quotaPct>=80?"#F59E0B":"#10B981";
  const maxTrend=Math.max(...trend.map((t:any)=>t.count),1);

  const statCards=[
    {label:t("dashboard.todaySent"),value:s.today_sent,sub:t("dashboard.dailyLimit",{limit:s.daily_limit}),icon:"📮",color:"#6366F1",bg:"#EEF2FF"},
    {label:t("dashboard.monthSent"),value:s.month_sent,sub:t("dashboard.monthLabel",{month:new Date().getMonth()+1}),icon:"📅",color:"#8B5CF6",bg:"#F5F3FF"},
    {label:t("dashboard.totalEmails"),value:s.total_emails,sub:t("dashboard.batchCount",{count:s.total_jobs}),icon:"📊",color:"#06B6D4",bg:"#ECFEFF"},
    {label:t("dashboard.successJobs"),value:s.success_jobs,sub:t("dashboard.failedCount",{count:s.failed_jobs}),icon:"✅",color:"#10B981",bg:"#ECFDF5"},
  ];

  const deliveryCards=[
    {label:t("dashboard.deliveryRate"),value:`${pct(d.delivered,d.total)}%`,count:d.delivered,color:"#10B981",bg:"bg-green-50",ring:"ring-green-200"},
    {label:t("dashboard.openRate"),value:`${pct(d.opened,d.total)}%`,count:d.opened,color:"#3B82F6",bg:"bg-blue-50",ring:"ring-blue-200"},
    {label:t("dashboard.clickRate"),value:`${pct(d.clicked,d.total)}%`,count:d.clicked,color:"#8B5CF6",bg:"bg-purple-50",ring:"ring-purple-200"},
    {label:t("dashboard.bounceRate"),value:`${pct(d.bounced,d.total)}%`,count:d.bounced,color:"#EF4444",bg:"bg-red-50",ring:"ring-red-200"},
    {label:t("dashboard.complaintRate"),value:`${pct(d.complained,d.total)}%`,count:d.complained,color:"#F59E0B",bg:"bg-amber-50",ring:"ring-amber-200"},
  ];

  const stColor:Record<string,string>={"success":"#10B981","failed":"#EF4444","sending":"#3B82F6","queued":"#6B7280","partial":"#F59E0B"};
  const stText:Record<string,string>={"success":t("status.success"),"failed":t("status.failed"),"sending":t("status.sending"),"queued":t("status.queued"),"partial":t("status.partial")};

  return <div className="space-y-6">
    <div className="grid grid-cols-4 gap-4">
      {statCards.map(c=><div key={c.label} className="rounded-2xl p-5 border border-gray-100 shadow-sm" style={{background:c.bg}}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-2xl">{c.icon}</span>
          <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{color:c.color,background:`${c.color}18`}}>{c.sub}</span>
        </div>
        <p className="text-3xl font-bold" style={{color:c.color}}>{c.value.toLocaleString()}</p>
        <p className="text-sm text-gray-500 mt-1">{c.label}</p>
      </div>)}
    </div>

    <Card>
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">{t("dashboard.dailyQuota")}</span>
            <span className="text-sm" style={{color:quotaColor}}>
              {s.today_sent} / {s.daily_limit} <span className="text-gray-400 text-xs ml-1">({t("dashboard.remaining",{count:s.daily_remaining})})</span>
            </span>
          </div>
          <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-500" style={{width:`${quotaPct}%`,background:quotaColor}}/>
          </div>
        </div>
      </div>
    </Card>

    <div className="grid grid-cols-2 gap-6">
      <Card title={t("dashboard.trend7d")}>
        <div className="flex items-end gap-2 h-40 pt-2">
          {trend.map((t:any)=>{
            const h=maxTrend>0?(t.count/maxTrend*100):0;
            return <div key={t.date} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-xs font-medium text-gray-600">{t.count>0?t.count:""}</span>
              <div className="w-full rounded-t-lg transition-all duration-300" style={{height:`${Math.max(h,4)}%`,background:t.count>0?"#6366F1":"#E5E7EB",minHeight:4}}/>
              <span className="text-xs text-gray-400">{t.date}</span>
            </div>;
          })}
        </div>
      </Card>

      <Card title={`${t("dashboard.deliveryMetrics")}${d.total>0?` (${t("dashboard.deliveryTotal",{count:d.total})})`:""}`}>
        <div className="space-y-3">
          {deliveryCards.map(c=>{
            const pctVal=d.total>0?(c.count/d.total*100):0;
            return <div key={c.label} className="flex items-center gap-3">
              <span className="text-sm text-gray-600 w-14">{c.label}</span>
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all" style={{width:`${pctVal}%`,background:c.color}}/>
              </div>
              <span className="text-sm font-semibold w-16 text-right" style={{color:c.color}}>{c.value}</span>
              <span className="text-xs text-gray-400 w-10 text-right">{c.count}</span>
            </div>;
          })}
        </div>
      </Card>
    </div>

    <Card title={t("dashboard.recentSends")}>
      {recent.length===0?<p className="text-center py-6 text-sm text-gray-400">{t("dashboard.noRecords")}</p>:
      <div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b border-gray-100">
          {[t("history.batchId"),t("history.template"),t("history.group"),t("history.contactCount"),t("history.status"),t("history.sendTime")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 py-2.5 px-3">{h}</th>)}
        </tr></thead>
        <tbody>{recent.map((j:any)=><tr key={j.batch_id} className="border-b border-gray-50 hover:bg-gray-50/50">
          <td className="py-2.5 px-3 text-xs font-mono text-gray-500">{j.batch_id.replace("batch-","").slice(0,8)}</td>
          <td className="py-2.5 px-3 text-sm text-gray-700">{j.template_name}</td>
          <td className="py-2.5 px-3 text-sm text-gray-500">{j.group_name}</td>
          <td className="py-2.5 px-3 text-sm font-medium text-gray-700">{j.total_contacts}</td>
          <td className="py-2.5 px-3"><span className="inline-block text-xs font-medium px-2 py-0.5 rounded-full" style={{color:stColor[j.status]||"#6B7280",background:`${stColor[j.status]||"#6B7280"}15`}}>{stText[j.status]||j.status}</span></td>
          <td className="py-2.5 px-3 text-xs text-gray-400">{fmtTime(j.created_at)}</td>
        </tr>)}</tbody>
      </table></div>}
    </Card>
  </div>;
}
