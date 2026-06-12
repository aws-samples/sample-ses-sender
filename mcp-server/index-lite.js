#!/usr/bin/env node

/**
 * SES Sender MCP Server — 精简版（单工具路由模式）
 * 
 * 只注册 1 个 MCP tool，通过 action 参数路由到不同 API，
 * 避免 15 个工具定义膨胀上下文窗口。
 * 
 * AI 通过 Skill 文档了解可用操作，通过这个单一工具执行。
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const BASE_URL = process.env.SES_SENDER_URL || "http://localhost:3000/api";
let AUTH_TOKEN = "";

async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (AUTH_TOKEN) headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  const opts = { method, headers };
  if (body && method !== "GET") opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE_URL}${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

const ACTIONS = {
  // 认证与个人
  login:              { method: "POST", path: "/auth/login",          desc: "登录" },
  me:                 { method: "GET",  path: "/auth/me",             desc: "当前用户信息" },
  set_contact_email:  { method: "PUT",  path: "/user/contact-email",  desc: "修改收件邮箱" },
  // 概览与配额
  dashboard:          { method: "GET",  path: "/user/dashboard",      desc: "数据概览" },
  quota:              { method: "GET",  path: "/user/daily-quota",    desc: "今日配额" },
  ses_quota:          { method: "GET",  path: "/ses-quota",           desc: "SES 实时配额" },
  // 客群与联系人
  groups:             { method: "GET",  path: "/groups",              desc: "客群列表" },
  group_create:       { method: "POST", path: "/groups",              desc: "创建客群" },
  group_update:       { method: "PUT",  path: "/groups/{group_id}",   desc: "更新客群" },
  group_delete:       { method: "DELETE",path:"/groups/{group_id}",   desc: "删除客群" },
  contacts:           { method: "GET",  path: "/groups/{group_id}/contacts", desc: "联系人列表" },
  contact_add:        { method: "POST", path: "/contacts",            desc: "添加联系人" },
  contact_delete:     { method: "DELETE",path:"/contacts/{contact_id}",desc: "删除联系人" },
  // 模版 CRUD
  templates:          { method: "GET",  path: "/user/templates",      desc: "模版列表" },
  template_create:    { method: "POST", path: "/user/templates",      desc: "创建模版" },
  template_update:    { method: "PUT",  path: "/user/templates/{template_id}", desc: "更新模版" },
  template_delete:    { method: "DELETE",path:"/user/templates/{template_id}", desc: "删除模版" },
  // AI 模版能力
  ai_optimize:        { method: "POST", path: "/ai/optimize-template", desc: "AI 优化模版" },
  ai_evaluate:        { method: "POST", path: "/ai/evaluate-template", desc: "AI 评测模版" },
  ai_dimension_fix:   { method: "POST", path: "/ai/dimension-fix",     desc: "AI 单维度修复建议" },
  ai_models:          { method: "GET",  path: "/ai-models/available",  desc: "可用 AI 模型" },
  // 发送
  send:               { method: "POST", path: "/send-bulk",           desc: "发送邮件" },
  progress:           { method: "GET",  path: "/sending-jobs/{batch_id}/progress", desc: "发送进度" },
  history:            { method: "GET",  path: "/sending-jobs",        desc: "发送历史" },
  metrics:            { method: "GET",  path: "/sending-jobs/{batch_id}/metrics", desc: "批次指标" },
  batch_details:      { method: "GET",  path: "/sending-jobs/{batch_id}/details", desc: "批次每封邮件明细" },
  email_details:      { method: "GET",  path: "/email-details",       desc: "邮件明细搜索" },
  // 定时任务
  scheduled_list:     { method: "GET",  path: "/scheduled-jobs",      desc: "定时任务列表" },
  scheduled_create:   { method: "POST", path: "/scheduled-jobs",      desc: "创建定时任务" },
  scheduled_toggle:   { method: "PUT",  path: "/scheduled-jobs/{job_id}", desc: "暂停/恢复任务" },
  scheduled_delete:   { method: "DELETE",path:"/scheduled-jobs/{job_id}", desc: "删除任务" },
  // 退订管理
  unsubscribes:       { method: "GET",  path: "/unsubscribe-list",    desc: "退订列表" },
  unsubscribe_delete: { method: "DELETE",path:"/unsubscribe-list/{record_id}", desc: "删除退订记录（恢复发送）" },
  // 发送实体 / 域名验证（管理员）
  identities:         { method: "GET",  path: "/admin/identities",    desc: "发送实体列表" },
  identity_reputation:{ method: "GET",  path: "/admin/identities/reputation", desc: "账户声誉" },
  verify_email:       { method: "POST", path: "/admin/identities/verify-email", desc: "验证发件邮箱" },
  verify_domain:      { method: "POST", path: "/admin/identities/verify-domain", desc: "验证发件域名" },
  // 测试邮件（管理员）
  test_email:         { method: "POST", path: "/admin/test-email",    desc: "发送测试邮件" },
  // 邮箱黑名单（管理员）
  blacklist:          { method: "GET",  path: "/admin/blacklist",     desc: "黑名单列表" },
  blacklist_add:      { method: "POST", path: "/admin/blacklist",     desc: "添加黑名单" },
  blacklist_delete:   { method: "DELETE",path:"/admin/blacklist/{item_id}", desc: "删除黑名单" },
  blacklist_count:    { method: "GET",  path: "/admin/blacklist/count", desc: "黑名单数量" },
  // 用户管理（管理员）
  users_list:         { method: "GET",  path: "/admin/users",          desc: "用户列表" },
  user_create:        { method: "POST", path: "/admin/users",          desc: "创建用户" },
  user_update:        { method: "PUT",  path: "/admin/users/{user_id}",desc: "更新用户" },
  users_quotas:       { method: "GET",  path: "/admin/users/quotas",   desc: "用户配额使用" },
  // 管理员统计
  admin_stats:        { method: "GET",  path: "/admin/sending-stats",  desc: "管理员发送统计" },
  admin_jobs:         { method: "GET",  path: "/admin/sending-jobs",   desc: "管理员全部发送任务" },
};

const server = new McpServer({ name: "ses-sender", version: "2.0.0" });

server.tool(
  "ses",
  `操作 SES 邮件发送平台。action 可选值: ${Object.keys(ACTIONS).join(", ")}。params 为 JSON 对象，包含该操作需要的参数。详见项目 Skill 文档。`,
  {
    action: z.string().describe("操作名称"),
    params: z.string().optional().describe("操作参数（JSON 字符串）"),
  },
  async ({ action, params: paramsStr }) => {
    let params = {};
    if (paramsStr) {
      try { params = JSON.parse(paramsStr); } catch { params = {}; }
    }
    const act = ACTIONS[action];
    if (!act) {
      return { content: [{ type: "text", text: `未知操作: ${action}\n可用操作: ${Object.entries(ACTIONS).map(([k,v]) => `${k}(${v.desc})`).join(", ")}` }] };
    }

    let path = act.path;
    for (const [key, val] of Object.entries(params)) {
      if (path.includes(`{${key}}`)) {
        path = path.replace(`{${key}}`, encodeURIComponent(String(val)));
        delete params[key];
      }
    }

    if (act.method === "GET" && Object.keys(params).length > 0) {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
      }
      path += `?${qs}`;
    }

    const body = act.method !== "GET" ? params : undefined;

    if (action === "login") {
      const data = await api("POST", path, body);
      AUTH_TOKEN = data.access_token;
      return { content: [{ type: "text", text: `登录成功！${data.user.display_name}（${data.user.is_admin ? "管理员" : "用户"}）发送邮箱: ${data.user.email || "未配置"} 每日限额: ${data.user.daily_send_limit || 1000}` }] };
    }

    if (action === "send") {
      const data = await api("POST", path, { TemplateId: params.template_id, GroupId: params.group_id });
      return { content: [{ type: "text", text: `发送任务已创建！批次: ${data.batch_id} 联系人: ${data.total_contacts} 状态: ${data.status}` }] };
    }

    const data = await api(act.method, path, body);
    return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}
main().catch(console.error);
