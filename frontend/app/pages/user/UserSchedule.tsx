"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, useConfirm, Card, Badge, Btn, Input, Select, Modal } from "../../components/shared";
import { useT } from "../../i18n";

function buildTypes(t:(k:string)=>string):{[k:string]:string}{
  return {once:t("schedule.typeOnce"),daily:t("schedule.typeDaily"),weekly:t("schedule.typeWeekly"),monthly:t("schedule.typeMonthly")};
}
function buildDays(t:(k:string)=>string):string[]{
  return [t("week.mon"),t("week.tue"),t("week.wed"),t("week.thu"),t("week.fri"),t("week.sat"),t("week.sun")];
}
function buildStatusMap(t:(k:string)=>string):{[k:string]:{label:string;color:string}}{
  return {
    active:{label:t("status.active"),color:"green"},paused:{label:t("status.paused"),color:"gray"},
    completed:{label:t("status.completed"),color:"blue"},cancelled:{label:t("status.cancelled"),color:"red"},
  };
}

const TIMEZONES=[
  {value:"UTC",label:"UTC",offset:0},
  {value:"Asia/Shanghai",label:"Asia/Shanghai (UTC+8)",offset:8},
  {value:"Asia/Tokyo",label:"Asia/Tokyo (UTC+9)",offset:9},
  {value:"Asia/Singapore",label:"Asia/Singapore (UTC+8)",offset:8},
  {value:"Asia/Kolkata",label:"Asia/Kolkata (UTC+5:30)",offset:5.5},
  {value:"Asia/Dubai",label:"Asia/Dubai (UTC+4)",offset:4},
  {value:"Europe/London",label:"Europe/London (UTC+0/+1)",offset:0},
  {value:"Europe/Berlin",label:"Europe/Berlin (UTC+1/+2)",offset:1},
  {value:"Europe/Paris",label:"Europe/Paris (UTC+1/+2)",offset:1},
  {value:"America/New_York",label:"America/New_York (UTC-5/-4)",offset:-5},
  {value:"America/Chicago",label:"America/Chicago (UTC-6/-5)",offset:-6},
  {value:"America/Denver",label:"America/Denver (UTC-7/-6)",offset:-7},
  {value:"America/Los_Angeles",label:"America/Los_Angeles (UTC-8/-7)",offset:-8},
  {value:"America/Sao_Paulo",label:"America/Sao_Paulo (UTC-3)",offset:-3},
  {value:"Australia/Sydney",label:"Australia/Sydney (UTC+10/+11)",offset:10},
  {value:"Pacific/Auckland",label:"Pacific/Auckland (UTC+12/+13)",offset:12},
];

function localToUtcHour(hour:number, minute:number, tz:string):{h:number;m:number}{
  const tzInfo = TIMEZONES.find(t=>t.value===tz);
  if(!tzInfo||tz==="UTC") return {h:hour,m:minute};
  const totalMin = hour*60 + minute - tzInfo.offset*60;
  let utcMin = ((totalMin % 1440) + 1440) % 1440;
  return {h:Math.floor(utcMin/60), m:utcMin%60};
}

function guessTimezone():string{
  try{
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if(TIMEZONES.find(t=>t.value===tz)) return tz;
  }catch{}
  return "UTC";
}

