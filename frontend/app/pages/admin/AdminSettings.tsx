"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, Card, Btn, Input, Select, Badge } from "../../components/shared";
import { useT } from "../../i18n";

import UnsubPageEditor, { DEFAULT_REASONS } from "../shared/UnsubPageEditor";

const REGIONS=["us-east-1","us-west-2","eu-west-1","eu-central-1","ap-northeast-1","ap-southeast-1","ap-southeast-2","ap-south-1"];

export default function AdminSettings() {
  const [subTab,setSubTab]=useState<"ai"|"image"|"unsub"|"sso">("ai");
  const t=useT();

  return <div>
    <div className="flex gap-1 mb-5 bg-gray-100 rounded-lg p-1 w-fit">
      {([["ai",t("settings.tabAi")],["image",t("settings.tabImage")],["unsub",t("settings.tabUnsub")],["sso",t("settings.tabSso")]] as const).map(([id,label])=>(
        <button key={id} onClick={()=>setSubTab(id)} className={`px-5 py-2 text-sm rounded-md transition-all ${subTab===id?"bg-white text-indigo-600 shadow-sm font-medium":"text-gray-500 hover:text-gray-700"}`}>{label}</button>
      ))}
    </div>
    {subTab==="ai"&&<AiSettings/>}
    {subTab==="image"&&<ImageSettings/>}
    {subTab==="unsub"&&<UnsubSettings/>}
    {subTab==="sso"&&<SsoSettings/>}
  </div>;
}

function useSettings() {
  const {token}=useAuth(); const {toast}=useToast(); const t=useT();
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [f,setF]=useState<any>({});

  useEffect(()=>{
    (async()=>{
      try{const r=await fetch(`${API}/admin/settings`,{headers:authH(token)});if(r.ok)setF(await r.json());}catch{}
      finally{setLoading(false);}
    })();
  },[]);

  const save=async(payload:any)=>{
    setSaving(true);
    try{
      const r=await fetch(`${API}/admin/settings`,{method:"PUT",headers:authH(token),body:JSON.stringify(payload)});
      if(r.ok)toast("success",t("common.savedMsg"));else{const e=await r.json();toast("error",t("common.operationFailed"),e.detail);}
    }catch{toast("error",t("common.networkError"));}
    finally{setSaving(false);}
  };

  return {token,toast,loading,saving,f,setF,save,t};
}

