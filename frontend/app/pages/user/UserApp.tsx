"use client";
import React, { useState } from "react";
import { Sidebar } from "../../components/shared";
import { useT } from "../../i18n";
import UserDashboard from "./UserDashboard";
import UserGroups from "./UserGroups";
import UserSend from "./UserSend";
import UserSchedule from "./UserSchedule";
import SendingHistory from "./SendingHistory";
import TemplateManager from "../shared/TemplateManager";
import EmailDetails from "../shared/EmailDetails";
import UnsubscribeManager from "../shared/UnsubscribeManager";

export default function UserApp() {
  const [tab,setTab]=useState("dashboard");
  const t=useT();
  const titles: Record<string,string> = {dashboard:t("menu.dashboard"),groups:t("menu.groups"),templates:t("menu.templates"),send:t("menu.send"),schedule:t("menu.schedule"),history:t("menu.history"),details:t("menu.details"),unsub:t("menu.unsub")};
  return <div className="min-h-screen flex">
    <Sidebar menus={[{id:"dashboard",icon:"📈",label:t("menu.dashboard")},{id:"groups",icon:"📁",label:t("menu.groups")},{id:"templates",icon:"📋",label:t("menu.templates")},{id:"send",icon:"🚀",label:t("menu.send")},{id:"schedule",icon:"⏰",label:t("menu.schedule")},{id:"history",icon:"📊",label:t("menu.history")},{id:"details",icon:"📧",label:t("menu.details")},{id:"unsub",icon:"🚫",label:t("menu.unsub")}]} active={tab} setActive={setTab}/>
    <div className="flex-1 flex flex-col min-w-0">
      <header className="h-16 flex items-center px-6 bg-white border-b border-gray-100 shadow-sm flex-shrink-0"><h2 className="text-lg font-semibold text-gray-800">{titles[tab]}</h2></header>
      <main className="flex-1 p-6 overflow-auto">
        {tab==="dashboard"&&<UserDashboard/>}
        {tab==="groups"&&<UserGroups/>}
        {tab==="templates"&&<TemplateManager apiPrefix="/user/templates"/>}
        {tab==="send"&&<UserSend/>}
        {tab==="schedule"&&<UserSchedule/>}
        {tab==="history"&&<SendingHistory/>}
        {tab==="details"&&<EmailDetails/>}
        {tab==="unsub"&&<UnsubscribeManager/>}
      </main>
    </div>
  </div>;
}
