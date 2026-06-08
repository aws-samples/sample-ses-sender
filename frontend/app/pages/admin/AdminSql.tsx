"use client";
import React, { useState } from "react";
import { API, authH, useAuth, useToast, Card, Btn } from "../../components/shared";

export default function AdminSql() {
  const {token}=useAuth(); const {toast}=useToast();
  const [sql,setSql]=useState("SELECT * FROM users LIMIT 10;");
  const [loading,setLoading]=useState(false);
  const [result,setResult]=useState<any>(null);
  const [error,setError]=useState("");
  const [allowWrite,setAllowWrite]=useState(false);
  const [history,setHistory]=useState<string[]>([]);

  const execute=async()=>{
    if(!sql.trim()) return toast("warning","请输入 SQL");
    setLoading(true);setError("");setResult(null);
    try{
      const r=await fetch(`${API}/admin/sql`,{method:"POST",headers:authH(token),body:JSON.stringify({sql:sql.trim(),allow_write:allowWrite})});
      const d=await r.json();
      if(r.ok){
        setResult(d);
        setHistory(prev=>{const h=[sql.trim(),...prev.filter(s=>s!==sql.trim())].slice(0,20);return h;});
        if(d.message) toast("success",d.message);
      } else {
        setError(d.detail||"执行失败");
      }
    }catch{setError("网络错误");}
    finally{setLoading(false);}
  };

  return <div className="space-y-4">
    <Card title="SQL 控制台" extra={<span className="text-xs text-red-400">仅管理员可用</span>}>
      <div className="space-y-3">
        <div>
          <textarea
            value={sql}
            onChange={e=>setSql(e.target.value)}
            onKeyDown={e=>{if(e.key==="Enter"&&(e.metaKey||e.ctrlKey)){e.preventDefault();execute();}}}
            placeholder="输入 SQL 查询语句..."
            className="w-full border border-gray-200 rounded-lg p-4 text-sm font-mono resize-none outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-300"
            style={{minHeight:120,background:"#1e1e2e",color:"#a6e3a1",caretColor:"#fff"}}
            spellCheck={false}
          />
          <p className="text-xs text-gray-400 mt-1">Ctrl+Enter 执行 | 支持 SELECT / SHOW / DESCRIBE / EXPLAIN</p>
        </div>
        <div className="flex items-center gap-4">
          <Btn onClick={execute} disabled={loading}>{loading?"执行中...":"执行 SQL"}</Btn>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" className="rounded accent-red-500" checked={allowWrite} onChange={e=>setAllowWrite(e.target.checked)}/>
            <span className={allowWrite?"text-red-600 font-medium":"text-gray-500"}>允许写操作 (INSERT/UPDATE/DELETE)</span>
          </label>
          {result&&<span className="text-xs text-gray-400">{result.row_count} 行</span>}
        </div>

        {error&&<div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600 font-mono whitespace-pre-wrap">{error}</div>}

        {result&&result.columns?.length>0&&(
          <div className="overflow-x-auto border border-gray-200 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>{result.columns.map((col:string)=><th key={col} className="text-left px-3 py-2 text-xs font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap">{col}</th>)}</tr>
              </thead>
              <tbody>{result.rows.map((row:any,i:number)=>(
                <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                  {result.columns.map((col:string)=><td key={col} className="px-3 py-2 text-xs text-gray-700 font-mono whitespace-nowrap max-w-xs truncate" title={String(row[col]??"")}>
                    {row[col]===null?<span className="text-gray-300 italic">NULL</span>:String(row[col]).length>100?String(row[col]).slice(0,100)+"...":String(row[col])}
                  </td>)}
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}

        {result&&result.message&&!result.columns?.length&&(
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-700">{result.message}</div>
        )}
      </div>
    </Card>

    {history.length>0&&<Card title="历史查询">
      <div className="space-y-1 max-h-40 overflow-y-auto">
        {history.map((h,i)=>(
          <div key={i} onClick={()=>setSql(h)} className="px-3 py-1.5 text-xs font-mono text-gray-600 hover:bg-indigo-50 rounded cursor-pointer truncate">{h}</div>
        ))}
      </div>
    </Card>}
  </div>;
}