function AiSettings() {
  const {token}=useAuth(); const {toast}=useToast(); const t=useT();
  const [providers,setProviders]=useState<any[]>([]);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [expandIdx,setExpandIdx]=useState<number|null>(null);
  const [testResult,setTestResult]=useState<any>(null);
  const [testingModel,setTestingModel]=useState("");

  useEffect(()=>{(async()=>{try{const r=await fetch(`${API}/admin/ai-models`,{headers:authH(token)});if(r.ok)setProviders(await r.json());}catch{}finally{setLoading(false);}})();},[]);

  const saveAll=async(list?:any[])=>{
    setSaving(true);
    try{const r=await fetch(`${API}/admin/ai-models`,{method:"PUT",headers:authH(token),body:JSON.stringify({models:list||providers})});if(r.ok)toast("success",t("common.savedMsg"));else{const e=await r.json();toast("error",t("common.failed"),e.detail);}}catch{toast("error",t("common.networkError"));}finally{setSaving(false);}
  };

  const addProvider=(type:string)=>{
    const p:any={id:`p_${Date.now()}`,type,name:type==="bedrock"?"AWS Bedrock":"",models:[]};
    if(type==="bedrock"){p.region="us-east-1";p.auth_mode="iam_role";}else{p.api_base="";p.api_key="";}
    setProviders([...providers,p]);setExpandIdx(providers.length);
  };
  const updateProvider=(idx:number,field:string,val:any)=>{const np=[...providers];np[idx]={...np[idx],[field]:val};setProviders(np);};
  const removeProvider=(idx:number)=>{setProviders(providers.filter((_,i)=>i!==idx));setExpandIdx(null);};

  const addModel=(pIdx:number)=>{
    const np=[...providers];
    const models=[...(np[pIdx].models||[])];
    const m:any={id:`m_${Date.now()}`,name:""};
    if(np[pIdx].type==="bedrock") m.model_id=""; else m.model="";
    models.push(m);np[pIdx]={...np[pIdx],models};setProviders(np);
  };
  const updateModel=(pIdx:number,mIdx:number,field:string,val:string)=>{
    const np=[...providers];const models=[...(np[pIdx].models||[])];models[mIdx]={...models[mIdx],[field]:val};np[pIdx]={...np[pIdx],models};setProviders(np);
  };
  const removeModel=(pIdx:number,mIdx:number)=>{
    const np=[...providers];np[pIdx]={...np[pIdx],models:np[pIdx].models.filter((_:any,i:number)=>i!==mIdx)};setProviders(np);
  };

  const testModel=async(pIdx:number,mIdx:number)=>{
    const p=providers[pIdx];const m=p.models[mIdx];
    const mid=m.id;setTestingModel(mid);setTestResult(null);
    const body:any={...p,test_model:m.model_id||m.model};delete body.models;
    try{const r=await fetch(`${API}/admin/ai-models/test`,{method:"POST",headers:authH(token),body:JSON.stringify(body)});const d=await r.json();setTestResult({mid,...d});if(d.success)toast("success",t("settings.ai.testPassed"));else toast("error",t("settings.ai.testFailed"),d.error);}catch{toast("error",t("common.networkError"));}finally{setTestingModel("");}
  };

  if(loading) return <div className="flex items-center justify-center h-32 text-gray-400">{t("common.loading")}</div>;

  return <div className="max-w-4xl space-y-4">
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-medium text-gray-600">{t("settings.ai.title")}</h3>
      <div className="flex gap-2">
        <Btn size="sm" onClick={()=>addProvider("bedrock")} className="bg-orange-500 hover:bg-orange-600 text-white">{t("settings.ai.addBedrock")}</Btn>
        <Btn size="sm" onClick={()=>addProvider("openai_compatible")} className="bg-blue-500 hover:bg-blue-600 text-white">{t("settings.ai.addOpenai")}</Btn>
      </div>
    </div>

    {providers.length===0&&<Card><p className="text-center py-8 text-sm text-gray-400">{t("settings.ai.noProviders")}</p></Card>}

    {providers.map((p,pi)=><Card key={p.id}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 cursor-pointer flex-1" onClick={()=>setExpandIdx(expandIdx===pi?null:pi)}>
          <span className="text-lg">{p.type==="bedrock"?"☁️":"🔗"}</span>
          <Badge color={p.type==="bedrock"?"orange":"blue"}>{p.type==="bedrock"?"Bedrock":"OpenAI"}</Badge>
          <span className="text-sm font-semibold text-gray-800">{p.name||t("settings.ai.unnamed")}</span>
          <span className="text-xs text-gray-400">{t("settings.ai.models",{count:(p.models||[]).length})}</span>
          <span className="text-xs text-gray-300">{expandIdx===pi?"▼":"▶"}</span>
        </div>
        <Btn size="sm" variant="danger" onClick={()=>removeProvider(pi)}>{t("common.delete")}</Btn>
      </div>

      {expandIdx===pi&&<div className="mt-4 space-y-4 border-t border-gray-100 pt-4">
        <div className="grid grid-cols-3 gap-3">
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.providerName")}</label><Input value={p.name||""} onChange={(e:any)=>updateProvider(pi,"name",e.target.value)} placeholder={p.type==="bedrock"?"AWS Bedrock":"My LiteLLM"}/></div>
          {p.type==="bedrock"&&<>
            <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.region")}</label><Select value={p.region||""} onChange={(e:any)=>updateProvider(pi,"region",e.target.value)}><option value="">{t("settings.ai.defaultRegion")}</option>{REGIONS.map(r=><option key={r} value={r}>{r}</option>)}</Select></div>
            <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.authMode")}</label><Select value={p.auth_mode||"iam_role"} onChange={(e:any)=>updateProvider(pi,"auth_mode",e.target.value)}><option value="iam_role">{t("settings.ai.iamRole")}</option><option value="ak_sk">{t("settings.ai.aksk")}</option><option value="api_key">{t("settings.ai.apiKeyMode")}</option></Select></div>
          </>}
          {p.type==="openai_compatible"&&<>
            <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.apiBase")}</label><Input value={p.api_base||""} onChange={(e:any)=>updateProvider(pi,"api_base",e.target.value)} placeholder="https://api.openai.com/v1"/></div>
            <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.apiKey")}</label><Input type="password" value={p.api_key||""} onChange={(e:any)=>updateProvider(pi,"api_key",e.target.value)} placeholder={t("settings.ai.optional")}/></div>
          </>}
        </div>
        {p.type==="bedrock"&&p.auth_mode==="ak_sk"&&<div className="grid grid-cols-2 gap-3">
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.accessKey")}</label><Input value={p.access_key||""} onChange={(e:any)=>updateProvider(pi,"access_key",e.target.value)}/></div>
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.secretKey")}</label><Input type="password" value={p.secret_key||""} onChange={(e:any)=>updateProvider(pi,"secret_key",e.target.value)}/></div>
        </div>}
        {p.type==="bedrock"&&p.auth_mode==="api_key"&&<div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.bedrockApiKey")}</label><Input type="password" value={p.bedrock_api_key||""} onChange={(e:any)=>updateProvider(pi,"bedrock_api_key",e.target.value)}/></div>}

        <div className="border-t border-gray-100 pt-3">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-semibold text-gray-700">{t("settings.ai.modelList")}</label>
            <button onClick={()=>addModel(pi)} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">{t("settings.ai.addModel")}</button>
          </div>
          {(p.models||[]).length===0&&<p className="text-xs text-gray-400 py-2">{t("settings.ai.noModels")}</p>}
          <div className="space-y-2">{(p.models||[]).map((m:any,mi:number)=>(
            <div key={m.id} className="bg-gray-50 rounded-lg px-3 py-2 space-y-2">
              <div className="grid grid-cols-12 gap-2 items-center">
                <span className="text-xs text-gray-400 col-span-1 text-center">{mi+1}</span>
                <div className="col-span-3"><Input value={m.name||""} onChange={(e:any)=>updateModel(pi,mi,"name",e.target.value)} placeholder={t("settings.ai.displayName")}/></div>
                <div className="col-span-5"><Input value={p.type==="bedrock"?(m.model_id||""):(m.model||"")} onChange={(e:any)=>updateModel(pi,mi,p.type==="bedrock"?"model_id":"model",e.target.value)} placeholder={p.type==="bedrock"?t("settings.ai.modelId")+" (global.anthropic.claude-opus-4-6-v1)":t("settings.ai.modelName")+" (gpt-4o)"} className="font-mono text-xs"/></div>
                <div className="col-span-3 flex items-center gap-1">
                  <Btn size="sm" variant="outline" onClick={()=>testModel(pi,mi)} disabled={testingModel===m.id}>{testingModel===m.id?"...":t("settings.ai.test")}</Btn>
                  <button onClick={()=>removeModel(pi,mi)} className="text-red-400 hover:text-red-600 text-lg px-1">×</button>
                  {testResult?.mid===m.id&&<span className={`text-xs truncate ${testResult.success?"text-green-600":"text-red-500"}`}>{testResult.success?"✓ "+testResult.reply:"✗ "+(testResult.error||"").slice(0,30)}</span>}
                </div>
              </div>
            </div>
          ))}</div>
        </div>
      </div>}
    </Card>)}

    <div className="flex gap-3 pt-2"><Btn onClick={()=>saveAll()} disabled={saving}>{saving?t("common.savingMsg"):t("settings.ai.saveAll")}</Btn><span className="text-xs text-gray-400 self-center">{t("settings.ai.providerCount",{count:providers.length,modelCount:providers.reduce((s:number,p:any)=>s+(p.models||[]).length,0)})}</span></div>
  </div>;
}

function ImageSettings() {
  const {token,toast,loading,saving,f,setF,save,t}=useSettings();
  const doSave=()=>{
    const mode=f.image_storage_mode||"local";
    const p:any={image_storage_mode:mode,image_base_url:f.image_base_url};
    if(mode==="s3"){
      p.image_s3_bucket=f.image_s3_bucket;p.image_s3_region=f.image_s3_region;p.image_s3_prefix=f.image_s3_prefix;p.image_s3_access_key=f.image_s3_access_key;
      if(f.image_s3_secret_key)p.image_s3_secret_key=f.image_s3_secret_key;
    }else if(mode==="r2"){
      p.image_r2_account_id=f.image_r2_account_id;p.image_r2_bucket=f.image_r2_bucket;p.image_r2_prefix=f.image_r2_prefix;p.image_r2_access_key=f.image_r2_access_key;p.image_r2_public_url=f.image_r2_public_url;
      if(f.image_r2_secret_key)p.image_r2_secret_key=f.image_r2_secret_key;
    }
    save(p);
  };
  if(loading) return <div className="flex items-center justify-center h-32 text-gray-400">{t("common.loading")}</div>;

  return <div className="max-w-3xl"><Card title={t("settings.image.title")}><div className="space-y-5">
    <div><label className="text-sm font-medium text-gray-700 mb-3 block">{t("settings.image.storageMode")}</label>
      <div className="grid grid-cols-3 gap-3">{([{id:"local",label:t("settings.image.local"),desc:t("settings.image.localDesc"),sel:"border-green-400 bg-green-50",dot:"bg-green-500"},{id:"s3",label:t("settings.image.s3"),desc:t("settings.image.s3Desc"),sel:"border-blue-400 bg-blue-50",dot:"bg-blue-500"},{id:"r2",label:t("settings.image.r2"),desc:t("settings.image.r2Desc"),sel:"border-orange-400 bg-orange-50",dot:"bg-orange-500"}] as const).map(m=>{const active=(f.image_storage_mode||"local")===m.id;return <button key={m.id} onClick={()=>setF({...f,image_storage_mode:m.id})} className={`p-3 rounded-xl border-2 text-left transition ${active?m.sel:"border-gray-200 hover:border-gray-300"}`}><div className="flex items-center gap-2 mb-1"><span className={`w-3 h-3 rounded-full ${active?m.dot:"bg-gray-300"}`}/><span className="text-sm font-semibold text-gray-800">{m.label}</span></div><p className="text-xs text-gray-500">{m.desc}</p></button>;})}</div>
    </div>
    {f.image_storage_mode==="s3"&&<div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
      <h4 className="text-sm font-semibold text-blue-800">{t("settings.image.s3Config")}</h4>
      <div className="grid grid-cols-2 gap-3"><div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.image.bucket")}</label><Input placeholder="my-email-images" value={f.image_s3_bucket||""} onChange={(e:any)=>setF({...f,image_s3_bucket:e.target.value})}/></div><div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.ai.region")}</label><Select value={f.image_s3_region||""} onChange={(e:any)=>setF({...f,image_s3_region:e.target.value})}><option value="">{t("settings.image.useEnvDefault")}</option>{REGIONS.map(r=><option key={r} value={r}>{r}</option>)}</Select></div><div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.image.keyPrefix")}</label><Input placeholder="ses-sender/images/" value={f.image_s3_prefix||""} onChange={(e:any)=>setF({...f,image_s3_prefix:e.target.value})}/></div></div>
      <h4 className="text-sm font-semibold text-blue-800 pt-2">{t("settings.image.s3Credentials")} <span className="text-gray-400 font-normal text-xs">（{t("settings.image.s3CredentialsHint")}）</span></h4>
      <div className="grid grid-cols-2 gap-3"><div><label className="text-xs font-medium text-gray-600 mb-1 block">Access Key ID</label><Input placeholder={f.image_has_s3_secret?t("settings.ai.configured"):"AKIA..."} value={f.image_s3_access_key||""} onChange={(e:any)=>setF({...f,image_s3_access_key:e.target.value})}/></div><div><label className="text-xs font-medium text-gray-600 mb-1 block">Secret Access Key</label><Input type="password" placeholder={f.image_has_s3_secret?t("settings.ai.configured"):"wJalr..."} value={f.image_s3_secret_key||""} onChange={(e:any)=>setF({...f,image_s3_secret_key:e.target.value})}/></div></div>
      {f.image_has_s3_secret&&!f.image_s3_secret_key&&<button onClick={()=>{(async()=>{await fetch(`${API}/admin/settings`,{method:"PUT",headers:authH(token),body:JSON.stringify({image_s3_access_key:"__CLEAR__",image_s3_secret_key:"__CLEAR__"})});setF((p:any)=>({...p,image_s3_access_key:"",image_has_s3_secret:false}));toast("success",t("settings.image.s3CredCleared"));})();}} className="text-xs text-red-500 hover:text-red-700 underline">{t("settings.image.clearS3")}</button>}
    </div>}
    {f.image_storage_mode==="r2"&&<div className="bg-orange-50 border border-orange-200 rounded-xl p-4 space-y-3">
      <h4 className="text-sm font-semibold text-orange-800">{t("settings.image.r2Config")}</h4>
      <div className="grid grid-cols-2 gap-3"><div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.image.r2AccountId")}</label><Input placeholder="a1b2c3d4e5f6..." value={f.image_r2_account_id||""} onChange={(e:any)=>setF({...f,image_r2_account_id:e.target.value})}/></div><div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.image.bucket")}</label><Input placeholder="my-email-images" value={f.image_r2_bucket||""} onChange={(e:any)=>setF({...f,image_r2_bucket:e.target.value})}/></div><div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.image.keyPrefix")}</label><Input placeholder="ses-sender/images/" value={f.image_r2_prefix||""} onChange={(e:any)=>setF({...f,image_r2_prefix:e.target.value})}/></div></div>
      <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.image.r2PublicUrl")} <span className="text-red-400">*</span></label><Input placeholder="https://pub-xxx.r2.dev" value={f.image_r2_public_url||""} onChange={(e:any)=>setF({...f,image_r2_public_url:e.target.value})}/><p className="text-xs text-gray-400 mt-1">{t("settings.image.r2PublicUrlHint")}</p></div>
      <h4 className="text-sm font-semibold text-orange-800 pt-2">{t("settings.image.r2Credentials")} <span className="text-gray-400 font-normal text-xs">（{t("settings.image.r2CredentialsHint")}）</span></h4>
      <div className="grid grid-cols-2 gap-3"><div><label className="text-xs font-medium text-gray-600 mb-1 block">Access Key ID</label><Input placeholder={f.image_has_r2_secret?t("settings.ai.configured"):"R2 Access Key ID"} value={f.image_r2_access_key||""} onChange={(e:any)=>setF({...f,image_r2_access_key:e.target.value})}/></div><div><label className="text-xs font-medium text-gray-600 mb-1 block">Secret Access Key</label><Input type="password" placeholder={f.image_has_r2_secret?t("settings.ai.configured"):"R2 Secret Access Key"} value={f.image_r2_secret_key||""} onChange={(e:any)=>setF({...f,image_r2_secret_key:e.target.value})}/></div></div>
      {f.image_has_r2_secret&&!f.image_r2_secret_key&&<button onClick={()=>{(async()=>{await fetch(`${API}/admin/settings`,{method:"PUT",headers:authH(token),body:JSON.stringify({image_r2_access_key:"__CLEAR__",image_r2_secret_key:"__CLEAR__"})});setF((p:any)=>({...p,image_r2_access_key:"",image_has_r2_secret:false}));toast("success",t("settings.image.r2CredCleared"));})();}} className="text-xs text-red-500 hover:text-red-700 underline">{t("settings.image.clearR2")}</button>}
    </div>}
    {f.image_storage_mode!=="r2"&&<div className="border-t border-gray-100 pt-4"><label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("settings.image.baseUrl")} <span className="text-gray-400 font-normal text-xs">（{t("common.optional")}）</span></label><Input placeholder="https://cdn.example.com" value={f.image_base_url||""} onChange={(e:any)=>setF({...f,image_base_url:e.target.value})}/><p className="text-xs text-gray-400 mt-1">{f.image_storage_mode==="s3"?t("settings.image.baseUrlHint"):t("settings.image.baseUrlHintLocal")}</p></div>}
    <div className="flex items-center gap-3 pt-2 border-t border-gray-100"><Btn onClick={doSave} disabled={saving}>{saving?t("common.savingMsg"):t("settings.ai.saveConfig")}</Btn><Badge color={f.image_storage_mode==="s3"?"blue":f.image_storage_mode==="r2"?"orange":"green"}>{f.image_storage_mode==="s3"?t("settings.image.s3Storage"):f.image_storage_mode==="r2"?t("settings.image.r2Storage"):t("settings.image.localStorage")}</Badge></div>
  </div></Card></div>;
}

