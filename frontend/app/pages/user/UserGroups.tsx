"use client";
import React, { useState, useEffect, useRef } from "react";
import { API, authH, useAuth, useToast, useConfirm, Badge, Card, Btn, Input, Pager, Modal } from "../../components/shared";
import { useLocale } from "../../i18n";

type Contact = {
  id: number;
  name: string | null;
  email: string;
  attributes: string | null;
  is_blacklisted: boolean;
  blacklist_sources: ("manual" | "ses")[];
  is_ses_suppressed: boolean | null;
  ses_suppression_reason: "BOUNCE" | "COMPLAINT" | null;
  is_unsubscribed: boolean | null;
  has_bounced: boolean;
  status_unknown: boolean;
};

const CONTACT_FLAGS = ["bounced", "manual", "ses", "unsubscribed", "unmatched", "unknown"] as const;
const MANUAL_SELECTION_LIMIT = 1000;
type ContactFlag = typeof CONTACT_FLAGS[number];
type Validation = {
  total: number;
  checked_at: string;
  counts: Record<ContactFlag, number>;
};
type SelectionSnapshot = { selection_id: string; selected_count: number; expires_at: string };

type SuppressionSync = {
  status: "ready" | "pending" | "error" | "stale" | "disabled";
  last_synced_at: string | null;
  region: string;
};

