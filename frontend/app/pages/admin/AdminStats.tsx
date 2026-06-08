"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, Card, Badge, Btn, Pager } from "../../components/shared";
import { useT } from "../../i18n";

export default function AdminStats() {
  const {token}=useAuth(); const t=useT();
  const fmtTime=(v:string|null)=>{if(!v) return "-";const s=v.includes("T")&&!v.endsWith("Z")&&!v.includes("+")&&!v.includes("-",11)?v+"Z":v;return new Date(s).toLocaleString(undefined,{hour12:false});};
  const [stats,setStats]=useState<any>(null);
  const [jobs,setJobs]=useState<any[]>([]); const [page,setPage]=useState(1); const [total,setTotal]=useState(0); const [totalPages,setTotalPages]=useState(1);

  const loadStats=async()=>{try{setStats(await(await fetch(`${API}/admin/sending-stats`,{headers:authH(token)})).json());}catch{}};
  const loadJobs=async(p=1)=>{try{const d=await(await fetch(`${API}/admin/sending-jobs?page=${p}&page_size=10`,{headers:authH(token)})).json();setJobs(d.items||[]);setTotal(d.total||0);setTotalPages(d.total_pages||1);setPage(d.page||1);}catch{setJobs([]);}};
  useEffect(()=>{loadStats();loadJobs(1);},[]);

  const statCard=(label:string,value:any,sub:string,color:string)=>(
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <p className="text-sm text-gray-400">{label}</p>
      <p className="text-3xl font-bold mt-1" style={{color}}>{value}</p>
      {sub&&<p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );

  return <div className="space-y-6">
    {stats?.summary&&<div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {statCard(t("admin.stats.totalUsers"),stats.summary.total_users,t("admin.stats.usersSub"),"#3C50E0")}
      {statCard(t("admin.stats.totalJobs"),stats.summary.total_jobs,t("admin.stats.jobsSub"),"#8B5CF6")}
      {statCard(t("admin.stats.totalContacts"),stats.summary.total_contacts,t("admin.stats.contactsSub"),"#10B981")}
      {statCard(t("admin.stats.successRate"),stats.summary.success_rate+"%",t("admin.stats.rateSub"),"#F59E0B")}
    </div>}

    <Card title={t("admin.stats.userStatsTitle")} extra={<Btn variant="outline" size="sm" onClick={()=>{loadStats();loadJobs(1);}}>{t("common.refresh")}</Btn>}>
      <div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b border-gray-100">{[t("admin.stats.colUsername"),t("admin.stats.colDisplayName"),t("admin.stats.colSendEmail"),t("admin.stats.colBatches"),t("admin.stats.colContacts"),t("admin.stats.colSuccess"),t("admin.stats.colFailed"),t("admin.stats.colFirstSend"),t("admin.stats.colLastSend")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider py-3 px-3 whitespace-nowrap">{h}</th>)}</tr></thead>
        <tbody>{(stats?.users||[]).map((u:any)=><tr key={u.user_id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
          <td className="py-3 px-3 text-sm font-medium text-gray-800">{u.username}</td>
          <td className="py-3 px-3 text-sm text-gray-600">{u.display_name}</td>
          <td className="py-3 px-3 text-sm text-gray-500">{u.email||"-"}</td>
          <td className="py-3 px-3 text-sm text-gray-800 text-center font-medium">{u.total_jobs}</td>
          <td className="py-3 px-3 text-sm text-center font-medium" style={{color:"#3C50E0"}}>{u.total_contacts}</td>
          <td className="py-3 px-3 text-center"><Badge color="green">{u.success_count}</Badge></td>
          <td className="py-3 px-3 text-center">{u.failed_count>0?<Badge color="red">{u.failed_count}</Badge>:<span className="text-gray-300">0</span>}</td>
          <td className="py-3 px-3 text-xs text-gray-400 whitespace-nowrap">{fmtTime(u.first_send)}</td>
          <td className="py-3 px-3 text-xs text-gray-400 whitespace-nowrap">{fmtTime(u.last_send)}</td>
        </tr>)}</tbody>
      </table></div>
      {(!stats?.users||stats.users.length===0)&&<p className="text-center py-8 text-sm text-gray-400">{t("admin.stats.noSendData")}</p>}
    </Card>

    <Card title={t("admin.stats.allRecordsTitle")}>
      <div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b border-gray-100">{[t("admin.stats.colBatchId"),t("admin.stats.colUser"),t("admin.stats.colTemplate"),t("admin.stats.colGroup"),t("admin.stats.colEmail"),t("admin.stats.colCount"),t("admin.stats.colStatus"),t("admin.stats.colSendTime")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider py-3 px-3 whitespace-nowrap">{h}</th>)}</tr></thead>
        <tbody>{jobs.map((j:any)=><tr key={j.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
          <td className="py-3 px-3 text-xs text-gray-500 font-mono">{j.batch_id}</td>
          <td className="py-3 px-3 text-sm text-gray-800">{j.display_name||j.username}</td>
          <td className="py-3 px-3 text-sm text-gray-600">{j.template_name}</td>
          <td className="py-3 px-3 text-sm text-gray-600">{j.group_name}</td>
          <td className="py-3 px-3 text-sm text-gray-500">{j.source_email}</td>
          <td className="py-3 px-3 text-sm text-gray-800 text-center">{j.total_contacts}</td>
          <td className="py-3 px-3">{j.status==="success"?<Badge color="green">{t("admin.stats.statusSuccess")}</Badge>:j.status==="partial"?<Badge color="orange">{t("admin.stats.statusPartial")}</Badge>:j.status==="queued"?<Badge color="gray">{t("admin.stats.statusQueued")}</Badge>:j.status==="sending"?<Badge color="blue">{t("admin.stats.statusSending")}</Badge>:<Badge color="red">{t("admin.stats.statusFailed")}</Badge>}</td>
          <td className="py-3 px-3 text-xs text-gray-400 whitespace-nowrap">{fmtTime(j.created_at)}</td>
        </tr>)}</tbody>
      </table></div>
      {jobs.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t("admin.stats.noSendRecords")}</p>}
      <Pager page={page} totalPages={totalPages} total={total} onPageChange={p=>loadJobs(p)}/>
    </Card>
  </div>;
}
