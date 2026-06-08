"use client";
import React, { useState, useEffect, useRef } from "react";
import { API, authH, useAuth, useToast, Card, Btn, Input, Modal, Badge } from "../../components/shared";
import { useT } from "../../i18n";

export default function AdminBlacklist() {
  const { token } = useAuth();
  const { toast } = useToast();
  const t = useT();
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newReason, setNewReason] = useState("");
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async (p = 1) => {
    const params = new URLSearchParams({ page: String(p), page_size: "20" });
    if (search) params.set("search", search);
    const r = await fetch(`${API}/admin/blacklist?${params}`, { headers: authH(token) });
    if (r.ok) {
      const d = await r.json();
      setItems(d.items || []);
      setTotal(d.total || 0);
      setTotalPages(d.total_pages || 1);
      setPage(p);
    }
  };

  useEffect(() => { load(); }, []);

  const fmtTime = (v: string | null) => {
    if (!v) return "—";
    const s = v.includes("T") && !v.endsWith("Z") && !v.includes("+") && !v.includes("-", 11) ? v + "Z" : v;
    return new Date(s).toLocaleString(undefined, { hour12: false });
  };

  const doAdd = async () => {
    if (!newEmail.trim()) return toast("warning", "请输入邮箱");
    const r = await fetch(`${API}/admin/blacklist`, { method: "POST", headers: authH(token), body: JSON.stringify({ email: newEmail, reason: newReason }) });
    if (r.ok) { toast("success", "已添加"); setShowAdd(false); setNewEmail(""); setNewReason(""); load(page); }
    else { const e = await r.json(); toast("error", e.detail); }
  };

  const doDelete = async (id: number) => {
    const r = await fetch(`${API}/admin/blacklist/${id}`, { method: "DELETE", headers: authH(token) });
    if (r.ok) { toast("success", "已删除"); load(page); }
  };

  const doBatchDelete = async () => {
    if (!selected.length) return;
    const r = await fetch(`${API}/admin/blacklist/batch-delete`, { method: "POST", headers: authH(token), body: JSON.stringify({ ids: selected }) });
    if (r.ok) { toast("success", `已删除 ${selected.length} 条`); setSelected([]); load(page); }
  };

  const doUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await fetch(`${API}/admin/blacklist/upload`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
      if (r.ok) { const d = await r.json(); toast("success", d.message); load(1); }
      else { const d = await r.json(); toast("error", d.detail); }
    } catch { toast("error", "上传失败"); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const toggleSelect = (id: number) => {
    setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  };
  const toggleAll = () => {
    if (selected.length === items.length) setSelected([]);
    else setSelected(items.map(i => i.id));
  };

  return <>
    <Modal open={showAdd} onClose={() => setShowAdd(false)} title="添加黑名单" width={400}>
      <div className="space-y-4">
        <div><label className="text-sm font-medium text-gray-700 mb-1 block">邮箱地址</label><Input placeholder="user@example.com" value={newEmail} onChange={(e: any) => setNewEmail(e.target.value)} /></div>
        <div><label className="text-sm font-medium text-gray-700 mb-1 block">原因（可选）</label><Input placeholder="如：硬退信、无效邮箱" value={newReason} onChange={(e: any) => setNewReason(e.target.value)} /></div>
        <div className="flex justify-end gap-2"><Btn variant="outline" onClick={() => setShowAdd(false)}>取消</Btn><Btn onClick={doAdd}>确认添加</Btn></div>
      </div>
    </Modal>

    <Card title={`邮箱黑名单（${total}）`} extra={
      <div className="flex items-center gap-2 flex-nowrap">
        <Input placeholder="🔍 搜索邮箱" value={search} onChange={(e: any) => setSearch(e.target.value)} className="w-40" onKeyDown={(e: any) => e.key === "Enter" && load(1)} />
        <Btn size="sm" className="whitespace-nowrap" onClick={() => load(1)}>搜索</Btn>
        <Btn size="sm" variant="outline" className="whitespace-nowrap" onClick={() => setShowAdd(true)}>+ 添加</Btn>
        <label className="cursor-pointer">
          <Btn size="sm" variant="outline" className="whitespace-nowrap" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "导入中..." : "📄 批量导入"}
          </Btn>
          <input ref={fileRef} type="file" accept=".txt,.csv,.xlsx" className="hidden" onChange={doUpload} />
        </label>
        <Btn size="sm" variant="outline" className="whitespace-nowrap" onClick={() => { const a=document.createElement("a");a.href=`${API}/admin/blacklist/template`;a.download="blacklist_template.xlsx";a.click(); }}>📥 模板</Btn>
        {selected.length > 0 && <Btn size="sm" variant="warning" className="whitespace-nowrap" onClick={doBatchDelete}>删除选中({selected.length})</Btn>}
      </div>
    }>
      <div className="text-xs text-gray-400 mb-3">黑名单中的邮箱在所有用户发送时会被自动拒绝。支持 .txt/.csv 文件批量导入（每行一个邮箱）。</div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-gray-100 text-left text-xs text-gray-400 uppercase">
            <th className="py-2 px-3 w-8"><input type="checkbox" checked={selected.length === items.length && items.length > 0} onChange={toggleAll} /></th>
            <th className="py-2 px-3 font-medium">邮箱</th>
            <th className="py-2 px-3 font-medium">原因</th>
            <th className="py-2 px-3 font-medium">添加人</th>
            <th className="py-2 px-3 font-medium">添加时间</th>
            <th className="py-2 px-3 font-medium">操作</th>
          </tr></thead>
          <tbody>{items.map(item => <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50 transition">
            <td className="py-2.5 px-3"><input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggleSelect(item.id)} /></td>
            <td className="py-2.5 px-3 font-mono text-xs">{item.email}</td>
            <td className="py-2.5 px-3 text-xs text-gray-500">{item.reason || "—"}</td>
            <td className="py-2.5 px-3 text-xs text-gray-500">{item.created_by}</td>
            <td className="py-2.5 px-3 text-xs text-gray-400">{fmtTime(item.created_at)}</td>
            <td className="py-2.5 px-3"><Btn variant="warning" size="sm" onClick={() => doDelete(item.id)}>删除</Btn></td>
          </tr>)}</tbody>
        </table>
      </div>
      {totalPages > 1 && <div className="flex justify-center gap-2 mt-4">
        <Btn size="sm" variant="outline" disabled={page <= 1} onClick={() => load(page - 1)}>上一页</Btn>
        <span className="text-sm text-gray-500 py-1">{page}/{totalPages}</span>
        <Btn size="sm" variant="outline" disabled={page >= totalPages} onClick={() => load(page + 1)}>下一页</Btn>
      </div>}
    </Card>
  </>;
}