export default function UserSchedule() {
  const {token}=useAuth(); const {toast}=useToast(); const {confirm:cfm}=useConfirm(); const t=useT();
  const TYPES=buildTypes(t); const DAYS=buildDays(t); const STATUS_MAP=buildStatusMap(t);
  const [jobs,setJobs]=useState<any[]>([]);
  const [ts,setTs]=useState<any[]>([]); const [gs,setGs]=useState<any[]>([]);
  const [show,setShow]=useState(false);
  const [f,setF]=useState({template_id:"",group_id:"",schedule_type:"once",scheduled_time:"",cron_hour:9,cron_minute:0,day_of_week:0,day_of_month:1,timezone:guessTimezone()});

  const load=async()=>{
    const r=await fetch(`${API}/scheduled-jobs`,{headers:authH(token)});
    if(r.ok) setJobs(await r.json());
  };
  useEffect(()=>{
    load();
    Promise.all([
      fetch(`${API}/user/templates`,{headers:authH(token)}).then(r=>r.json()),
      fetch(`${API}/groups`,{headers:authH(token)}).then(r=>r.json()),
    ]).then(([tpl,g])=>{
      setTs(Array.isArray(tpl)?tpl:[]);
      setGs(Array.isArray(g?.items)?g.items:Array.isArray(g)?g:[]);
    });
  },[]);

  const openCreate=()=>{
    setF({template_id:"",group_id:"",schedule_type:"once",scheduled_time:"",cron_hour:9,cron_minute:0,day_of_week:0,day_of_month:1,timezone:guessTimezone()});
    setShow(true);
  };

  const create=async()=>{
    if(!f.template_id||!f.group_id) return toast("warning",t("schedule.selectBoth"));
    if(f.schedule_type==="once"&&!f.scheduled_time) return toast("warning",t("schedule.selectTimeError"));

    const payload:any={
      template_id:parseInt(f.template_id),group_id:parseInt(f.group_id),
      schedule_type:f.schedule_type,
    };

    if(f.schedule_type==="once"){
      const [datePart,timePart] = f.scheduled_time.split("T");
      if(!datePart||!timePart) return toast("warning",t("schedule.selectValidTime"));
      const [yyyy,mm,dd] = datePart.split("-").map(Number);
      const [hh,mi] = timePart.split(":").map(Number);
      const tzInfo = TIMEZONES.find(t=>t.value===f.timezone);
      const offsetMin = (tzInfo?.offset||0)*60;
      const d = new Date(Date.UTC(yyyy,mm-1,dd,hh,mi) - offsetMin*60000);
      payload.scheduled_time=d.toISOString();
      payload.cron_hour=d.getUTCHours();
      payload.cron_minute=d.getUTCMinutes();
    } else {
      const utc = localToUtcHour(f.cron_hour, f.cron_minute, f.timezone);
      payload.cron_hour=utc.h;
      payload.cron_minute=utc.m;
      const now=new Date();
      now.setUTCHours(utc.h,utc.m,0,0);
      payload.scheduled_time=now.toISOString();
    }
    if(f.schedule_type==="weekly") payload.day_of_week=f.day_of_week;
    if(f.schedule_type==="monthly") payload.day_of_month=f.day_of_month;

    const r=await fetch(`${API}/scheduled-jobs`,{method:"POST",headers:authH(token),body:JSON.stringify(payload)});
    if(r.ok){toast("success",t("schedule.created"));setShow(false);load();}
    else{const e=await r.json();toast("error",t("schedule.createFailed"),e.detail);}
  };

  const togglePause=async(j:any)=>{
    const newStatus=j.status==="active"?"paused":"active";
    const r=await fetch(`${API}/scheduled-jobs/${j.id}`,{method:"PUT",headers:authH(token),body:JSON.stringify({status:newStatus})});
    if(r.ok){toast("success",newStatus==="active"?t("schedule.resumed"):t("schedule.paused"));load();}
  };

  const del=async(j:any)=>{
    if(!await cfm(t("schedule.deleteTitle"),t("schedule.deleteConfirm",{template:j.template_name,group:j.group_name})))return;
    const r=await fetch(`${API}/scheduled-jobs/${j.id}`,{method:"DELETE",headers:authH(token)});
    if(r.ok){toast("success",t("schedule.deleted"));load();}
  };

  const fmtTime=(iso:string|null)=>{
    if(!iso) return "-";
    const d = new Date(iso.endsWith("Z")?iso:iso+"Z");
    return d.toLocaleString(undefined,{hour12:false,timeZoneName:"short"});
  };
  const descSchedule=(j:any)=>{
    const hh=String(j.cron_hour).padStart(2,"0");
    const mm=String(j.cron_minute).padStart(2,"0");
    const tz=" (UTC)";
    if(j.schedule_type==="once") return fmtTime(j.scheduled_time);
    if(j.schedule_type==="daily") return `${t("schedule.typeDaily")} ${hh}:${mm}${tz}`;
    if(j.schedule_type==="weekly") return `${t("schedule.typeWeekly")}${DAYS[j.day_of_week||0]} ${hh}:${mm}${tz}`;
    if(j.schedule_type==="monthly") return `${t("schedule.typeMonthly")} ${j.day_of_month||1}${t("schedule.day")||"日"} ${hh}:${mm}${tz}`;
    return "-";
  };

  const utcPreview=()=>{
    if(f.schedule_type==="once") return null;
    const utc=localToUtcHour(f.cron_hour,f.cron_minute,f.timezone);
    return t("schedule.utcPreview",{time:`${String(utc.h).padStart(2,"0")}:${String(utc.m).padStart(2,"0")}`});
  };

  return <>
    <Modal open={show} onClose={()=>setShow(false)} title={t("schedule.createTitle")} width={560}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("send.emailTemplate")}</label>
            <Select value={f.template_id} onChange={(e:any)=>setF({...f,template_id:e.target.value})}>
              <option value="">{t("schedule.selectTemplate")}</option>
              {ts.map((tpl:any)=><option key={tpl.id} value={tpl.id}>{tpl.name}</option>)}
            </Select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("send.targetGroup")}</label>
            <Select value={f.group_id} onChange={(e:any)=>setF({...f,group_id:e.target.value})}>
              <option value="">{t("schedule.selectGroup")}</option>
              {gs.map((g:any)=><option key={g.id} value={g.id}>{g.name}</option>)}
            </Select>
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("schedule.sendType")}</label>
          <div className="flex gap-2">
            {Object.entries(TYPES).map(([k,v])=>(
              <button key={k} onClick={()=>setF({...f,schedule_type:k})}
                className={`px-4 py-2 rounded-lg text-sm font-medium border transition ${f.schedule_type===k?"bg-indigo-50 border-indigo-300 text-indigo-700":"bg-white border-gray-200 text-gray-500 hover:bg-gray-50"}`}>{v}</button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("schedule.timezone")}</label>
          <Select value={f.timezone} onChange={(e:any)=>setF({...f,timezone:e.target.value})}>
            {TIMEZONES.map(tz=><option key={tz.value} value={tz.value}>{tz.label}</option>)}
          </Select>
        </div>

        {f.schedule_type==="once"&&(
          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("schedule.sendTime")}</label>
            <Input type="datetime-local" value={f.scheduled_time} onChange={(e:any)=>setF({...f,scheduled_time:e.target.value})}/>
            <p className="text-xs text-gray-400 mt-1">{t("schedule.localTime",{tz:f.timezone})}</p>
          </div>
        )}

        {f.schedule_type!=="once"&&(
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("schedule.execTime")}</label>
              <div className="flex gap-2 items-center">
                <Input type="number" min={0} max={23} value={f.cron_hour} onChange={(e:any)=>setF({...f,cron_hour:parseInt(e.target.value)||0})} className="w-20"/>
                <span className="text-gray-400 font-bold">:</span>
                <Input type="number" min={0} max={59} value={f.cron_minute} onChange={(e:any)=>setF({...f,cron_minute:parseInt(e.target.value)||0})} className="w-20"/>
              </div>
              {utcPreview()&&<p className="text-xs text-indigo-500 mt-1">{utcPreview()}</p>}
            </div>
            {f.schedule_type==="weekly"&&(
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("schedule.dayOfWeek")}</label>
                <Select value={f.day_of_week} onChange={(e:any)=>setF({...f,day_of_week:parseInt(e.target.value)})}>
                  {DAYS.map((d,i)=><option key={i} value={i}>{d}</option>)}
                </Select>
              </div>
            )}
            {f.schedule_type==="monthly"&&(
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("schedule.dayOfMonth")}</label>
                <Input type="number" min={1} max={31} value={f.day_of_month} onChange={(e:any)=>setF({...f,day_of_month:parseInt(e.target.value)||1})}/>
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="outline" onClick={()=>setShow(false)}>{t("common.cancel")}</Btn>
          <Btn variant="success" onClick={create}>{t("schedule.createBtn")}</Btn>
        </div>
      </div>
    </Modal>

    <Card title={t("schedule.title")} extra={<Btn size="sm" onClick={openCreate}>{t("schedule.create")}</Btn>}>
      {jobs.length===0?<p className="text-center py-8 text-sm text-gray-400">{t("schedule.noTasks")}</p>:
      <div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b border-gray-100">
          {[t("schedule.tableTemplate"),t("schedule.tableGroup"),t("schedule.tableType"),t("schedule.tablePlan"),t("schedule.tableStatus"),t("schedule.tableExecCount"),t("schedule.tableNextRun"),t("schedule.tableActions")].map(h=><th key={h} className="text-left text-xs font-medium text-gray-500 py-3 px-3">{h}</th>)}
        </tr></thead>
        <tbody>{jobs.map((j:any)=>{
          const st=STATUS_MAP[j.status]||{label:j.status,color:"gray"};
          return <tr key={j.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition">
            <td className="py-3 px-3 text-sm font-medium text-gray-800">{j.template_name}</td>
            <td className="py-3 px-3 text-sm text-gray-600">{j.group_name}</td>
            <td className="py-3 px-3"><Badge color="blue">{TYPES[j.schedule_type]||j.schedule_type}</Badge></td>
            <td className="py-3 px-3 text-xs text-gray-500">{descSchedule(j)}</td>
            <td className="py-3 px-3"><Badge color={st.color as any}>{st.label}</Badge></td>
            <td className="py-3 px-3 text-sm text-gray-500">{t("schedule.execCount",{count:j.run_count})}</td>
            <td className="py-3 px-3 text-xs text-gray-400">{j.next_run_at?fmtTime(j.next_run_at):"-"}</td>
            <td className="py-3 px-3">
              <div className="flex gap-1">
                {(j.status==="active"||j.status==="paused")&&(
                  <Btn variant={j.status==="active"?"warning":"success"} size="sm" onClick={()=>togglePause(j)}>
                    {j.status==="active"?t("schedule.pause"):t("schedule.resume")}
                  </Btn>
                )}
                <Btn variant="danger" size="sm" onClick={()=>del(j)}>{t("common.delete")}</Btn>
              </div>
              {j.error_message&&<p className="text-xs text-red-400 mt-1">{j.error_message}</p>}
            </td>
          </tr>;
        })}</tbody>
      </table></div>}
    </Card>
  </>;
}
