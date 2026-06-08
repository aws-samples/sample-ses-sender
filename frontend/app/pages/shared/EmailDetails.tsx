"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, Card, Badge, Btn, Input, Select, Pager } from "../../components/shared";
import { useT } from "../../i18n";

export default function EmailDetails() {
  const {token}=useAuth();
  const t = useT();
  const [items,setItems]=useState<any[]>([]);
  const [page,setPage]=useState(1);
  const [total,setTotal]=useState(0);
  const [totalPages,setTotalPages]=useState(1);
  const [loading,setLoading]=useState(false);

  const [recipient,setRecipient]=useState("");
  const [batchId,setBatchId]=useState("");
  const [sendStatus,setSendStatus]=useState("");
  const [deliveryStatus,setDeliveryStatus]=useState("");

  const load=async(p=1)=>{
    setLoading(true);
    try{
      const params=new URLSearchParams({page:String(p),page_size:"20"});
      if(recipient)params.set("recipient",recipient);
      if(batchId)params.set("batch_id",batchId);
      if(sendStatus)params.set("send_status",sendStatus);
      if(deliveryStatus)params.set("delivery_status",deliveryStatus);
      const r=await fetch(`${API}/email-details?${params}`,{headers:authH(token)});
      const d=await r.json();
      setItems(d.items||[]);setTotal(d.total||0);setTotalPages(d.total_pages||1);setPage(p);
    }catch{}finally{setLoading(false);}
  };

  useEffect(()=>{load();},[]);

  const doSearch=()=>{load(1);};
  const doReset=()=>{setRecipient("");setBatchId("");setSendStatus("");setDeliveryStatus("");setTimeout(()=>load(1),0);};

  const sendBadge=(s:string)=>{
    if(s==="Success")return <Badge color="green">{t("details.statusAccepted")}</Badge>;
    if(s==="Pending")return <Badge color="gray">{t("details.statusPending")}</Badge>;
    if(s==="Unsubscribed")return <Badge color="orange">{t("details.statusUnsub")}</Badge>;
    if(s==="Failed"||s==="MessageRejected")return <Badge color="red">{s}</Badge>;
    return <Badge color="orange">{s||"—"}</Badge>;
  };
  const delivBadge=(s:string|null)=>{
    if(!s)return <span className="text-gray-300">—</span>;
    if(s==="Delivery")return <Badge color="green">{t("details.deliveryDelivered")}</Badge>;
    if(s==="Bounce")return <Badge color="red">{t("details.deliveryBounce")}</Badge>;
    if(s==="Reject")return <Badge color="red">{t("details.deliveryReject")}</Badge>;
    if(s==="Sent")return <Badge color="blue">{t("details.deliverySent")}</Badge>;
    return <Badge color="orange">{s}</Badge>;
  };
  const fmtTime=(t:string|null)=>{
    if(!t) return "—";
    const s = t.includes("T")&&!t.endsWith("Z")&&!t.includes("+")&&!t.includes("-",11) ? t+"Z" : t;
    return new Date(s).toLocaleString(undefined,{hour12:false});
  };

  const doExport=()=>{
    const params=new URLSearchParams();
    if(recipient)params.set("recipient",recipient);
    if(batchId)params.set("batch_id",batchId);
    if(sendStatus)params.set("send_status",sendStatus);
    if(deliveryStatus)params.set("delivery_status",deliveryStatus);
    const url=`${API}/email-details/export?${params}`;
    const a=document.createElement("a");
    a.href=url;
    a.download="email-details.xlsx";
    fetch(url,{headers:authH(token)}).then(r=>r.blob()).then(blob=>{
      const u=URL.createObjectURL(blob);a.href=u;a.click();URL.revokeObjectURL(u);
    });
  };

  return <>
    <Card title={t("details.title")} extra={<div className="flex gap-2"><Btn variant="outline" size="sm" onClick={doExport}>{t("details.exportExcel")}</Btn><Btn variant="secondary" size="sm" onClick={()=>load(page)}>{t("common.refresh")}</Btn></div>}>
      <div className="mb-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
        <div>
          <label className="text-xs font-medium text-gray-500 mb-1 block">{t("details.recipient")}</label>
          <Input placeholder={t("details.searchRecipient")} value={recipient} onChange={(e:any)=>setRecipient(e.target.value)} onKeyDown={(e:any)=>e.key==="Enter"&&doSearch()}/>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 mb-1 block">{t("details.batchId")}</label>
          <Input placeholder={t("details.searchBatch")} value={batchId} onChange={(e:any)=>setBatchId(e.target.value)} onKeyDown={(e:any)=>e.key==="Enter"&&doSearch()}/>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 mb-1 block">{t("details.sendStatus")}</label>
          <Select value={sendStatus} onChange={(e:any)=>setSendStatus(e.target.value)}>
            <option value="">{t("details.statusAll")}</option>
            <option value="Success">{t("details.statusAccepted")}</option>
            <option value="Pending">{t("details.statusPending")}</option>
            <option value="Failed">{t("details.statusFailed")}</option>
            <option value="MessageRejected">{t("details.statusRejected")}</option>
            <option value="Unsubscribed">{t("details.statusUnsub")}</option>
          </Select>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-500 mb-1 block">{t("details.deliveryStatus")}</label>
          <Select value={deliveryStatus} onChange={(e:any)=>setDeliveryStatus(e.target.value)}>
            <option value="">{t("details.deliveryAll")}</option>
            <option value="Delivery">{t("details.deliveryDelivered")}</option>
            <option value="Bounce">{t("details.deliveryBounce")}</option>
            <option value="Sent">{t("details.deliverySent")}</option>
            <option value="Reject">{t("details.deliveryReject")}</option>
          </Select>
        </div>
        <div className="flex gap-2">
          <Btn size="sm" onClick={doSearch} className="flex-1">{t("common.search")}</Btn>
          <Btn variant="secondary" size="sm" onClick={doReset} className="flex-1">{t("common.reset")}</Btn>
        </div>
      </div>

      <div className="mb-3 flex items-center gap-4 text-xs text-gray-500">
        <span>{t("details.total",{count:String(total)})}</span>
        {loading&&<span className="inline-block w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"/>}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-gray-400 uppercase border-b border-gray-100">
            <th className="py-2 px-3 font-medium">{t("details.recipient")}</th>
            <th className="py-2 px-3 font-medium">{t("details.batchId")}</th>
            <th className="py-2 px-3 font-medium">{t("details.template")}</th>
            <th className="py-2 px-3 font-medium">{t("details.group")}</th>
            <th className="py-2 px-3 font-medium">{t("details.sendStatus")}</th>
            <th className="py-2 px-3 font-medium">{t("details.deliveryStatus")}</th>
            <th className="py-2 px-3 font-medium">{t("details.openCount")}</th>
            <th className="py-2 px-3 font-medium">{t("details.clickCount")}</th>
            <th className="py-2 px-3 font-medium">{t("details.deliveryTime")}</th>
            <th className="py-2 px-3 font-medium">{t("details.openTime")}</th>
          </tr></thead>
          <tbody>{items.map((d,i)=><tr key={d.id||i} className="border-b border-gray-50 hover:bg-gray-50 transition">
            <td className="py-2.5 px-3 font-mono text-xs">{d.recipient}</td>
            <td className="py-2.5 px-3"><span className="text-xs text-gray-400 font-mono">{d.batch_id?.slice(0,18)}</span></td>
            <td className="py-2.5 px-3 text-xs text-gray-600">{d.template_name||"—"}</td>
            <td className="py-2.5 px-3 text-xs text-gray-600">{d.group_name||"—"}</td>
            <td className="py-2.5 px-3"><span title={d.send_error||""}>{sendBadge(d.send_status)}{d.send_error&&<span className="ml-1 text-red-400 cursor-help" title={d.send_error}>⚠</span>}</span></td>
            <td className="py-2.5 px-3">{delivBadge(d.delivery_status)}</td>
            <td className="py-2.5 px-3 text-center">{d.open_count>0?<span className="text-green-600 font-medium">{t("details.times",{count:d.open_count})}</span>:<span className="text-gray-300">—</span>}</td>
            <td className="py-2.5 px-3 text-center">{d.click_count>0?<span className="text-blue-600 font-medium">{t("details.times",{count:d.click_count})}</span>:<span className="text-gray-300">—</span>}</td>
            <td className="py-2.5 px-3 text-xs text-gray-500">{fmtTime(d.delivery_time)}</td>
            <td className="py-2.5 px-3 text-xs text-gray-500">{fmtTime(d.first_open_time)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {items.length===0&&<p className="text-center py-8 text-sm text-gray-400">{loading?t("common.loading"):t("details.noData")}</p>}
      <Pager page={page} totalPages={totalPages} total={total} onPageChange={p=>load(p)}/>
    </Card>
  </>;
}
