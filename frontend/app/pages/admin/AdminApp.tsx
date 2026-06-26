"use client";
import React, { useState } from "react";
import { Sidebar } from "../../components/shared";
import { useT } from "../../i18n";
import AdminStats from "./AdminStats";
import AdminUsers from "./AdminUsers";
import AdminIdentities from "./AdminIdentities";
import AdminTestEmail from "./AdminTestEmail";
import AdminSettings from "./AdminSettings";
import AdminSql from "./AdminSql";
import AdminLogs from "./AdminLogs";
import AdminBlacklist from "./AdminBlacklist";
import TemplateManager from "../shared/TemplateManager";

export default function AdminApp() {
  const [tab,setTab]=useState("stats");
  const t=useT();
  const titles: Record<string,string> = {stats:t("menu.stats"),users:t("menu.users"),identities:t("menu.identities"),templates:t("menu.templates"),test:t("menu.test"),settings:t("menu.settings"),sql:"SQL",logs:t("menu.logs")||"Logs",blacklist:t("menu.blacklist")||"Blacklist"};
  return <div className="min-h-screen flex">
    <Sidebar menus={[{id:"stats",icon:"📊",label:t("menu.stats")},{id:"users",icon:"👤",label:t("menu.users")},{id:"identities",icon:"🔐",label:t("menu.identities")},{id:"templates",icon:"📋",label:t("menu.templates")},{id:"test",icon:"📧",label:t("menu.test")},{id:"blacklist",icon:"🚫",label:t("menu.blacklist")||"Blacklist"},{id:"settings",icon:"⚙️",label:t("menu.settings")},{id:"sql",icon:"🗄️",label:"SQL"},{id:"logs",icon:"📄",label:t("menu.logs")||"Logs"}]} active={tab} setActive={setTab}/>
    <div className="flex-1 flex flex-col min-w-0">
      <header className="h-16 flex items-center px-6 bg-white border-b border-gray-100 shadow-sm flex-shrink-0"><h2 className="text-lg font-semibold text-gray-800">{titles[tab]}</h2></header>
      <main className="flex-1 p-6 overflow-auto">
        {tab==="stats"&&<AdminStats/>}
        {tab==="users"&&<AdminUsers/>}
        {tab==="identities"&&<AdminIdentities/>}
        {tab==="templates"&&<TemplateManager apiPrefix="/admin/templates"/>}
        {tab==="test"&&<AdminTestEmail/>}
        {tab==="settings"&&<AdminSettings/>}
        {tab==="sql"&&<AdminSql/>}
        {tab==="logs"&&<AdminLogs/>}
        {tab==="blacklist"&&<AdminBlacklist/>}
      </main>
    </div>
  </div>;
}
