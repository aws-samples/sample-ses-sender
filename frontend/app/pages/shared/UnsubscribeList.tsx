"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, useConfirm, Card, Btn, Input, Pager } from "../../components/shared";

export default function UnsubscribeList() {
  const {token}=useAuth(); const {toast}=useToast(); const {confirm:cfm}=useConfirm();
  const [items,setItems]=useState<any[]>([]);
  const [page,setPage]=useState(1);
  const [total,setTotal]=useState(0);
  const [totalPages,setTotalPages]=useState(1);
  const [search,setSearch]=useState("");
  const [loading,setLoading]=useState(false);
  const [selected,setSelected]=useState<Set<number>>(new Set());

  const load=async(p=1,s=search)=>{
    setLoading(true);setSelected(new Set());
    try{
      const params=new URLSearchParams({page:String(p),page_size:"20"});
      if(s)params.set("search",s);
      const r=await fetch(`${API}/unsubscribe-list?${params}`,{headers:authH(token)});
      const d=await r.json();
      setItems(d.items||[]);setTotal(d.total||0);setTotalPages(d.total_pages||1);setPage(p);
    }catch{}finally{setLoading(false);}
  };

  useEffect(()=>{load();},[]);

  const doSearch=()=>load(1,search);
  const doReset=()=>{setSearch("");load(1,"");};

  const toggleSelect=(id:number)=>{
    setSelected(prev=>{const s=new Set(prev);s.has(id)?s.delete(id):s.add(id);return s;});
  };
  const toggleAll=()=>{
    if(selected.size===items.length) setSelected(new Set());
    else setSelected(new Set(items.map(r=>r.id)));
  };

  const restore=async(r:any)=>{
    if(!await cfm("恢复发送",`确定恢复向「${r.email}」发送邮件吗？`,"确认恢复"))return;
    try{
      const res=await fetch(`${API}/unsubscribe-list/${r.id}`,{method:"DELETE",headers:authH(token)});
      if(res.ok){toast("success","已恢复");load(page);}
      else{const e=await res.json();toast("error","操作失败",e.detail);}
    }catch{toast("error","网络错误");}
  };

  const batchRestore=async()=>{
    if(selected.size===0) return toast("warning","请先选择要恢复的记录");
    if(!await cfm("批量恢复",`确定恢复选中的 ${selected.size} 条退订记录吗？\n恢复后这些邮箱将重新接收邮件。`,"确认恢复"))return;
    try{
      const r=await fetch(`${API}/unsubscribe-list/batch-delete`,{method:"POST",headers:authH(token),body:JSON.stringify({ids:[...selected]})});
      const d=await r.json();
      if(r.ok){toast("success",d.message);load(page);}
      else toast("error","操作失败",d.detail);
    }catch{toast("error","网络错误");}
  };

  const fmtTime=(t:string|null)=>{
    if(!t) return "—";
    const s = t.includes("T")&&!t.endsWith("Z")&&!t.includes("+")&&!t.includes("-",11) ? t+"Z" : t;
    return new Date(s).toLocaleString(undefined,{hour12:false});
  };
  const reasonLabel=(r:string)=>{
    const map:{[k:string]:string}={"one-click":"一键退订","manual":"手动退订","complaint":"投诉退订",
      "web-unsubscribe":"网页退订","too_frequent":"邮件太频繁","not_relevant":"内容不相关",
      "never_subscribed":"未订阅","prefer_other":"偏好其他渠道"};
    if(map[r]) return map[r];
    if(r?.startsWith("other:")) return `其他: ${r.slice(6)}`;
    return r||"—";
  };

  return <Card title="退订用户列表" extra={<Btn variant="secondary" size="sm" onClick={()=>load(page)}>刷新</Btn>}>
    <div className="mb-4 flex gap-3 items-end">
      <div className="flex-1">
        <label className="text-xs font-medium text-gray-500 mb-1 block">搜索退订邮箱</label>
        <Input placeholder="输入邮箱搜索..." value={search} onChange={(e:any)=>setSearch(e.target.value)} onKeyDown={(e:any)=>e.key==="Enter"&&doSearch()}/>
      </div>
      <Btn size="sm" onClick={doSearch}>搜索</Btn>
      <Btn variant="secondary" size="sm" onClick={doReset}>重置</Btn>
    </div>

    <div className="mb-3 flex items-center gap-4 text-xs text-gray-500">
      <span>共 <strong className="text-gray-800">{total}</strong> 个退订邮箱</span>
      {selected.size>0&&(
        <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-1.5">
          <span className="text-indigo-700 font-medium">已选 {selected.size} 条</span>
          <Btn size="sm" variant="warning" onClick={batchRestore}>批量恢复发送</Btn>
          <button onClick={()=>setSelected(new Set())} className="text-gray-400 hover:text-gray-600 text-xs">取消选择</button>
        </div>
      )}
      {loading&&<span className="inline-block w-3 h-3 ml-2 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"/>}
    </div>

    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-gray-400 uppercase border-b border-gray-100">
          <th className="py-2 px-3 w-10">
            <input type="checkbox" className="rounded accent-indigo-500" checked={items.length>0&&selected.size===items.length} onChange={toggleAll}/>
          </th>
          <th className="py-2 px-3 font-medium">退订邮箱</th>
          <th className="py-2 px-3 font-medium">发送邮箱</th>
          <th className="py-2 px-3 font-medium">退订原因</th>
          <th className="py-2 px-3 font-medium">退订时间</th>
          <th className="py-2 px-3 font-medium">操作</th>
        </tr></thead>
        <tbody>{items.map(r=>(
          <tr key={r.id} className={`border-b border-gray-50 hover:bg-gray-50 transition ${selected.has(r.id)?"bg-indigo-50/50":""}`}>
            <td className="py-2.5 px-3">
              <input type="checkbox" className="rounded accent-indigo-500" checked={selected.has(r.id)} onChange={()=>toggleSelect(r.id)}/>
            </td>
            <td className="py-2.5 px-3 font-mono text-xs">{r.email}</td>
            <td className="py-2.5 px-3 text-xs text-gray-500">{r.source_email}</td>
            <td className="py-2.5 px-3"><span className="inline-block px-2 py-0.5 text-xs rounded-full bg-orange-50 text-orange-600 border border-orange-200">{reasonLabel(r.reason)}</span></td>
            <td className="py-2.5 px-3 text-xs text-gray-400">{fmtTime(r.unsubscribed_at)}</td>
            <td className="py-2.5 px-3"><Btn variant="outline" size="sm" onClick={()=>restore(r)}>恢复发送</Btn></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
    {items.length===0&&<p className="text-center py-8 text-sm text-gray-400">{loading?"加载中...":"暂无退订记录"}</p>}
    <Pager page={page} totalPages={totalPages} total={total} onPageChange={p=>load(p)}/>
  </Card>;
}