function UnsubSettings() {
  const {token,toast,loading,saving,f,setF,save,t}=useSettings();
  const [form,setForm]=useState({title:"",subtitle:"",success:"",logo:"",color:"",buttonText:"",cancelText:"",emailLabel:"",senderLabel:"",reasons:DEFAULT_REASONS});
  const [inited,setInited]=useState(false);

  if(!inited&&!loading&&f.unsub_page_title!==undefined){
    let reasons=DEFAULT_REASONS;
    if(f.unsub_page_reasons){try{reasons=JSON.parse(f.unsub_page_reasons);}catch{}}
    setForm({title:f.unsub_page_title||t("unsubPage.defaultTitle"),subtitle:f.unsub_page_subtitle||"",success:f.unsub_page_success||t("unsubPage.defaultSuccess"),logo:f.unsub_page_logo||"",color:f.unsub_page_color||"#667eea",buttonText:f.unsub_page_button_text||"",cancelText:f.unsub_page_cancel_text||"",emailLabel:f.unsub_page_email_label||"",senderLabel:f.unsub_page_sender_label||"",reasons});
    setInited(true);
  }

  const doSave=()=>{
    save({unsub_page_title:form.title,unsub_page_subtitle:form.subtitle,unsub_page_success:form.success,unsub_page_logo:form.logo,unsub_page_color:form.color,unsub_page_button_text:form.buttonText,unsub_page_cancel_text:form.cancelText,unsub_page_email_label:form.emailLabel,unsub_page_sender_label:form.senderLabel,unsub_page_reasons:JSON.stringify(form.reasons)});
  };

  if(loading) return <div className="flex items-center justify-center h-32 text-gray-400">{t("common.loading")}</div>;

  return <UnsubPageEditor f={form} setF={setForm} onSave={doSave} saving={saving} title={t("settings.unsub.title")} description={t("settings.unsub.desc")}/>;
}

