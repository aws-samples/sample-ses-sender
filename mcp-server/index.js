#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const BASE_URL = process.env.SES_SENDER_URL || "http://localhost:3000/api";
let AUTH_TOKEN = "";

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (AUTH_TOKEN) headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `API error ${res.status}`);
  return data;
}

function fmt(obj) {
  return JSON.stringify(obj, null, 2);
}

const server = new McpServer({
  name: "ses-sender",
  version: "1.0.0",
});

// ==================== 认证 ====================

server.tool(
  "login",
  "登录 SES Sender 系统，获取操作权限。后续所有操作都需要先登录。",
  { username: z.string().describe("用户名"), password: z.string().describe("密码") },
  async ({ username, password }) => {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    AUTH_TOKEN = data.access_token;
    return { content: [{ type: "text", text: `登录成功！欢迎 ${data.user.display_name}（${data.user.is_admin ? "管理员" : "用户"}）\n发送邮箱: ${data.user.email || "未配置"}\n每日限额: ${data.user.daily_send_limit || 1000}` }] };
  }
);

// ==================== Dashboard ====================

server.tool(
  "get_dashboard",
  "查看个人发送数据概览：今日/本月/总计发送量、配额使用、送达率、7天趋势等",
  {},
  async () => {
    const d = await api("/user/dashboard");
    const s = d.summary;
    const dl = d.delivery;
    const pct = (v, t) => t > 0 ? (v / t * 100).toFixed(1) + "%" : "0%";

    let text = `📊 发送数据概览\n${"─".repeat(40)}\n`;
    text += `📮 今日发送: ${s.today_sent} / ${s.daily_limit}（剩余 ${s.daily_remaining}）\n`;
    text += `📅 本月发送: ${s.month_sent}\n`;
    text += `📈 历史总量: ${s.total_emails}（${s.total_jobs} 个批次）\n`;
    text += `✅ 成功批次: ${s.success_jobs}  ❌ 失败: ${s.failed_jobs}\n`;
    text += `\n📬 送达指标（共 ${dl.total} 封）\n${"─".repeat(40)}\n`;
    text += `送达率: ${pct(dl.delivered, dl.total)}（${dl.delivered}）\n`;
    text += `打开率: ${pct(dl.opened, dl.total)}（${dl.opened}）\n`;
    text += `点击率: ${pct(dl.clicked, dl.total)}（${dl.clicked}）\n`;
    text += `退信率: ${pct(dl.bounced, dl.total)}（${dl.bounced}）\n`;
    text += `投诉率: ${pct(dl.complained, dl.total)}（${dl.complained}）\n`;
    text += `\n📉 最近 7 天趋势\n${"─".repeat(40)}\n`;
    d.daily_trend.forEach(t => { text += `${t.date}: ${"█".repeat(Math.min(30, Math.round(t.count / Math.max(...d.daily_trend.map(x => x.count), 1) * 30)))} ${t.count}\n`; });
    if (d.recent_jobs.length > 0) {
      text += `\n📋 最近发送\n${"─".repeat(40)}\n`;
      d.recent_jobs.forEach(j => { text += `[${j.status}] ${j.template_name} → ${j.group_name}（${j.total_contacts} 封）${j.created_at ? " " + new Date(j.created_at).toLocaleString() : ""}\n`; });
    }
    return { content: [{ type: "text", text }] };
  }
);

server.tool(
  "get_daily_quota",
  "查看今日发送配额使用情况",
  {},
  async () => {
    const q = await api("/user/daily-quota");
    return { content: [{ type: "text", text: `今日配额: ${q.today_sent} / ${q.daily_limit}（剩余 ${q.remaining} 封）` }] };
  }
);

// ==================== 客群与联系人 ====================

server.tool(
  "list_groups",
  "查看客群列表",
  { search: z.string().optional().describe("搜索关键词"), page: z.number().optional().describe("页码，默认1") },
  async ({ search, page }) => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    params.set("page", String(page || 1));
    const d = await api(`/groups?${params}`);
    if (!d.items?.length) return { content: [{ type: "text", text: "暂无客群" }] };
    let text = `客群列表（第 ${d.page}/${d.total_pages} 页，共 ${d.total} 个）\n${"─".repeat(40)}\n`;
    d.items.forEach(g => { text += `#${g.id} ${g.name}${g.description ? " - " + g.description : ""}\n`; });
    return { content: [{ type: "text", text }] };
  }
);

