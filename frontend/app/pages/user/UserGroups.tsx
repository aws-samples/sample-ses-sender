"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, useConfirm, Card, Btn, Input, Pager, Modal } from "../../components/shared";
import { useT } from "../../i18n";

export default function UserGroups() {
  const {token}=useAuth(); const {toast}=useToast(); const {confirm:cfm}=useConfirm(); const t=useT();
  const [gs,setGs]=useState<any[]>([]); const [gS,setGS]=useState(""); const [gP,setGP]=useState(1); const [gT,setGT]=useState(0); const [gTP,setGTP]=useState(1);
  const [sel,setSel]=useState<number|null>(null); const [cs,setCs]=useState<any[]>([]); const [cS,setCS]=useState(""); const [cP,setCP]=useState(1); const [cT,setCT]=useState(0); const [cTP,setCTP]=useState(1);

  const [showAddGroup,setShowAddGroup]=useState(false);
  const [showEditGroup,setShowEditGroup]=useState(false);
  const [editGroupId,setEditGroupId]=useState<number|null>(null);
  const [ng,setNg]=useState("");
  const [ngDesc,setNgDesc]=useState("");
  const [showAddContact,setShowAddContact]=useState(false);
  const [rows,setRows]=useState([{name:"",email:"",attrKeys:[""],attrVals:[""]}] as any[]);

  const PAGE_SIZE = 10;
  const loadG=async(p=gP,s=gS)=>{try{const d=await(await fetch(`${API}/groups?page=${p}&page_size=${PAGE_SIZE}&search=${encodeURIComponent(s)}`,{headers:authH(token)})).json();setGs(d.items||[]);setGT(d.total||0);setGTP(d.total_pages||1);setGP(d.page||1);}catch{setGs([]);}};
  useEffect(()=>{loadG(1,"");},[]);
  const searchG=(v:string)=>{setGS(v);loadG(1,v);};
  const loadC=async(gid:number,p=1,s="")=>{try{const d=await(await fetch(`${API}/groups/${gid}/contacts?page=${p}&page_size=${PAGE_SIZE}&search=${encodeURIComponent(s)}`,{headers:authH(token)})).json();setCs(d.items||[]);setCT(d.total||0);setCTP(d.total_pages||1);setCP(d.page||1);setSel(gid);}catch{setCs([]);}};
  const searchC=(v:string)=>{setCS(v);if(sel)loadC(sel,1,v);};

  const addG=async()=>{if(!ng)return toast("warning",t("groups.enterName"));await fetch(`${API}/groups`,{method:"POST",headers:authH(token),body:JSON.stringify({name:ng,description:ngDesc})});toast("success",t("groups.created"));setNg("");setNgDesc("");setShowAddGroup(false);loadG(1,gS);};
  const openEditG=(g:any)=>{setEditGroupId(g.id);setNg(g.name);setNgDesc(g.description||"");setShowEditGroup(true);};
  const updateG=async()=>{if(!ng)return toast("warning",t("groups.enterName"));const r=await fetch(`${API}/groups/${editGroupId}`,{method:"PUT",headers:authH(token),body:JSON.stringify({name:ng,description:ngDesc})});if(r.ok){toast("success",t("groups.updated"));setShowEditGroup(false);loadG(gP,gS);}else{const e=await r.json();toast("error",t("groups.updateFailed"),e.detail);}};
  const delG=async(g:any)=>{if(!await cfm(t("groups.deleteTitle"),t("groups.deleteBody",{name:g.name,count:g.contact_count}),t("groups.confirmDelete")))return;await fetch(`${API}/groups/${g.id}`,{method:"DELETE",headers:authH(token)});if(sel===g.id){setSel(null);setCs([]);}loadG(gP,gS);};

  const updR=(i:number,f:string,v:string)=>{const r=[...rows];(r[i] as any)[f]=v;setRows(r);};
  const addR=()=>setRows([...rows,{name:"",email:"",attrKeys:[""],attrVals:[""]}]);
  const rmR=(i:number)=>{if(rows.length>1)setRows(rows.filter((_,j)=>j!==i));};
  const updAttr=(ri:number,ai:number,field:"key"|"val",v:string)=>{const r=[...rows];if(field==="key")r[ri].attrKeys[ai]=v;else r[ri].attrVals[ai]=v;setRows(r);};
  const addAttrRow=(ri:number)=>{const r=[...rows];r[ri].attrKeys.push("");r[ri].attrVals.push("");setRows(r);};
  const rmAttrRow=(ri:number,ai:number)=>{const r=[...rows];r[ri].attrKeys.splice(ai,1);r[ri].attrVals.splice(ai,1);setRows(r);};
  const buildAttrs=(r:any)=>{const o:any={};(r.attrKeys||[]).forEach((k:string,i:number)=>{const key=k.trim(),val=(r.attrVals[i]||"").trim();if(key&&val)o[key]=val;});return Object.keys(o).length?JSON.stringify(o):null;};
  const saveC=async()=>{const v=rows.filter(r=>r.email.trim());if(!v.length)return toast("warning",t("groups.fillEmail"));for(const r of v)await fetch(`${API}/contacts`,{method:"POST",headers:authH(token),body:JSON.stringify({name:r.name.trim(),email:r.email.trim(),attributes:buildAttrs(r),group_id:sel})});toast("success",t("groups.contactsAdded",{count:v.length}));setRows([{name:"",email:"",attrKeys:[""],attrVals:[""]}]);setShowAddContact(false);loadC(sel!,cP,cS);loadG(gP,gS);};
  const delC=async(c:any)=>{if(!await cfm(t("groups.contactDeleteTitle"),t("groups.contactDeleteBody",{name:c.name||c.email,email:c.email}),t("groups.confirmDelete")))return;await fetch(`${API}/contacts/${c.id}`,{method:"DELETE",headers:authH(token)});loadC(sel!,cP,cS);loadG(gP,gS);};

  const dlTpl=()=>window.open(`${API}/contacts/template/download?token=${token}`,"_blank");
  const dlCs=()=>{if(sel)window.open(`${API}/groups/${sel}/contacts/download?token=${token}`,"_blank");};
  const ulCs=async(e:any)=>{const file=e.target.files[0];if(!file||!sel)return;const fd=new FormData();fd.append("file",file);const r=await fetch(`${API}/groups/${sel}/contacts/upload`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body:fd});const d=await r.json();if(r.ok){toast("success",t("groups.importSuccess"),d.message);loadC(sel,1,cS);loadG(gP,gS);}else toast("error",t("groups.importFailed"),d.detail);e.target.value="";};

  return <>
    <Modal open={showAddGroup} onClose={()=>setShowAddGroup(false)} title={t("groups.createTitle")} width={440}>
      <div className="space-y-4">
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("groups.name")}</label><Input placeholder={t("groups.namePlaceholder")} value={ng} onChange={(e:any)=>setNg(e.target.value)} onKeyDown={(e:any)=>e.key==="Enter"&&addG()}/></div>
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("groups.descLabel")}</label><Input placeholder={t("groups.descPlaceholder")} value={ngDesc} onChange={(e:any)=>setNgDesc(e.target.value)}/></div>
        <div className="flex justify-end gap-2"><Btn variant="outline" onClick={()=>setShowAddGroup(false)}>{t("common.cancel")}</Btn><Btn onClick={addG}>{t("groups.createBtn")}</Btn></div>
      </div>
    </Modal>

    <Modal open={showEditGroup} onClose={()=>setShowEditGroup(false)} title={t("groups.editTitle")} width={440}>
      <div className="space-y-4">
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("groups.name")}</label><Input value={ng} onChange={(e:any)=>setNg(e.target.value)}/></div>
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("groups.description")}</label><Input placeholder={t("groups.descPlaceholder")} value={ngDesc} onChange={(e:any)=>setNgDesc(e.target.value)}/></div>
        <div className="flex justify-end gap-2"><Btn variant="outline" onClick={()=>setShowEditGroup(false)}>{t("common.cancel")}</Btn><Btn onClick={updateG}>{t("groups.saveChanges")}</Btn></div>
      </div>
    </Modal>

    <Modal open={showAddContact} onClose={()=>setShowAddContact(false)} title={t("groups.addContact")} width={640}>
      <div className="space-y-3 max-h-[60vh] overflow-y-auto">
        {rows.map((r,i)=><div key={i} className="border border-gray-100 rounded-lg p-3 space-y-2">
          <div className="flex gap-2 items-center">
            <Input placeholder={t("groups.contactName")} value={r.name} onChange={(e:any)=>updR(i,"name",e.target.value)}/>
            <Input placeholder={t("groups.emailRequired")} value={r.email} onChange={(e:any)=>updR(i,"email",e.target.value)}/>
            {rows.length>1&&<button onClick={()=>rmR(i)} className="text-gray-400 hover:text-red-500 text-xl leading-none px-1 flex-shrink-0">&times;</button>}
          </div>
          <div className="pl-1">
            <span className="text-xs text-gray-400 mb-1 block">{t("groups.attrHint")} {"{{key}}"}</span>
            {(r.attrKeys||[""]).map((_:any,ai:number)=><div key={ai} className="flex gap-2 items-center mb-1">
              <input className="h-8 px-2 border border-gray-200 rounded text-xs text-gray-700 w-28 outline-none focus:border-indigo-400" placeholder={t("groups.attrName")} value={r.attrKeys[ai]||""} onChange={(e:any)=>updAttr(i,ai,"key",e.target.value)}/>
              <span className="text-gray-300">=</span>
              <input className="h-8 px-2 border border-gray-200 rounded text-xs text-gray-700 flex-1 outline-none focus:border-indigo-400" placeholder={t("groups.attrValue")} value={r.attrVals[ai]||""} onChange={(e:any)=>updAttr(i,ai,"val",e.target.value)}/>
              {(r.attrKeys||[]).length>1&&<button onClick={()=>rmAttrRow(i,ai)} className="text-gray-300 hover:text-red-400 text-sm">&times;</button>}
            </div>)}
            <button onClick={()=>addAttrRow(i)} className="text-xs text-indigo-500 hover:text-indigo-700">{t("groups.addAttr")}</button>
          </div>
        </div>)}
        <Btn variant="outline" size="sm" onClick={addR}>{t("groups.addRow")}</Btn>
        <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
          <Btn variant="outline" onClick={()=>setShowAddContact(false)}>{t("common.cancel")}</Btn>
          <Btn variant="success" onClick={saveC}>{t("groups.batchSave")}</Btn>
        </div>
      </div>
    </Modal>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <Card title={t("groups.title")} extra={<Btn size="sm" onClick={()=>{setNg("");setShowAddGroup(true);}}>{t("groups.create")}</Btn>}>
        <Input placeholder={t("groups.searchPlaceholder")} value={gS} onChange={(e:any)=>searchG(e.target.value)} className="mb-4"/>
        <div className="space-y-1">{gs.map((g:any)=><div key={g.id} onClick={()=>{setCS("");loadC(g.id,1,"");}} className={`flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition ${sel===g.id?"bg-indigo-50 text-indigo-700":"hover:bg-gray-50 text-gray-700"}`}>
          <span className={`text-sm ${sel===g.id?"font-semibold":""}`}>{g.name} <span className="text-xs text-gray-400">({g.contact_count})</span></span>
          <div className="flex gap-1">
            <Btn variant="outline" size="sm" onClick={(e:any)=>{e.stopPropagation();openEditG(g);}}>{t("common.edit")}</Btn>
            <Btn variant="danger" size="sm" onClick={(e:any)=>{e.stopPropagation();delG(g);}}>{t("common.delete")}</Btn>
          </div>
        </div>)}{gs.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t("groups.noGroups")}</p>}</div>
        <Pager page={gP} totalPages={gTP} total={gT} onPageChange={p=>loadG(p,gS)}/>
      </Card>

      <div className="lg:col-span-2"><Card title={sel?t("groups.contactManager"):t("groups.selectGroup")} extra={sel&&<div className="flex gap-2">
        <Btn variant="outline" size="sm" onClick={dlTpl}>{t("groups.downloadTemplate")}</Btn>
        <label className="inline-flex items-center justify-center font-medium rounded-lg transition h-8 px-3 text-xs border border-gray-200 text-gray-600 hover:bg-gray-50 bg-white cursor-pointer">{t("groups.excelImport")}<input type="file" accept=".xlsx,.xls" className="hidden" onChange={ulCs}/></label>
        <Btn variant="outline" size="sm" onClick={dlCs}>{t("groups.excelExport")}</Btn>
        <Btn variant="success" size="sm" onClick={()=>{setRows([{name:"",email:"",attrKeys:[""],attrVals:[""]}]);setShowAddContact(true);}}>{t("groups.addContact")}</Btn>
      </div>}>
        {sel?<>
          <div className="flex items-center gap-3 mb-4"><Input placeholder={t("groups.searchContact")} value={cS} onChange={(e:any)=>searchC(e.target.value)}/><span className="text-sm text-gray-400 whitespace-nowrap">{t("groups.totalContacts",{count:cT})}</span></div>
          <div className="overflow-x-auto"><table className="w-full">
            <thead><tr className="border-b border-gray-100">{[t("groups.contactName"),t("groups.email"),t("groups.attributes"),t("groups.tableActions")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider py-3 px-4">{h}</th>)}</tr></thead>
            <tbody>{cs.map((c:any)=>{
              let attrPreview="";
              try{const a=c.attributes?JSON.parse(c.attributes):{};attrPreview=Object.entries(a).map(([k,v])=>`${k}: ${v}`).join(", ");}catch{}
              return <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
              <td className="py-3 px-4 text-sm text-gray-800">{c.name}</td>
              <td className="py-3 px-4 text-sm text-gray-500">{c.email}</td>
              <td className="py-3 px-4 text-xs text-gray-400 max-w-[200px] truncate" title={attrPreview}>{attrPreview||"—"}</td>
              <td className="py-3 px-4"><Btn variant="danger" size="sm" onClick={()=>delC(c)}>{t("common.delete")}</Btn></td>
            </tr>})}</tbody>
          </table></div>
          {cs.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t("groups.noContacts")}</p>}
          <Pager page={cP} totalPages={cTP} total={cT} onPageChange={p=>loadC(sel,p,cS)}/>
        </>:<p className="text-center py-16 text-gray-400">{t("groups.selectGroupHint")}</p>}
      </Card></div>
    </div>
  </>;
}