function SsoSettings() {
  const {token,toast,loading,saving,f,setF,save,t}=useSettings();

  const doSave=()=>save({
    sso_github_enabled:f.sso_github_enabled,sso_github_client_id:f.sso_github_client_id,
    ...(f.sso_github_client_secret?{sso_github_client_secret:f.sso_github_client_secret}:{}),
    sso_google_enabled:f.sso_google_enabled,sso_google_client_id:f.sso_google_client_id,
    ...(f.sso_google_client_secret?{sso_google_client_secret:f.sso_google_client_secret}:{}),
    sso_saml_enabled:f.sso_saml_enabled,sso_saml_idp_entity_id:f.sso_saml_idp_entity_id,
    sso_saml_idp_sso_url:f.sso_saml_idp_sso_url,sso_saml_idp_cert:f.sso_saml_idp_cert,
    sso_saml_sp_entity_id:f.sso_saml_sp_entity_id,
  });

  if(loading) return <div className="flex items-center justify-center h-32 text-gray-400">{t("common.loading")}</div>;

  const Toggle=({label,checked,onChange}:{label:string;checked:boolean;onChange:(v:boolean)=>void})=>(
    <label className="flex items-center gap-3 cursor-pointer">
      <div className={`w-10 h-6 rounded-full transition relative ${checked?"bg-indigo-500":"bg-gray-300"}`} onClick={()=>onChange(!checked)}>
        <div className={`w-4 h-4 rounded-full bg-white absolute top-1 transition ${checked?"left-5":"left-1"}`}/>
      </div>
      <span className="text-sm font-medium text-gray-700">{label}</span>
    </label>
  );

  return <div className="max-w-3xl space-y-6">
    <Card title={t("settings.sso.github")}>
      <div className="space-y-4">
        <Toggle label={t("settings.sso.enableGithub")} checked={f.sso_github_enabled==="true"} onChange={v=>setF({...f,sso_github_enabled:v?"true":"false"})}/>
        {f.sso_github_enabled==="true"&&<div className="grid grid-cols-2 gap-4">
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.clientId")}</label><Input value={f.sso_github_client_id||""} onChange={(e:any)=>setF({...f,sso_github_client_id:e.target.value})} placeholder="Iv1.xxx"/></div>
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.clientSecret")}</label><Input type="password" value={f.sso_github_client_secret||""} onChange={(e:any)=>setF({...f,sso_github_client_secret:e.target.value})} placeholder={f.sso_has_github_secret?t("settings.sso.configured"):"xxx"}/></div>
        </div>}
        {f.sso_github_enabled==="true"&&<p className="text-xs text-gray-400">{t("settings.sso.callbackUrl")} <code className="bg-gray-100 px-1 rounded">{typeof window!=="undefined"?window.location.origin:""}/api/sso/github/callback</code></p>}
      </div>
    </Card>

    <Card title={t("settings.sso.google")}>
      <div className="space-y-4">
        <Toggle label={t("settings.sso.enableGoogle")} checked={f.sso_google_enabled==="true"} onChange={v=>setF({...f,sso_google_enabled:v?"true":"false"})}/>
        {f.sso_google_enabled==="true"&&<div className="grid grid-cols-2 gap-4">
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.clientId")}</label><Input value={f.sso_google_client_id||""} onChange={(e:any)=>setF({...f,sso_google_client_id:e.target.value})} placeholder="xxx.apps.googleusercontent.com"/></div>
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.clientSecret")}</label><Input type="password" value={f.sso_google_client_secret||""} onChange={(e:any)=>setF({...f,sso_google_client_secret:e.target.value})} placeholder={f.sso_has_google_secret?t("settings.sso.configured"):"GOCSPX-xxx"}/></div>
        </div>}
        {f.sso_google_enabled==="true"&&<p className="text-xs text-gray-400">{t("settings.sso.redirectUri")} <code className="bg-gray-100 px-1 rounded">{typeof window!=="undefined"?window.location.origin:""}/api/sso/google/callback</code></p>}
      </div>
    </Card>

    <Card title={t("settings.sso.saml")}>
      <div className="space-y-4">
        <Toggle label={t("settings.sso.enableSaml")} checked={f.sso_saml_enabled==="true"} onChange={v=>setF({...f,sso_saml_enabled:v?"true":"false"})}/>
        {f.sso_saml_enabled==="true"&&<>
          <div className="grid grid-cols-2 gap-4">
            <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.idpEntityId")}</label><Input value={f.sso_saml_idp_entity_id||""} onChange={(e:any)=>setF({...f,sso_saml_idp_entity_id:e.target.value})} placeholder="https://idp.example.com/entity"/></div>
            <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.idpSsoUrl")}</label><Input value={f.sso_saml_idp_sso_url||""} onChange={(e:any)=>setF({...f,sso_saml_idp_sso_url:e.target.value})} placeholder="https://idp.example.com/sso"/></div>
          </div>
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.idpCert")}</label><textarea value={f.sso_saml_idp_cert||""} onChange={(e:any)=>setF({...f,sso_saml_idp_cert:e.target.value})} placeholder="-----BEGIN CERTIFICATE-----" className="w-full border border-gray-200 rounded-lg p-3 text-xs font-mono resize-none outline-none focus:border-indigo-400" rows={4}/></div>
          <div><label className="text-xs font-medium text-gray-600 mb-1 block">{t("settings.sso.spEntityId")}</label><Input value={f.sso_saml_sp_entity_id||""} onChange={(e:any)=>setF({...f,sso_saml_sp_entity_id:e.target.value})} placeholder="ses-sender"/></div>
          <p className="text-xs text-gray-400">{t("settings.sso.acsUrl")} <code className="bg-gray-100 px-1 rounded">{typeof window!=="undefined"?window.location.origin:""}/api/sso/saml/callback</code></p>
        </>}
      </div>
    </Card>

    <div className="flex gap-3"><Btn onClick={doSave} disabled={saving}>{saving?t("common.savingMsg"):t("settings.sso.save")}</Btn></div>
  </div>;
}