server.tool(
  "create_group",
  "创建新客群",
  { name: z.string().describe("客群名称"), description: z.string().optional().describe("客群描述") },
  async ({ name, description }) => {
    const d = await api("/groups", { method: "POST", body: JSON.stringify({ name, description: description || "" }) });
    return { content: [{ type: "text", text: `客群创建成功！ID: ${d.id}，名称: ${d.name}` }] };
  }
);

server.tool(
  "delete_group",
  "删除客群（同时删除其中所有联系人）",
  { group_id: z.number().describe("客群 ID") },
  async ({ group_id }) => {
    await api(`/groups/${group_id}`, { method: "DELETE" });
    return { content: [{ type: "text", text: `客群 #${group_id} 已删除` }] };
  }
);

server.tool(
  "list_contacts",
  "查看指定客群的联系人列表",
  { group_id: z.number().describe("客群 ID"), search: z.string().optional().describe("搜索邮箱或姓名"), page: z.number().optional().describe("页码") },
  async ({ group_id, search, page }) => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    params.set("page", String(page || 1));
    const d = await api(`/groups/${group_id}/contacts?${params}`);
    if (!d.items?.length) return { content: [{ type: "text", text: "该客群暂无联系人" }] };
    let text = `联系人列表（第 ${d.page}/${d.total_pages} 页，共 ${d.total} 人）\n${"─".repeat(40)}\n`;
    d.items.forEach(c => {
      text += `${c.name || "(无名)"} <${c.email}>`;
      if (c.attributes) { try { const a = JSON.parse(c.attributes); text += ` ${JSON.stringify(a)}`; } catch {} }
      text += "\n";
    });
    return { content: [{ type: "text", text }] };
  }
);

server.tool(
  "add_contact",
  "添加联系人到指定客群",
  {
    group_id: z.number().describe("客群 ID"),
    email: z.string().describe("邮箱地址"),
    name: z.string().optional().describe("姓名"),
    attributes: z.string().optional().describe("自定义属性 JSON 字符串，如 {\"company\":\"Acme\"}"),
  },
  async ({ group_id, email, name, attributes }) => {
    const body = { group_id, email, name: name || "" };
    if (attributes) body.attributes = attributes;
    const d = await api("/contacts", { method: "POST", body: JSON.stringify(body) });
    return { content: [{ type: "text", text: `联系人已添加！${name || ""} <${email}> → 客群 #${group_id}` }] };
  }
);

server.tool(
  "delete_contact",
  "删除联系人",
  { contact_id: z.number().describe("联系人 ID") },
  async ({ contact_id }) => {
    await api(`/contacts/${contact_id}`, { method: "DELETE" });
    return { content: [{ type: "text", text: `联系人 #${contact_id} 已删除` }] };
  }
);

// ==================== 邮件模版 ====================

server.tool(
  "list_templates",
  "查看邮件模版列表",
  {},
  async () => {
    const list = await api("/user/templates");
    if (!list?.length) return { content: [{ type: "text", text: "暂无模版" }] };
    let text = `邮件模版（${list.length} 个）\n${"─".repeat(40)}\n`;
    list.forEach(t => { text += `#${t.id} ${t.name} | 主题: ${t.subject}\n`; });
    return { content: [{ type: "text", text }] };
  }
);

// ==================== 发送邮件 ====================

server.tool(
  "send_bulk_email",
  "批量发送邮件：选择模版和客群，立即异步发送",
  { template_id: z.number().describe("模版 ID"), group_id: z.number().describe("客群 ID") },
  async ({ template_id, group_id }) => {
    const d = await api("/send-bulk", {
      method: "POST",
      body: JSON.stringify({ TemplateId: template_id, GroupId: group_id }),
    });
    return { content: [{ type: "text", text: `发送任务已创建！\n批次 ID: ${d.batch_id}\n联系人数: ${d.total_contacts}\n状态: ${d.status}\n\n任务在后台异步执行，可通过 get_sending_progress 查看进度。` }] };
  }
);