export default function UserGroups() {
  const {token}=useAuth(); const {toast}=useToast(); const {confirm:cfm}=useConfirm(); const {t}=useLocale();
  const [gs,setGs]=useState<any[]>([]); const [gS,setGS]=useState(""); const [gP,setGP]=useState(1); const [gT,setGT]=useState(0); const [gTP,setGTP]=useState(1);
  const [sel,setSel]=useState<number|null>(null); const [cs,setCs]=useState<Contact[]>([]); const [cS,setCS]=useState(""); const [cP,setCP]=useState(1); const [cT,setCT]=useState(0); const [cTP,setCTP]=useState(1);
  const [contactsLoading,setContactsLoading]=useState(false);
  const [contactsError,setContactsError]=useState(false);
  const [suppressionSync,setSuppressionSync]=useState<SuppressionSync|null>(null);
  const contactRequest=useRef<AbortController|null>(null);
  const selectedGroup=useRef<number|null>(null);
  const [groupName,setGroupName]=useState("");
  const [flags,setFlags]=useState<ContactFlag[]>([]);
  const [validation,setValidation]=useState<Validation|null>(null);
  const [validating,setValidating]=useState(false);
  const [selectedIds,setSelectedIds]=useState<Set<number>>(()=>new Set());
  const [snapshot,setSnapshot]=useState<SelectionSnapshot|null>(null);
  const [selectingAll,setSelectingAll]=useState(false);
  const [deleting,setDeleting]=useState(false);
  const contextVersion=useRef(0);
  const selectionVersion=useRef(0);
  const actionRequests=useRef<{validation:AbortController|null;selection:AbortController|null}>({validation:null,selection:null});
  const contactQuery=useRef({page:1,search:"",flags:[] as ContactFlag[]});

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
  useEffect(()=>()=>{
    contactRequest.current?.abort();
    actionRequests.current.validation?.abort();
    actionRequests.current.selection?.abort();
    contextVersion.current++;
  },[]);
  const clearSelection=()=>{selectionVersion.current++;setSelectedIds(new Set());setSnapshot(null);};
  const resetContext=()=>{
    contextVersion.current++;
    actionRequests.current.validation?.abort();actionRequests.current.selection?.abort();
    setValidating(false);setSelectingAll(false);clearSelection();
  };
  useEffect(()=>{
    if(!snapshot)return;
    const value=snapshot.expires_at;
    const expires=Date.parse(/[zZ]|[+-]\d{2}:\d{2}$/.test(value)?value:`${value}Z`);
    const timer=window.setTimeout(()=>{
      clearSelection();toast("warning",t("groups.selectionExpired"));
    },Math.max(0,expires-Date.now()));
    return ()=>window.clearTimeout(timer);
  },[snapshot]);
  const loadC=async(gid:number,p=1,s="",fs:ContactFlag[]=[])=>{
    contactRequest.current?.abort();
    const request=new AbortController();
    contactRequest.current=request;
    contactQuery.current={page:p,search:s,flags:fs};
    setCP(p);setContactsLoading(true);setContactsError(false);setSuppressionSync(null);
    try{
      const response=await fetch(`${API}/groups/${gid}/contacts?page=${p}&page_size=${PAGE_SIZE}&search=${encodeURIComponent(s)}&flags=${fs.join(",")}`,{headers:authH(token),signal:request.signal});
      const d=await response.json();
      if(!response.ok)throw new Error(typeof d.detail==="string"?d.detail:t("groups.contactsLoadFailed"));
      if(!Array.isArray(d.items))throw new Error(t("groups.contactsLoadFailed"));
      if(request.signal.aborted||contactRequest.current!==request)return;
      setCs(d.items);setCT(d.total||0);setCTP(d.total_pages||1);setCP(d.page||1);setSuppressionSync(d.suppression_sync||null);
    }catch(error){
      if(request.signal.aborted||contactRequest.current!==request)return;
      setCs([]);setCT(0);setCTP(1);setContactsError(true);
      toast("error",t("groups.contactsLoadFailed"),error instanceof Error?error.message:undefined);
    }finally{
      if(!request.signal.aborted&&contactRequest.current===request)setContactsLoading(false);
    }
  };
  const refreshC=(gid:number)=>{if(selectedGroup.current===gid){const q=contactQuery.current;loadC(gid,q.page,q.search,q.flags);}};
  const chooseGroup=(g:any)=>{
    resetContext();selectedGroup.current=g.id;setSel(g.id);setGroupName(g.name);setCS("");setFlags([]);setValidation(null);loadC(g.id,1,"",[]);
  };
  const searchC=(v:string)=>{resetContext();setCS(v);if(sel)loadC(sel,1,v,flags);};
  const filterC=(flag:ContactFlag|null)=>{
    resetContext();
    const next=flag===null?[]:flags.includes(flag)?flags.filter(f=>f!==flag):[...flags,flag];
    setFlags(next);if(sel)loadC(sel,1,cS,next);
  };
  const requestData=async(url:string,body?:object,signal?:AbortSignal)=>{
    const response=await fetch(url,{method:"POST",headers:authH(token),body:body?JSON.stringify(body):undefined,signal});
    const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:t("groups.actionFailed"));
    return data;
  };
  const validateGroup=async()=>{
    if(!sel)return;
    resetContext();setValidation(null);setValidating(true);
    const gid=sel,version=contextVersion.current,request=new AbortController();
    actionRequests.current.validation=request;
    try{
      const result=await requestData(`${API}/groups/${gid}/validate`,undefined,request.signal);
      if(request.signal.aborted||contextVersion.current!==version)return;
      setValidation(result);refreshC(gid);
      toast("success",t("groups.validationDone",{count:result.total}));
    }catch(error){
      if(!request.signal.aborted&&contextVersion.current===version)toast("error",t("groups.validationFailed"),error instanceof Error?error.message:undefined);
    }finally{if(!request.signal.aborted&&contextVersion.current===version)setValidating(false);}
  };
  const selectAllResults=async()=>{
    if(!sel||contactsLoading||contactsError||!cT)return;
    const gid=sel,version=contextVersion.current,request=new AbortController();
    actionRequests.current.selection?.abort();actionRequests.current.selection=request;setSelectingAll(true);
    try{
      const result=await requestData(`${API}/groups/${gid}/contacts/selection`,{search:cS,flags},request.signal);
      if(request.signal.aborted||contextVersion.current!==version)return;
      clearSelection();
      if(result.selected_count>0)setSnapshot(result);
      else {toast("warning",t("groups.noMatchingContacts"));refreshC(gid);}
    }catch(error){
      if(!request.signal.aborted&&contextVersion.current===version)toast("error",t("groups.selectionFailed"),error instanceof Error?error.message:undefined);
    }finally{if(!request.signal.aborted&&contextVersion.current===version)setSelectingAll(false);}
  };
  const toggleContact=(id:number)=>{
    if(snapshot||deleting||selectingAll||validating)return;
    if(!selectedIds.has(id)&&selectedIds.size>=MANUAL_SELECTION_LIMIT){toast("warning",t("groups.selectionLimit"));return;}
    selectionVersion.current++;
    setSelectedIds(previous=>{const next=new Set(previous);if(next.has(id))next.delete(id);else next.add(id);return next;});
  };
  const togglePage=()=>{
    if(snapshot||deleting||selectingAll||validating)return;
    if(selectedIds.size+cs.filter(c=>!selectedIds.has(c.id)).length>MANUAL_SELECTION_LIMIT){toast("warning",t("groups.selectionLimit"));return;}
    selectionVersion.current++;
    setSelectedIds(previous=>{const next=new Set(previous);const all=cs.every(c=>next.has(c.id));cs.forEach(c=>all?next.delete(c.id):next.add(c.id));return next;});
  };
  const selectedCount=snapshot?.selected_count??selectedIds.size;
  const bulkDelete=async()=>{
    if(!sel||!selectedCount||deleting)return;
    const gid=sel,version=contextVersion.current,selection=selectionVersion.current,count=selectedCount;
    const body=snapshot?{selection_id:snapshot.selection_id}:{contact_ids:Array.from(selectedIds)};
    setDeleting(true);
    try{
      if(!await cfm(t("groups.bulkDeleteTitle"),t("groups.bulkDeleteBody",{name:groupName,count}),t("groups.confirmDelete")))return;
      if(contextVersion.current!==version||selectionVersion.current!==selection)return;
      const result=await requestData(`${API}/groups/${gid}/contacts/bulk-delete`,body);
      toast("success",t("groups.bulkDeleted",{count:result.deleted_count}));loadG(gP,gS);
      if(contextVersion.current===version){clearSelection();setValidation(null);const q=contactQuery.current;loadC(gid,1,q.search,q.flags);}
    }catch(error){
      toast("error",t("groups.bulkDeleteFailed"),error instanceof Error?error.message:undefined);
      if(contextVersion.current===version)clearSelection();
    }finally{setDeleting(false);}
  };

  const addG=async()=>{if(!ng)return toast("warning",t("groups.enterName"));await fetch(`${API}/groups`,{method:"POST",headers:authH(token),body:JSON.stringify({name:ng,description:ngDesc})});toast("success",t("groups.created"));setNg("");setNgDesc("");setShowAddGroup(false);loadG(1,gS);};
  const openEditG=(g:any)=>{setEditGroupId(g.id);setNg(g.name);setNgDesc(g.description||"");setShowEditGroup(true);};
  const updateG=async()=>{if(!ng)return toast("warning",t("groups.enterName"));const r=await fetch(`${API}/groups/${editGroupId}`,{method:"PUT",headers:authH(token),body:JSON.stringify({name:ng,description:ngDesc})});if(r.ok){toast("success",t("groups.updated"));if(selectedGroup.current===editGroupId)setGroupName(ng);setShowEditGroup(false);loadG(gP,gS);}else{const e=await r.json();toast("error",t("groups.updateFailed"),e.detail);}};
  const delG=async(g:any)=>{if(!await cfm(t("groups.deleteTitle"),t("groups.deleteBody",{name:g.name,count:g.contact_count}),t("groups.confirmDelete")))return;const r=await fetch(`${API}/groups/${g.id}`,{method:"DELETE",headers:authH(token)});if(!r.ok){toast("error",t("groups.actionFailed"));return;}if(selectedGroup.current===g.id){resetContext();contactRequest.current?.abort();selectedGroup.current=null;setSel(null);setCs([]);setValidation(null);setSuppressionSync(null);setContactsLoading(false);setContactsError(false);}loadG(gP,gS);};
  const refreshAfterMutation=(gid:number)=>{
    if(selectedGroup.current===gid){resetContext();setValidation(null);refreshC(gid);}
    loadG(gP,gS);
  };

  const updR=(i:number,f:string,v:string)=>{const r=[...rows];(r[i] as any)[f]=v;setRows(r);};
  const addR=()=>setRows([...rows,{name:"",email:"",attrKeys:[""],attrVals:[""]}]);
  const rmR=(i:number)=>{if(rows.length>1)setRows(rows.filter((_,j)=>j!==i));};
  const updAttr=(ri:number,ai:number,field:"key"|"val",v:string)=>{const r=[...rows];if(field==="key")r[ri].attrKeys[ai]=v;else r[ri].attrVals[ai]=v;setRows(r);};
  const addAttrRow=(ri:number)=>{const r=[...rows];r[ri].attrKeys.push("");r[ri].attrVals.push("");setRows(r);};
  const rmAttrRow=(ri:number,ai:number)=>{const r=[...rows];r[ri].attrKeys.splice(ai,1);r[ri].attrVals.splice(ai,1);setRows(r);};
  const buildAttrs=(r:any)=>{const o:any={};(r.attrKeys||[]).forEach((k:string,i:number)=>{const key=k.trim(),val=(r.attrVals[i]||"").trim();if(key&&val)o[key]=val;});return Object.keys(o).length?JSON.stringify(o):null;};
  const saveC=async()=>{const gid=sel;if(!gid)return;const v=rows.filter(r=>r.email.trim());if(!v.length)return toast("warning",t("groups.fillEmail"));try{for(const r of v)await requestData(`${API}/contacts`,{name:r.name.trim(),email:r.email.trim(),attributes:buildAttrs(r),group_id:gid});toast("success",t("groups.contactsAdded",{count:v.length}));setRows([{name:"",email:"",attrKeys:[""],attrVals:[""]}]);setShowAddContact(false);}catch(error){toast("error",t("groups.actionFailed"),error instanceof Error?error.message:undefined);}finally{refreshAfterMutation(gid);}};
  const delC=async(c:Contact)=>{
    const gid=sel,version=contextVersion.current;if(!gid)return;
    if(!await cfm(t("groups.contactDeleteTitle"),t("groups.contactDeleteBody",{name:c.name||c.email,email:c.email}),t("groups.confirmDelete")))return;
    if(contextVersion.current!==version)return;
    try{const r=await fetch(`${API}/contacts/${c.id}`,{method:"DELETE",headers:authH(token)});if(!r.ok)throw new Error(t("groups.actionFailed"));refreshAfterMutation(gid);}catch(error){toast("error",t("groups.actionFailed"),error instanceof Error?error.message:undefined);}
  };

  const dlTpl=()=>window.open(`${API}/contacts/template/download?token=${token}`,"_blank");
  const dlCs=()=>{if(sel)window.open(`${API}/groups/${sel}/contacts/download?token=${token}`,"_blank");};
  const ulCs=async(e:any)=>{const input=e.target,file=input.files[0],gid=sel;if(!file||!gid)return;const fd=new FormData();fd.append("file",file);try{const r=await fetch(`${API}/groups/${gid}/contacts/upload`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body:fd});const d=await r.json();if(r.ok){toast("success",t("groups.importSuccess"),d.message);refreshAfterMutation(gid);}else toast("error",t("groups.importFailed"),d.detail);}catch{toast("error",t("groups.importFailed"));}finally{input.value="";}};

  const refreshHint=contactsLoading||contactsError?undefined:[
    suppressionSync?.status!=="ready"?t(`groups.sesSync.${suppressionSync?.status||"pending"}`):cs.some(c=>c.is_ses_suppressed==null)?t("groups.sesStatusUnknown"):"",
    cs.some(c=>c.is_unsubscribed===null)?t("groups.senderNotConfigured"):"",
  ].filter(Boolean).join("\n")||undefined;

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
        <div className="space-y-1">{gs.map((g:any)=><div key={g.id} onClick={()=>chooseGroup(g)} className={`flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition ${sel===g.id?"bg-indigo-50 text-indigo-700":"hover:bg-gray-50 text-gray-700"}`}>
          <span className={`text-sm ${sel===g.id?"font-semibold":""}`}>{g.name} <span className="text-xs text-gray-400">({g.contact_count})</span></span>
          <div className="flex gap-1">
            <Btn variant="outline" size="sm" onClick={(e:any)=>{e.stopPropagation();openEditG(g);}}>{t("common.edit")}</Btn>
            <Btn variant="danger" size="sm" onClick={(e:any)=>{e.stopPropagation();delG(g);}}>{t("common.delete")}</Btn>
          </div>
        </div>)}{gs.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t("groups.noGroups")}</p>}</div>
        <Pager page={gP} totalPages={gTP} total={gT} onPageChange={p=>loadG(p,gS)}/>
      </Card>

      <div className="lg:col-span-2 min-w-0"><Card title={sel?t("groups.contactManager"):t("groups.selectGroup")} extra={sel&&<div className="flex flex-wrap justify-end gap-2">
        <Btn variant="outline" size="sm" onClick={dlTpl}>{t("groups.downloadTemplate")}</Btn>
        <label className="inline-flex items-center justify-center font-medium rounded-lg transition h-8 px-3 text-xs border border-gray-200 text-gray-600 hover:bg-gray-50 bg-white cursor-pointer">{t("groups.excelImport")}<input type="file" accept=".xlsx,.xls" className="hidden" onChange={ulCs}/></label>
        <Btn variant="outline" size="sm" onClick={dlCs}>{t("groups.excelExport")}</Btn>
        <Btn variant="success" size="sm" onClick={()=>{setRows([{name:"",email:"",attrKeys:[""],attrVals:[""]}]);setShowAddContact(true);}}>{t("groups.addContact")}</Btn>
      </div>}>
        {sel?<>
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <Input placeholder={t("groups.searchContact")} value={cS} onChange={(e:any)=>searchC(e.target.value)} className="min-w-0 flex-1 basis-48"/>
            {!contactsLoading&&!contactsError&&<span className="text-sm text-gray-400 whitespace-nowrap">{t("groups.totalContacts",{count:cT})}</span>}
            <Btn variant="outline" size="sm" className="shrink-0 whitespace-nowrap" disabled={contactsLoading||validating||deleting} title={refreshHint} onClick={()=>{resetContext();loadC(sel,cP,cS,flags);}}>{t("common.refresh")}</Btn>
            <Btn size="sm" className="shrink-0 whitespace-nowrap" disabled={validating||deleting||selectingAll} onClick={validateGroup}>{t(validating?"groups.validating":"groups.validateGroup")}</Btn>
          </div>
          <div role="group" aria-label={t("groups.flagFilters")} className="flex flex-wrap items-center gap-2 mb-3">
            <span className="text-xs text-gray-500 mr-1">{t("groups.flagFilters")}</span>
            <button type="button" aria-pressed={flags.length===0} onClick={()=>filterC(null)} className={`rounded-full border px-3 py-1 text-xs transition ${flags.length===0?"border-indigo-200 bg-indigo-50 text-indigo-700":"border-gray-200 text-gray-500 hover:bg-gray-50"}`}>{t("groups.filter.all")}</button>
            {CONTACT_FLAGS.map(flag=><button type="button" key={flag} aria-label={t(`groups.filter.${flag}`)} aria-pressed={flags.includes(flag)} title={flag==="unmatched"?t("groups.noListMatchHint"):flag==="unknown"?t("groups.unknownHint"):undefined} onClick={()=>filterC(flag)} className={`rounded-full border px-3 py-1 text-xs transition ${flags.includes(flag)?"border-indigo-200 bg-indigo-50 text-indigo-700":"border-gray-200 text-gray-500 hover:bg-gray-50"}`}>
              {t(`groups.filter.${flag}`)}{validation&&<span className="ml-1 tabular-nums">{validation.counts[flag]}</span>}
            </button>)}
            <span className="text-xs text-gray-400">{t("groups.filterOrHint")}</span>
          </div>
          {validation&&<p role="status" className="mb-3 text-xs text-gray-500">{t("groups.validationSummary",{count:validation.total})}</p>}
          {!contactsLoading&&!contactsError&&<div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <div className="flex flex-wrap items-center gap-2">
              {selectedCount>0&&<span className="text-sm font-medium text-indigo-700">{t("groups.selectedCount",{count:selectedCount})}</span>}
              {!snapshot&&cT>0&&<Btn variant="outline" size="sm" disabled={selectingAll||deleting||validating} onClick={selectAllResults}>{t(selectingAll?"groups.selectingAll":"groups.selectAllResults",{count:cT})}</Btn>}
              {selectedCount>0&&<button type="button" disabled={deleting||selectingAll} className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50" onClick={clearSelection}>{t("groups.clearSelection")}</button>}
            </div>
            {selectedCount>0&&<Btn variant="danger" size="sm" disabled={deleting||selectingAll||validating} onClick={bulkDelete}>{t(deleting?"groups.deleting":"groups.bulkDelete",{count:selectedCount})}</Btn>}
            {snapshot&&<p className="w-full text-xs text-gray-500">{t("groups.snapshotHint")}</p>}
          </div>}
          {contactsLoading?<p role="status" className="text-center py-8 text-sm text-gray-400">{t("common.loading")}</p>:contactsError?<p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{t("groups.contactsLoadFailed")}</p>:<>
          <div className="overflow-x-auto"><table className="w-full">
            <thead><tr className="border-b border-gray-100"><th className="w-10 py-3 pl-2 pr-1"><input type="checkbox" aria-label={t("groups.selectPage")} title={snapshot?t("groups.snapshotHint"):t("groups.selectPage")} className="size-4 accent-indigo-600 disabled:cursor-not-allowed" disabled={!!snapshot||deleting||selectingAll||validating||cs.length===0} checked={!snapshot&&cs.length>0&&cs.every(c=>selectedIds.has(c.id))} ref={node=>{if(node)node.indeterminate=!snapshot&&cs.some(c=>selectedIds.has(c.id))&&!cs.every(c=>selectedIds.has(c.id));}} onChange={togglePage}/></th>{[t("groups.contactName"),t("groups.email"),t("groups.attributes"),t("groups.tableActions")].map(h=><th key={h} className="whitespace-nowrap text-left text-xs font-medium text-gray-500 uppercase tracking-wider py-3 px-4">{h}</th>)}</tr></thead>
            <tbody>{cs.map(c=>{
              let attrPreview="";
              try{const a=c.attributes?JSON.parse(c.attributes):{};attrPreview=Object.entries(a).map(([k,v])=>`${k}: ${v}`).join(", ");}catch{}
              return <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
              <td className="py-3 pl-2 pr-1"><input type="checkbox" aria-label={t("groups.selectContact",{email:c.email})} title={snapshot?t("groups.snapshotHint"):undefined} className="size-4 accent-indigo-600 disabled:cursor-not-allowed" disabled={!!snapshot||deleting||selectingAll||validating} checked={!snapshot&&selectedIds.has(c.id)} onChange={()=>toggleContact(c.id)}/></td>
              <td className="py-3 px-4 text-sm text-gray-800">{c.name}</td>
              <td className="py-3 px-4 text-sm text-gray-500"><div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="break-all">{c.email}</span>
                {c.has_bounced&&<span className="inline-flex" title={t("groups.bouncedHint")}><Badge color="red">{t("groups.bounced")}</Badge></span>}
                {c.blacklist_sources?.includes("manual")&&<Badge color="red">{t("groups.blacklisted")}</Badge>}
                {c.is_ses_suppressed===true&&<span className="inline-flex" title={t(c.ses_suppression_reason==="BOUNCE"?"groups.sesBounce":c.ses_suppression_reason==="COMPLAINT"?"groups.sesComplaint":"groups.sesSuppressed")}><Badge color="red">{t("groups.sesSuppressed")}</Badge></span>}
                {c.is_unsubscribed===true&&<Badge color="orange">{t("groups.unsubscribed")}</Badge>}
                {c.status_unknown&&<span className="inline-flex" title={t("groups.unknownHint")}><Badge color="gray">{t("groups.filter.unknown")}</Badge></span>}
              </div></td>
              <td className="py-3 px-4 text-xs text-gray-400 max-w-[200px] truncate" title={attrPreview}>{attrPreview||"—"}</td>
              <td className="py-3 px-4"><Btn variant="danger" size="sm" className="whitespace-nowrap" disabled={deleting||selectingAll} onClick={()=>delC(c)}>{t("common.delete")}</Btn></td>
            </tr>})}</tbody>
          </table></div>
          {cs.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t(cS||flags.length?"groups.noMatchingContacts":"groups.noContacts")}</p>}
          <Pager page={cP} totalPages={cTP} total={cT} onPageChange={p=>loadC(sel,p,cS,flags)}/>
          </>}
        </>:<p className="text-center py-16 text-gray-400">{t("groups.selectGroupHint")}</p>}
      </Card></div>
    </div>
  </>;
}
