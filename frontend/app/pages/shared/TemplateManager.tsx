"use client";
import React, { useState, useEffect, useRef } from "react";
import { API, authH, useAuth, useToast, useConfirm, Card, Btn, Input, Textarea, Modal } from "../../components/shared";
import { useT } from "../../i18n";

export default function TemplateManager({apiPrefix}:{apiPrefix:string}) {
  const {token}=useAuth(); const {toast}=useToast(); const {confirm:cfm}=useConfirm();
  const t = useT();
  const [list,setList]=useState<any[]>([]);
  const [mode,setMode]=useState<"list"|"create"|"edit">("list");
  const [f,setF]=useState({name:"",subject:"",html_body:""});
  const [editId,setEditId]=useState<number|null>(null);
  const [previewTab,setPreviewTab]=useState<"split">("split");
  const visualHtmlRef = useRef<string>("");
  const splitIframeRef = useRef<HTMLIFrameElement>(null);
  const splitInitRef = useRef(false);
  const splitSyncingRef = useRef(false);
  const splitHtmlRef = useRef<string>("");

  const syncFromSplitEditor = () => {
    const iframe = splitIframeRef.current;
    if (!iframe) return;
    try {
      const doc = iframe.contentDocument;
      if (doc?.body) {
        splitSyncingRef.current = true;
        setF(prev => ({ ...prev, html_body: doc.body.innerHTML }));
        setTimeout(() => { splitSyncingRef.current = false; }, 50);
      }
    } catch {}
  };

  useEffect(() => {
    splitInitRef.current = false;
  }, [previewTab]);

  const initSplitIframe = (iframe: HTMLIFrameElement | null) => {
    if (!iframe) return;
    splitIframeRef.current = iframe;
    if (splitInitRef.current) return;
    const doInit = () => {
      if (splitInitRef.current) return;
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document;
        if (!doc) return;
        doc.open();
        doc.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;padding:20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;outline:none;min-height:500px;cursor:text;}</style></head><body>${f.html_body}</body></html>`);
        doc.close();
        doc.designMode = "on";
        splitHtmlRef.current = f.html_body;
        doc.body.addEventListener("blur", syncFromSplitEditor);
        splitInitRef.current = true;
      } catch {}
    };
    iframe.addEventListener("load", doInit, { once: true });
    setTimeout(doInit, 100);
  };

  useEffect(() => {
    if (previewTab !== "split" || !splitInitRef.current || splitSyncingRef.current) return;
    const iframe = splitIframeRef.current;
    if (!iframe) return;
    try {
      const doc = iframe.contentDocument;
      if (doc?.body && doc.body.innerHTML !== f.html_body) {
        const sel = doc.getSelection();
        const hadFocus = doc.hasFocus();
        doc.body.innerHTML = f.html_body;
        if (hadFocus && sel) { try { sel.selectAllChildren(doc.body); sel.collapseToEnd(); } catch {} }
      }
    } catch {}
  }, [f.html_body]);

  // AI 优化
  const [aiLoading,setAiLoading]=useState(false);
  const [aiResult,setAiResult]=useState<{suggestions:string[];optimized_subject:string;optimized_html:string}|null>(null);
  const [aiFeedback,setAiFeedback]=useState("");
  const [showAiPrompt,setShowAiPrompt]=useState(false);
  const [aiPrompt,setAiPrompt]=useState("");
  const [aiImages,setAiImages]=useState<{url:string;name:string}[]>([]);
  const [aiModels,setAiModels]=useState<{id:string;name:string;provider_name:string;provider_type:string}[]>([]);
  const [selectedModel,setSelectedModel]=useState("");

  useEffect(()=>{
    fetch(`${API}/ai-models/available`,{headers:authH(token)}).then(r=>r.json()).then(d=>{if(Array.isArray(d))setAiModels(d);}).catch(()=>{});
  },[]);

  const uploadAiImage=async(file:File)=>{
    const fd=new FormData();fd.append("file",file);
    try{
      const r=await fetch(`${API}/upload/image`,{method:"POST",headers:{"Authorization":`Bearer ${token}`},body:fd});
      if(!r.ok)return;
      const d=await r.json();
      setAiImages(prev=>[...prev,{url:d.url,name:file.name}]);
    }catch{}
  };

  const aiOptimize=async(feedback?:string)=>{
    const useOriginal = !feedback;
    const subj = useOriginal ? f.subject : (aiResult?.optimized_subject || f.subject);
    const body = useOriginal ? f.html_body : (aiResult?.optimized_html || f.html_body);
    if(!body.trim())return toast("warning",t("ai.writeContentFirst"));
    setAiLoading(true);setShowAiPrompt(false);
    if(useOriginal) setAiResult(null);
    try{
      const payload:any = {subject:subj, html_body:body};
      const prompt = feedback?.trim() || aiPrompt.trim();
      if(prompt) payload.user_feedback = prompt;
      const imgUrls = aiImages.map(i=>i.url);
      if(imgUrls.length>0) payload.images = imgUrls;
      if(selectedModel) payload.model_id = selectedModel;
      const r=await fetch(`${API}/ai/optimize-template`,{method:"POST",headers:authH(token),body:JSON.stringify(payload)});
      const d=await r.json();
      if(r.ok){setAiResult(d);setShowAi(true);setAiFeedback("");setAiPrompt("");setAiImages([]);}
      else toast("error",t("ai.optimizeFailed"),d.detail||"");
    }catch(e:any){toast("error",t("ai.optimizeFailed"),e?.message||t("common.networkError"));}
    finally{setAiLoading(false);}
  };
  const applyAi=()=>{
    if(aiResult){setF(prev=>({...prev,subject:aiResult.optimized_subject,html_body:aiResult.optimized_html}));setAiResult(null);setShowAi(false);toast("success",t("ai.applied"));}
  };

  const [showAi,setShowAi]=useState(false);
  const [evalLoading,setEvalLoading]=useState(false);
  const [evalResult,setEvalResult]=useState<any>(null);
  const [showEval,setShowEval]=useState(false);
  const [showEvalPanel,setShowEvalPanel]=useState(false);
  const [evalModels,setEvalModels]=useState<string[]>([]);
  const [evalTab,setEvalTab]=useState(0);
  const [showLinkModal,setShowLinkModal]=useState(false);
  const [linkUrl,setLinkUrl]=useState("https://");
  const [linkText,setLinkText]=useState("");
  const [fixLoading,setFixLoading]=useState("");
  const [fixResults,setFixResults]=useState<Record<string,any>>({});

  const toggleEvalModel=(id:string)=>{
    setEvalModels(prev=>prev.includes(id)?prev.filter(m=>m!==id):[...prev,id]);
  };

  const runEval=async()=>{
    if(!f.html_body.trim()) return toast("warning",t("ai.writeContentFirst"));
    setEvalLoading(true);setEvalResult(null);setFixResults({});setEvalTab(0);
    try{
      const payload:any={subject:f.subject,html_body:f.html_body};
      if(evalModels.length>0) payload.model_ids=evalModels;
      const r=await fetch(`${API}/ai/evaluate-template`,{method:"POST",headers:authH(token),body:JSON.stringify(payload)});
      const d=await r.json();
      if(r.ok){setEvalResult(d);setShowEval(true);}
      else toast("error",t("ai.evalFailed"),d.detail||"");
    }catch(e:any){toast("error",t("ai.evalFailed"),e?.message||t("common.networkError"));}
    finally{setEvalLoading(false);}
  };

  const getDimFix=async(dim:any)=>{
    setFixLoading(dim.name);
    try{
      const curModel=evalResult?.models?.[evalTab];
      const payload:any={subject:f.subject,html_body:f.html_body,dimension:dim.name,issues:dim.issues||[]};
      if(curModel?.model_id) payload.model_id=curModel.model_id;
      const r=await fetch(`${API}/ai/dimension-fix`,{method:"POST",headers:authH(token),body:JSON.stringify(payload)});
      if(r.ok){const d=await r.json();setFixResults(prev=>({...prev,[`${evalResult?.models?.[evalTab]?.model_id}_${dim.name}`]:d}));}
      else{const e=await r.json();toast("error",t("ai.dimFixFailed"),e.detail);}
    }catch{toast("error",t("common.networkError"));}
    finally{setFixLoading("");}
  };

  const load=async()=>{const d=await(await fetch(`${API}${apiPrefix}`,{headers:authH(token)})).json();setList(Array.isArray(d)?d:[]);}; useEffect(()=>{load();},[]);

  const create=async()=>{
    syncFromSplitEditor();
    if(!f.name||!f.subject||!f.html_body)return toast("warning",t("template.fillComplete"));
    const r=await fetch(`${API}${apiPrefix}`,{method:"POST",headers:authH(token),body:JSON.stringify(f)});
    if(r.ok){toast("success",t("template.created"));setMode("list");load();}
    else{const e=await r.json();toast("error",t("common.failed"),e.detail);}
  };

  const openEdit=(t:any)=>{setEditId(t.id);setF({name:t.name,subject:t.subject,html_body:t.html_body});setMode("edit");setAiResult(null);splitInitRef.current=false;};
  const openCreate=()=>{setF({name:"",subject:"",html_body:""});setMode("create");setAiResult(null);splitInitRef.current=false;};
  const goBack=()=>{setMode("list");setAiResult(null);};

  const update=async()=>{
    syncFromSplitEditor();
    if(!f.subject||!f.html_body)return toast("warning",t("template.fillComplete"));
    const r=await fetch(`${API}${apiPrefix}/${editId}`,{method:"PUT",headers:authH(token),body:JSON.stringify({subject:f.subject,html_body:f.html_body})});
    if(r.ok){toast("success",t("template.updated"));setMode("list");load();}
    else{const e=await r.json();toast("error",t("template.updateFailed"),e.detail);}
  };

  const del=async(t2:any)=>{if(!await cfm(t("template.deleteTitle"),t("template.deleteConfirm",{name:t2.name}),t("template.confirmDeleteBtn")))return;const r=await fetch(`${API}${apiPrefix}/${t2.id}`,{method:"DELETE",headers:authH(token)});if(r.ok){toast("success",t("template.deleted"));load();}else{const e=await r.json();toast("error",t("common.failed"),e.detail);}};

  const snippets = [
    {label:t("template.toolbar.heading"),icon:"H",html:`<h1 style="color:#333;font-size:24px;">${t("template.snippet.headingText")}</h1>\n`},
    {label:t("template.toolbar.paragraph"),icon:"P",html:`<p style="color:#555;font-size:14px;line-height:1.8;">${t("template.snippet.paragraphText")}</p>\n`},
    {label:t("template.toolbar.button"),icon:"▣",html:`<a href="https://example.com" style="display:inline-block;padding:12px 28px;background:#6366f1;color:#fff;text-decoration:none;border-radius:6px;font-size:14px;">${t("template.snippet.buttonText")}</a>\n`},
    {label:t("template.toolbar.image"),icon:"🖼",html:`<img src="https://via.placeholder.com/600x200" alt="${t("template.snippet.imageAlt")}" style="max-width:100%;height:auto;border-radius:8px;" />\n`},
    {label:t("template.toolbar.divider"),icon:"—",html:'<hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;" />\n'},
    {label:t("template.toolbar.table"),icon:"⊞",html:`<table style="width:100%;border-collapse:collapse;">\n  <tr style="background:#f3f4f6;">\n    <th style="padding:10px 16px;text-align:left;border-bottom:2px solid #e5e7eb;">${t("template.snippet.col1")}</th>\n    <th style="padding:10px 16px;text-align:left;border-bottom:2px solid #e5e7eb;">${t("template.snippet.col2")}</th>\n  </tr>\n  <tr>\n    <td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;">${t("template.snippet.cellContent")}</td>\n    <td style="padding:10px 16px;border-bottom:1px solid #f3f4f6;">${t("template.snippet.cellContent")}</td>\n  </tr>\n</table>\n`},
    {label:t("template.toolbar.card"),icon:"☐",html:`<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:24px;margin:16px 0;">\n  <h2 style="margin:0 0 8px;color:#333;font-size:18px;">${t("template.snippet.cardTitle")}</h2>\n  <p style="margin:0;color:#666;font-size:14px;">${t("template.snippet.cardContent")}</p>\n</div>\n`},
    {label:t("template.toolbar.footer"),icon:"⊥",html:`<div style="text-align:center;padding:20px 0;border-top:1px solid #e5e7eb;margin-top:30px;">\n  <p style="color:#999;font-size:12px;">© 2026 Your Company. All rights reserved.</p>\n  <p style="color:#999;font-size:12px;"><a href="{{unsubscribe_url}}" style="color:#999;">${t("template.snippet.unsubText")}</a></p>\n</div>\n`},
  ];

  const variables = [
    {label:t("template.var.name"),val:"{{name}}"},
    {label:t("template.var.email"),val:"{{email}}"},
    {label:t("template.var.company"),val:"{{company}}"},
    {label:t("template.var.date"),val:"{{date}}"},
    {label:t("template.var.unsubLink"),val:"{{unsubscribe_url}}"},
  ];

  const insertSnippet = (html:string) => { setF(prev=>({...prev,html_body:prev.html_body+html})); };
  const insertVariable = (val:string) => { setF(prev=>({...prev,html_body:prev.html_body+val})); };

  const [uploading,setUploading]=useState(false);
  const fileInputRef=useRef<HTMLInputElement>(null);

  const uploadImage = async (file: File) => {
    if (!file.type.startsWith("image/")) { toast("warning",t("template.imageOnly")); return; }
    if (file.size > 5*1024*1024) { toast("warning",t("template.imageSizeLimit")); return; }
    setUploading(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch(`${API}/upload/image`, {method:"POST", headers:{"Authorization":`Bearer ${token}`}, body:fd});
      if (!r.ok) { const e = await r.json(); toast("error",t("template.uploadFailed"),e.detail); return; }
      const d = await r.json();
      const imgUrl = d.url.startsWith("http") ? d.url : `${API}${d.url}`;
      const imgHtml = `<img src="${imgUrl}" alt="${file.name}" style="max-width:100%;height:auto;border-radius:8px;" />\n`;
      setF(prev=>({...prev,html_body:prev.html_body+imgHtml}));
      toast("success",t("template.imageUploaded"),file.name);
    } catch { toast("error",t("template.uploadFailed"),t("common.networkError")); }
    finally { setUploading(false); }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) { e.preventDefault(); const file = items[i].getAsFile(); if (file) uploadImage(file); return; }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer?.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) { if (files[i].type.startsWith("image/")) { uploadImage(files[i]); return; } }
  };

  const getPreviewHtml = (body:string) => {
    const subjectLine = f.subject ? f.subject.replace(/\{\{(\w+)\}\}/g, '<span style="background:#fef3c7;padding:1px 4px;border-radius:3px;color:#92400e;">$1</span>') : '';
    let previewBody = body.replace(/href=["']?\{\{unsubscribe_url\}\}["']?/g, 'href="#unsubscribe-preview"');
    previewBody = previewBody.replace(/\{\{(\w+)\}\}/g, '<span style="background:#fef3c7;padding:1px 4px;border-radius:3px;color:#92400e;font-size:inherit;">$1</span>');
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;}</style></head><body>
      <div style="max-width:640px;margin:0 auto;background:#fff;">
        ${subjectLine ? `<div style="background:#f8fafc;padding:12px 20px;border-bottom:1px solid #e5e7eb;"><span style="color:#9ca3af;font-size:12px;">${t("template.subjectLabel")}</span><span style="color:#374151;font-size:13px;">${subjectLine}</span></div>` : ''}
        <div style="padding:24px 20px;">${previewBody}</div>
      </div>
    </body></html>`;
  };

  const aiPreviewHtml = (body:string) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;padding:16px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:14px;color:#333;}</style></head><body>${body}</body></html>`;

  // ========== 列表视图 ==========
  if (mode === "list") {
    return <Card title={t("template.title")} extra={<Btn size="sm" onClick={openCreate}>{t("template.create")}</Btn>}>
      <div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b border-gray-100">{[t("template.tableTemplateName"),t("template.tableSubject"),t("template.tableCreatedAt"),t("template.tableActions")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider py-3 px-4">{h}</th>)}</tr></thead>
        <tbody>{list.map((tpl:any)=><tr key={tpl.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
          <td className="py-3 px-4 text-sm font-medium text-gray-800">{tpl.name}</td>
          <td className="py-3 px-4 text-sm text-gray-500">{tpl.subject}</td>
          <td className="py-3 px-4 text-sm text-gray-400">{(()=>{const v=tpl.created_at;if(!v) return "-";const s=v.includes("T")&&!v.endsWith("Z")&&!v.includes("+")&&!v.includes("-",11)?v+"Z":v;return new Date(s).toLocaleString(undefined,{hour12:false});})()}</td>
          <td className="py-3 px-4 flex gap-1"><Btn variant="primary" size="sm" onClick={()=>openEdit(tpl)}>{t("common.edit")}</Btn><Btn variant="danger" size="sm" onClick={()=>del(tpl)}>{t("common.delete")}</Btn></td>
        </tr>)}</tbody>
      </table></div>
      {list.length===0&&<p className="text-center py-8 text-sm text-gray-400">{t("template.noTemplates")}</p>}
    </Card>;
  }

  // ========== 编辑器视图（新建/编辑共用） ==========
  const isCreate = mode === "create";

  return <div className="space-y-4">
    {/* 顶部导航栏 */}
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button onClick={goBack} className="text-gray-400 hover:text-gray-700 transition text-sm flex items-center gap-1">
          <span className="text-lg leading-none">&larr;</span> {t("template.backToList")}
        </button>
        <span className="text-gray-200">|</span>
        <h2 className="text-lg font-semibold text-gray-800">{isCreate?t("template.createNew"):t("template.edit",{name:f.name})}</h2>
      </div>
      <div className="flex gap-2">
        <div className="relative">
          <Btn variant="outline" onClick={()=>{if(aiLoading)return;setShowAiPrompt(!showAiPrompt);}} disabled={aiLoading} className="border-purple-300 text-purple-600 hover:bg-purple-50">
            {aiLoading?t("ai.analyzing"):t("ai.optimize")}
          </Btn>
          {showAiPrompt&&!aiLoading&&<div className="absolute right-0 top-full mt-2 w-96 bg-white border border-purple-200 rounded-xl shadow-xl p-4 z-50"
            onDragOver={e=>{e.preventDefault();e.stopPropagation();}}
            onDrop={e=>{e.preventDefault();e.stopPropagation();const files=e.dataTransfer?.files;if(files)for(let i=0;i<files.length;i++){if(files[i].type.startsWith("image/"))uploadAiImage(files[i]);}}}
          >
            {aiModels.length>1&&<div className="mb-3">
              <label className="text-xs font-medium text-gray-600 mb-1 block">{t("ai.selectModel")}</label>
              <select value={selectedModel} onChange={e=>setSelectedModel(e.target.value)} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-purple-400">
                <option value="">{t("ai.defaultModel")}</option>
                {(()=>{const groups=new Map<string,typeof aiModels>();aiModels.forEach(m=>{const k=m.provider_name||m.provider_type;if(!groups.has(k))groups.set(k,[]);groups.get(k)!.push(m);});return [...groups.entries()].map(([g,ms])=><optgroup key={g} label={`${ms[0]?.provider_type==="bedrock"?"☁️":"🔗"} ${g}`}>{ms.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</optgroup>);})()}
              </select>
            </div>}
            <p className="text-sm font-medium text-gray-700 mb-2">{t("ai.optimizePrompt")} <span className="text-gray-400 font-normal">（{t("common.optional")}）</span></p>
            <textarea
              value={aiPrompt}
              onChange={e=>setAiPrompt(e.target.value)}
              onPaste={e=>{const items=e.clipboardData?.items;if(items)for(let i=0;i<items.length;i++){if(items[i].type.startsWith("image/")){e.preventDefault();const file=items[i].getAsFile();if(file)uploadAiImage(file);return;}}}}
              placeholder={t("ai.optimizePromptPlaceholder")}
              className="w-full border border-gray-200 rounded-lg p-3 text-sm resize-none outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-300"
              rows={3}
              autoFocus
            />
            {aiImages.length>0&&(
              <div className="flex flex-wrap gap-2 mt-2">
                {aiImages.map((img,i)=>(
                  <div key={i} className="relative group">
                    <img src={img.url.startsWith("http")?img.url:`${API}${img.url}`} alt={img.name} className="w-16 h-16 object-cover rounded-lg border border-gray-200"/>
                    <button onClick={()=>setAiImages(prev=>prev.filter((_,j)=>j!==i))}
                      className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition">x</button>
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-400 mt-2">{t("ai.pasteImageHint")}</p>
            <div className="flex justify-end gap-2 mt-2">
              <Btn variant="outline" size="sm" onClick={()=>{setShowAiPrompt(false);setAiImages([]);}}>{t("common.cancel")}</Btn>
              <Btn size="sm" onClick={()=>aiOptimize()} className="bg-purple-600 hover:bg-purple-700 text-white">{t("ai.startOptimize")}</Btn>
            </div>
          </div>}
        </div>
        <div className="relative">
          <Btn variant="outline" onClick={()=>{if(evalLoading)return;if(aiModels.length>1)setShowEvalPanel(!showEvalPanel);else runEval();}} disabled={evalLoading} className="border-cyan-300 text-cyan-600 hover:bg-cyan-50">
            {evalLoading?t("ai.evaluating"):t("ai.evaluate")}
          </Btn>
          {showEvalPanel&&aiModels.length>1&&!evalLoading&&<div className="absolute right-0 top-full mt-2 w-72 bg-white border border-cyan-200 rounded-xl shadow-xl p-3 z-50">
            <p className="text-xs font-medium text-gray-700 mb-2">{t("ai.selectEvalModels")}</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">{aiModels.map(m=>(
              <label key={m.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-cyan-50 cursor-pointer">
                <input type="checkbox" className="rounded accent-cyan-500" checked={evalModels.includes(m.id)} onChange={()=>toggleEvalModel(m.id)}/>
                <span className="text-xs">{m.provider_type==="bedrock"?"☁️":"🔗"}</span>
                <span className="text-sm text-gray-700">{m.name}</span>
              </label>
            ))}</div>
            <div className="flex justify-end gap-2 mt-2 pt-2 border-t border-gray-100">
              <button onClick={()=>setEvalModels(aiModels.map(m=>m.id))} className="text-xs text-cyan-600">{t("ai.selectAll")}</button>
              <Btn size="sm" onClick={()=>{setShowEvalPanel(false);runEval();}} className="bg-cyan-500 hover:bg-cyan-600 text-white">{t("ai.startEval")}</Btn>
            </div>
          </div>}
        </div>
        <Btn variant="outline" onClick={goBack}>{t("common.cancel")}</Btn>
        {isCreate ? <Btn variant="success" onClick={create}>{t("template.save")}</Btn> : <Btn onClick={update}>{t("template.saveChanges")}</Btn>}
      </div>
    </div>

    {/* 插入超链接弹窗 */}
    <Modal open={showLinkModal} onClose={()=>setShowLinkModal(false)} title="插入超链接" width={420}>
      <div className="space-y-4">
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">链接地址 (URL)</label><Input value={linkUrl} onChange={(e:any)=>setLinkUrl(e.target.value)} placeholder="https://example.com"/></div>
        <div><label className="text-sm font-medium text-gray-700 mb-1.5 block">链接文字</label><Input value={linkText} onChange={(e:any)=>setLinkText(e.target.value)} placeholder="点击这里"/></div>
        <div className="flex justify-end gap-2">
          <Btn variant="outline" onClick={()=>setShowLinkModal(false)}>取消</Btn>
          <Btn onClick={()=>{if(!linkUrl||linkUrl==="https://")return;const text=linkText||linkUrl;insertSnippet(`<a href="${linkUrl}" style="color:#6366f1;text-decoration:underline;">${text}</a>`);setShowLinkModal(false);}}>插入</Btn>
        </div>
      </div>
    </Modal>

    {/* AI 优化结果（弹窗） */}
    <Modal open={showAi} onClose={()=>setShowAi(false)} title={t("ai.suggestions")} width={1000}>
      {aiResult&&<div className="space-y-4 max-h-[70vh] overflow-y-auto">
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-purple-700 mb-2">{t("ai.suggestions")}</h3>
          <ul className="space-y-1.5">{aiResult.suggestions.map((s,i)=>(
            <li key={i} className="flex gap-2 text-sm text-purple-900"><span className="text-purple-400 flex-shrink-0">{i+1}.</span><span>{s}</span></li>
          ))}</ul>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
            <p className="text-xs text-gray-400 mb-1">{t("ai.originalSubject")}</p>
            <p className="text-sm text-gray-700">{f.subject||t("template.empty")}</p>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <p className="text-xs text-green-600 mb-1">{t("ai.optimizedSubject")}</p>
            <p className="text-sm text-green-800 font-medium">{aiResult.optimized_subject}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="bg-gray-100 px-3 py-1.5 text-xs text-gray-500 font-medium border-b border-gray-200">{t("ai.originalContent")}</div>
            <iframe srcDoc={aiPreviewHtml(f.html_body)} className="w-full border-0" style={{height:280}} sandbox="allow-same-origin" title="original"/>
          </div>
          <div className="border border-green-200 rounded-lg overflow-hidden">
            <div className="bg-green-50 px-3 py-1.5 text-xs text-green-600 font-medium border-b border-green-200">{t("ai.optimizedContent")}</div>
            <iframe srcDoc={aiPreviewHtml(aiResult.optimized_html)} className="w-full border-0" style={{height:280}} sandbox="allow-same-origin" title="optimized"/>
          </div>
        </div>
        <div className="flex justify-end gap-3 pt-2 border-t border-gray-100">
          <Btn variant="outline" onClick={()=>setShowAi(false)}>{t("ai.discard")}</Btn>
          <Btn onClick={applyAi} className="bg-purple-600 hover:bg-purple-700 text-white">{t("ai.apply")}</Btn>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-3">
          <h3 className="text-sm font-semibold text-amber-700 mb-2">{t("ai.feedback")}</h3>
          <textarea
            value={aiFeedback}
            onChange={e=>setAiFeedback(e.target.value)}
            onPaste={e=>{const items=e.clipboardData?.items;if(items)for(let i=0;i<items.length;i++){if(items[i].type.startsWith("image/")){e.preventDefault();const file=items[i].getAsFile();if(file)uploadAiImage(file);return;}}}}
            placeholder={t("ai.feedbackPlaceholder")}
            className="w-full border border-amber-200 rounded-lg p-3 text-sm resize-none outline-none focus:border-amber-400 focus:ring-1 focus:ring-amber-300"
            rows={3}
          />
          {aiImages.length>0&&<div className="flex flex-wrap gap-2 mt-2">
            {aiImages.map((img,i)=><div key={i} className="relative group">
              <img src={img.url.startsWith("http")?img.url:`${API}${img.url}`} alt={img.name} className="w-14 h-14 object-cover rounded-lg border border-amber-200"/>
              <button onClick={()=>setAiImages(prev=>prev.filter((_,j)=>j!==i))} className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition">x</button>
            </div>)}
          </div>}
          <div className="flex justify-end mt-2">
            <Btn
              onClick={()=>aiOptimize(aiFeedback)}
              disabled={aiLoading||(!aiFeedback.trim()&&aiImages.length===0)}
              className="bg-amber-500 hover:bg-amber-600 text-white disabled:opacity-50"
            >{aiLoading?t("ai.reOptimizing"):t("ai.reOptimize")}</Btn>
          </div>
        </div>
      </div>}
    </Modal>

    {/* AI 评测结果 */}
    <Modal open={showEval} onClose={()=>setShowEval(false)} title={t("ai.evalReport")} width={900}>
      {evalResult?.models&&<div className="space-y-4 max-h-[75vh] overflow-y-auto">
        {/* 多模型对比综合分 */}
        {evalResult.models.length>1&&<div className="flex gap-4 justify-center py-3">
          {evalResult.models.map((m:any,i:number)=>(
            <button key={i} onClick={()=>setEvalTab(i)} className={`text-center p-3 rounded-xl border-2 min-w-[120px] transition ${evalTab===i?"border-indigo-400 bg-indigo-50":"border-gray-200 hover:border-gray-300"}`}>
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full border-3 mb-1" style={{borderColor:m.overall_score>=80?"#10B981":m.overall_score>=60?"#F59E0B":"#EF4444"}}>
                <span className="text-xl font-bold" style={{color:m.overall_score>=80?"#10B981":m.overall_score>=60?"#F59E0B":"#EF4444"}}>{m.overall_score}</span>
              </div>
              <p className="text-xs text-gray-600 font-medium truncate">{m.model_name}</p>
            </button>
          ))}
        </div>}

        {/* 单模型详情 */}
        {evalResult.models.length===1&&<div className="text-center py-3">
          <div className="inline-flex items-center justify-center w-24 h-24 rounded-full border-4" style={{borderColor:evalResult.models[0].overall_score>=80?"#10B981":evalResult.models[0].overall_score>=60?"#F59E0B":"#EF4444"}}>
            <span className="text-3xl font-bold" style={{color:evalResult.models[0].overall_score>=80?"#10B981":evalResult.models[0].overall_score>=60?"#F59E0B":"#EF4444"}}>{evalResult.models[0].overall_score}</span>
          </div>
          <p className="text-sm text-gray-500 mt-1">{evalResult.models[0].model_name}</p>
        </div>}

        {/* 当前模型维度详情 */}
        {(()=>{
          const cur=evalResult.models[evalTab];
          if(!cur) return null;
          return <div className="grid grid-cols-2 gap-3">
            {(cur.dimensions||[]).map((d:any,i:number)=>{
              const color=d.score>=80?"#10B981":d.score>=60?"#F59E0B":"#EF4444";
              const fixKey=`${cur.model_id}_${d.name}`;
              const fix=fixResults[fixKey];
              return <div key={i} className="border border-gray-200 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">{d.name}</span>
                  <div className="flex items-center gap-2">
                    {evalResult.models.length>1&&<div className="flex gap-0.5">{evalResult.models.map((m2:any,j:number)=>{const d2=m2.dimensions?.find((x:any)=>x.name===d.name);return d2?<span key={j} className="text-xs px-1 rounded" style={{background:d2.score>=80?"#ECFDF5":d2.score>=60?"#FFFBEB":"#FEF2F2",color:d2.score>=80?"#10B981":d2.score>=60?"#F59E0B":"#EF4444"}}>{d2.score}</span>:null;})}</div>}
                    <span className="text-lg font-bold" style={{color}}>{d.score}</span>
                    {d.issues?.length>0&&!fix&&<button onClick={()=>{setFixLoading(fixKey);getDimFix(d).then(()=>setFixLoading(""));}} disabled={fixLoading===fixKey} className="text-xs text-indigo-600 border border-indigo-200 rounded-lg px-2 py-0.5 hover:bg-indigo-50">{fixLoading===fixKey?"...":t("ai.dimFix")}</button>}
                  </div>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-2"><div className="h-full rounded-full" style={{width:`${d.score}%`,background:color}}/></div>
                {d.issues?.length>0&&<div className="space-y-1">{d.issues.map((issue:string,j:number)=><p key={j} className="text-xs text-red-500 flex gap-1"><span>✗</span><span>{issue}</span></p>)}</div>}
                {d.suggestions?.length>0&&<div className="space-y-1 mt-1">{d.suggestions.map((s:string,j:number)=><p key={j} className="text-xs text-green-600 flex gap-1"><span>→</span><span>{s}</span></p>)}</div>}
                {fix&&<div className="mt-2 bg-indigo-50 border border-indigo-200 rounded-lg p-3 space-y-2">
                  <p className="text-xs font-semibold text-indigo-700">{t("ai.dimFixTitle")}</p>
                  {fix.key_changes&&<p className="text-xs text-indigo-600">{fix.key_changes}</p>}
                  {(fix.fixes||[]).map((fx:any,j:number)=><div key={j} className="space-y-1">
                    <p className="text-xs text-gray-700"><strong>{fx.issue}</strong>: {fx.fix}</p>
                    {fx.code&&<pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap max-h-32">{fx.code}</pre>}
                  </div>)}
                </div>}
              </div>;
            })}
          </div>;
        })()}

        <div className="flex justify-end pt-2"><Btn variant="outline" onClick={()=>setShowEval(false)}>{t("common.close")}</Btn></div>
      </div>}
    </Modal>

    {/* 编辑器主体 */}
    <Card>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("template.name")}</label>
            {isCreate ? <Input placeholder={t("template.namePlaceholder")} value={f.name} onChange={(e:any)=>setF({...f,name:e.target.value})}/> : <Input value={f.name} disabled className="bg-gray-50 opacity-60"/>}
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("template.subject")}</label>
            <Input placeholder={t("template.subjectPlaceholder")} value={f.subject} onChange={(e:any)=>setF({...f,subject:e.target.value})}/>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-gray-700">{t("template.htmlContent")}</label>
            <div className="flex items-center">
              <span className="text-xs text-gray-500 font-medium">{t("template.sourceAndVisual")}</span>
            </div>
          </div>

          {/* 工具栏 */}
          <div className="flex flex-wrap items-center gap-1 mb-2 p-2 bg-gray-50 border border-gray-200 rounded-t-lg">
            <span className="text-xs text-gray-400 mr-1">{t("template.toolbar.insert")}</span>
            {snippets.map(s=>(
              <button key={s.label} onClick={()=>insertSnippet(s.html)} title={s.label}
                className="px-2 py-1 text-xs bg-white border border-gray-200 rounded-md hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-600 transition-all text-gray-600">
                <span className="mr-0.5">{s.icon}</span>{s.label}
              </button>
            ))}
            <span className="w-px h-5 bg-gray-200 mx-1"/>
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={e=>{const file=e.target.files?.[0];if(file)uploadImage(file);e.target.value="";}}/>
            <button onClick={()=>fileInputRef.current?.click()} disabled={uploading}
              className="px-2 py-1 text-xs bg-emerald-50 border border-emerald-200 rounded-md hover:bg-emerald-100 transition-all text-emerald-700 disabled:opacity-50">
              {uploading?t("template.uploading"):t("template.uploadImage")}
            </button>
            <button onClick={()=>insertSnippet(`<div style="text-align:center;padding:16px 0;margin-top:24px;border-top:1px solid #eee;"><a href="{{unsubscribe_url}}" style="color:#999;font-size:12px;text-decoration:underline;">${t("template.snippet.unsubText")} / Unsubscribe</a></div>\n`)}
              className="px-2 py-1 text-xs bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-all text-red-600">
              {t("template.unsubLink")}
            </button>
            <button onClick={()=>{setLinkUrl("https://");setLinkText("");setShowLinkModal(true);}}
              className="px-2 py-1 text-xs bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 transition-all text-blue-600">
              🔗 超链接
            </button>
            <span className="w-px h-5 bg-gray-200 mx-1"/>
            <span className="text-xs text-gray-400 mr-1">{t("template.toolbar.variables")}</span>
            {variables.map(v=>(
              <button key={v.val} onClick={()=>insertVariable(v.val)}
                className="px-2 py-1 text-xs bg-amber-50 border border-amber-200 rounded-md hover:bg-amber-100 transition-all text-amber-700 font-mono">
                {v.val}
              </button>
            ))}
          </div>

          {/* 编辑区 */}
          <div className="border border-gray-200 rounded-b-lg overflow-hidden flex" style={{height:"calc(100vh - 380px)",minHeight:400}}
            onDragOver={e=>{e.preventDefault();e.stopPropagation();}} onDrop={handleDrop}>
            <div className="w-1/2 border-r border-gray-200 flex flex-col">
                <div className="bg-gray-50 px-3 py-1.5 border-b border-gray-200 flex items-center gap-1.5 flex-shrink-0">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-400"/><span className="w-2.5 h-2.5 rounded-full bg-yellow-400"/><span className="w-2.5 h-2.5 rounded-full bg-green-400"/>
                  <span className="text-xs text-gray-400 ml-2">{t("template.htmlSource")}</span>
                </div>
                <textarea
                  value={f.html_body}
                  onChange={e=>setF({...f,html_body:e.target.value})}
                  onPaste={handlePaste}
                  placeholder={t("template.htmlPlaceholder")}
                  className="w-full flex-1 p-3 text-sm font-mono resize-none outline-none"
                  style={{background:"#1e1e2e",color:"#a6e3a1",caretColor:"#fff"}}
                  spellCheck={false}
                />
            </div>
            <div className="w-1/2 flex flex-col">
                <div className="bg-gray-50 px-3 py-1.5 border-b border-gray-200 flex items-center gap-1.5 flex-shrink-0">
                  <span className="text-xs text-gray-400">{t("template.visualEdit")}</span>
                  <span className="text-xs text-indigo-500 ml-auto">{t("template.editSync")}</span>
                </div>
                <div className="bg-white flex-1">
                  <iframe
                    ref={initSplitIframe}
                    className="w-full border-0 h-full"
                    title={t("template.visualEdit")}
                  />
                </div>
            </div>
          </div>
        </div>
      </div>
    </Card>

    {/* 附件管理（编辑模式，放在页面底部） */}
    {!isCreate && editId && <AttachmentSection templateId={editId} apiPrefix={apiPrefix} token={token} />}
  </div>;
}


function AttachmentSection({templateId, apiPrefix, token}: {templateId: number; apiPrefix: string; token: string}) {
  const [attachments, setAttachments] = useState<any[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const {toast} = useToast();

  const load = async () => {
    const r = await fetch(`${API}/user/templates/${templateId}/attachments`, {headers: authH(token)});
    if (r.ok) setAttachments(await r.json());
  };
  useEffect(() => { load(); }, [templateId]);

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { toast("error", "附件大小不能超过 10MB"); return; }
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await fetch(`${API}/user/templates/${templateId}/attachments`, {method: "POST", headers: {Authorization: `Bearer ${token}`}, body: form});
      if (r.ok) { toast("success", "附件已上传"); load(); }
      else { const d = await r.json(); toast("error", d.detail); }
    } catch { toast("error", "上传失败"); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const remove = async (id: number) => {
    const r = await fetch(`${API}/user/templates/${templateId}/attachments/${id}`, {method: "DELETE", headers: authH(token)});
    if (r.ok) { toast("success", "已删除"); load(); }
  };

  const fmtSize = (bytes: number) => bytes < 1024 ? `${bytes}B` : bytes < 1048576 ? `${(bytes/1024).toFixed(1)}KB` : `${(bytes/1048576).toFixed(1)}MB`;

  return <div className="bg-white border border-gray-100 rounded-xl p-4">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-semibold text-gray-700">📎 附件（{attachments.length}/5）</h3>
      <label>
        <Btn size="sm" variant="outline" className="whitespace-nowrap" onClick={() => fileRef.current?.click()} disabled={uploading || attachments.length >= 5}>
          {uploading ? "上传中..." : "+ 添加附件"}
        </Btn>
        <input ref={fileRef} type="file" className="hidden" onChange={upload} />
      </label>
    </div>
    {attachments.length === 0 ? (
      <p className="text-xs text-gray-400">暂无附件，发送邮件时不会携带附件。单个附件最大 10MB。</p>
    ) : (
      <div className="space-y-2">
        {attachments.map(att => (
          <div key={att.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-gray-400">📄</span>
              <span className="text-sm text-gray-700 truncate">{att.file_name}</span>
              <span className="text-xs text-gray-400 flex-shrink-0">{fmtSize(att.file_size)}</span>
            </div>
            <button onClick={() => remove(att.id)} className="text-red-400 hover:text-red-600 text-xs flex-shrink-0 ml-2">删除</button>
          </div>
        ))}
      </div>
    )}
  </div>;
}