server.tool(
  "get_sending_progress",
  "查看某个发送任务的实时进度",
  { batch_id: z.string().describe("批次 ID") },
  async ({ batch_id }) => {
    const d = await api(`/sending-jobs/${batch_id}/progress`);
    const status = { queued: "排队中", sending: "发送中", success: "已完成", partial: "部分成功", failed: "失败" };
    return { content: [{ type: "text", text: `批次: ${d.batch_id}\n状态: ${status[d.status] || d.status}\n进度: ${d.sent_count}/${d.total_contacts}（${d.progress}%）${d.error_message ? "\n错误: " + d.error_message : ""}` }] };
  }
);

// ==================== 发送历史 ====================

server.tool(
  "list_sending_history",
  "查看发送历史记录",
  { page: z.number().optional().describe("页码，默认1") },
  async ({ page }) => {
    const d = await api(`/sending-jobs?page=${page || 1}`);
    if (!d.items?.length) return { content: [{ type: "text", text: "暂无发送记录" }] };
    const status = { queued: "排队中", sending: "发送中", success: "✅", partial: "⚠️", failed: "❌" };
    let text = `发送历史（第 ${d.page}/${d.total_pages} 页，共 ${d.total} 条）\n${"─".repeat(50)}\n`;
    d.items.forEach(j => {
      text += `${status[j.status] || j.status} ${j.batch_id.replace("batch-", "").slice(0, 8)} | ${j.template_name} → ${j.group_name} | ${j.sent_count || 0}/${j.total_contacts} 封 | ${j.created_at ? new Date(j.created_at).toLocaleString() : ""}\n`;
    });
    return { content: [{ type: "text", text }] };
  }
);

server.tool(
  "get_batch_metrics",
  "查看某个批次的送达率、打开率等指标（需要配置 CloudWatch）",
  { batch_id: z.string().describe("批次 ID") },
  async ({ batch_id }) => {
    const d = await api(`/sending-jobs/${batch_id}/metrics`);
    let text = `批次 ${batch_id} 指标\n${"─".repeat(40)}\n`;
    Object.entries(d).forEach(([k, v]) => { text += `${k}: ${v}\n`; });
    return { content: [{ type: "text", text }] };
  }
);

// ==================== 邮件明细 ====================

server.tool(
  "search_email_details",
  "搜索邮件发送明细：按收件人、批次ID、状态筛选",
  {
    recipient: z.string().optional().describe("收件人邮箱搜索"),
    batch_id: z.string().optional().describe("批次 ID 搜索"),
    send_status: z.string().optional().describe("发送状态: Success / Failed / Pending"),
    delivery_status: z.string().optional().describe("送达状态: Delivery / Bounce"),
    page: z.number().optional().describe("页码"),
  },
  async ({ recipient, batch_id, send_status, delivery_status, page }) => {
    const params = new URLSearchParams();
    if (recipient) params.set("recipient", recipient);
    if (batch_id) params.set("batch_id", batch_id);
    if (send_status) params.set("send_status", send_status);
    if (delivery_status) params.set("delivery_status", delivery_status);
    params.set("page", String(page || 1));
    const d = await api(`/email-details?${params}`);
    if (!d.items?.length) return { content: [{ type: "text", text: "无匹配的邮件明细" }] };
    let text = `邮件明细（第 ${d.page}/${d.total_pages} 页，共 ${d.total} 条）\n${"─".repeat(60)}\n`;
    d.items.forEach(e => {
      text += `${e.recipient} | 发送:${e.send_status} | 送达:${e.delivery_status || "-"} | 打开:${e.open_count} | 点击:${e.click_count}`;
      if (e.bounce_type) text += ` | 退信:${e.bounce_type}`;
      text += "\n";
    });
    return { content: [{ type: "text", text }] };
  }
);

// ==================== 定时任务 ====================

server.tool(
  "list_scheduled_jobs",
  "查看定时发送任务列表",
  {},
  async () => {
    const list = await api("/scheduled-jobs");
    if (!list?.length) return { content: [{ type: "text", text: "暂无定时任务" }] };
    const types = { once: "单次", daily: "每天", weekly: "每周", monthly: "每月" };
    const statuses = { active: "运行中", paused: "已暂停", completed: "已完成", cancelled: "已取消" };
    let text = `定时任务（${list.length} 个）\n${"─".repeat(50)}\n`;
    list.forEach(j => {
      text += `#${j.id} [${statuses[j.status] || j.status}] ${types[j.schedule_type] || j.schedule_type} | ${j.template_name} → ${j.group_name} | 已执行 ${j.run_count} 次`;
      if (j.next_run_at) text += ` | 下次: ${new Date(j.next_run_at).toLocaleString()}`;
      if (j.error_message) text += ` | 错误: ${j.error_message}`;
      text += "\n";
    });
    return { content: [{ type: "text", text }] };
  }
);

server.tool(
  "create_scheduled_job",
  "创建定时发送任务",
  {
    template_id: z.number().describe("模版 ID"),
    group_id: z.number().describe("客群 ID"),
    schedule_type: z.enum(["once", "daily", "weekly", "monthly"]).describe("类型: once=单次, daily=每天, weekly=每周, monthly=每月"),
    scheduled_time: z.string().optional().describe("单次模式: ISO 时间字符串，如 2026-04-20T09:00:00"),
    cron_hour: z.number().optional().describe("周期模式: 执行小时 (0-23 UTC)，默认 9"),
    cron_minute: z.number().optional().describe("周期模式: 执行分钟 (0-59)，默认 0"),
    day_of_week: z.number().optional().describe("每周模式: 0=周一 ... 6=周日"),
    day_of_month: z.number().optional().describe("每月模式: 1-31"),
  },
  async (params) => {
    const body = { ...params };
    if (!body.scheduled_time) {
      const now = new Date();
      now.setUTCHours(body.cron_hour || 9, body.cron_minute || 0, 0, 0);
      body.scheduled_time = now.toISOString();
    }
    const d = await api("/scheduled-jobs", { method: "POST", body: JSON.stringify(body) });
    return { content: [{ type: "text", text: `定时任务创建成功！\n#${d.id} ${d.schedule_type} | ${d.template_name} → ${d.group_name}\n下次执行: ${d.next_run_at ? new Date(d.next_run_at).toLocaleString() : "-"}` }] };
  }
);

server.tool(
  "toggle_scheduled_job",
  "暂停或恢复定时任务",
  { job_id: z.number().describe("任务 ID"), action: z.enum(["pause", "resume"]).describe("操作: pause=暂停, resume=恢复") },
  async ({ job_id, action }) => {
    const status = action === "pause" ? "paused" : "active";
    await api(`/scheduled-jobs/${job_id}`, { method: "PUT", body: JSON.stringify({ status }) });
    return { content: [{ type: "text", text: `任务 #${job_id} 已${action === "pause" ? "暂停" : "恢复"}` }] };
  }
);

// ==================== 退订管理 ====================

server.tool(
  "list_unsubscribes",
  "查看退订用户列表",
  { search: z.string().optional().describe("搜索邮箱"), page: z.number().optional().describe("页码") },
  async ({ search, page }) => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    params.set("page", String(page || 1));
    const d = await api(`/unsubscribe-list?${params}`);
    if (!d.items?.length) return { content: [{ type: "text", text: "暂无退订记录" }] };
    let text = `退订列表（第 ${d.page}/${d.total_pages} 页，共 ${d.total} 条）\n${"─".repeat(40)}\n`;
    d.items.forEach(r => { text += `${r.email}（来自 ${r.source_email}）| 原因: ${r.reason} | ${r.unsubscribed_at ? new Date(r.unsubscribed_at).toLocaleString() : ""}\n`; });
    return { content: [{ type: "text", text }] };
  }
);

// ==================== 启动 ====================

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);
