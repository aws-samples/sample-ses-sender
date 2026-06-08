#!/usr/bin/env node

/**
 * SES Sender Remote MCP Server (Streamable HTTP)
 *
 * 启动: node index-remote.js
 * 端口: MCP_PORT (默认 8808)
 * Endpoint: http://your-server:8808/mcp
 */

import express from "express";
import { randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

const BASE_URL = process.env.SES_SENDER_URL || "http://localhost:3000/api";
const PORT = parseInt(process.env.MCP_PORT || "8808");
const API_KEY = process.env.MCP_API_KEY || "";

const sessionTokens = new Map();

async function api(sessionId, method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = sessionTokens.get(sessionId);
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const opts = { method, headers };
  if (body && method !== "GET") opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE_URL}${path}`, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

const ACTIONS = {
  login:              { method: "POST", path: "/auth/login" },
  dashboard:          { method: "GET",  path: "/user/dashboard" },
  quota:              { method: "GET",  path: "/user/daily-quota" },
  groups:             { method: "GET",  path: "/groups" },
  group_create:       { method: "POST", path: "/groups" },
  group_delete:       { method: "DELETE",path:"/groups/{group_id}" },
  contacts:           { method: "GET",  path: "/groups/{group_id}/contacts" },
  contact_add:        { method: "POST", path: "/contacts" },
  contact_delete:     { method: "DELETE",path:"/contacts/{contact_id}" },
  templates:          { method: "GET",  path: "/user/templates" },
  send:               { method: "POST", path: "/send-bulk" },
  progress:           { method: "GET",  path: "/sending-jobs/{batch_id}/progress" },
  history:            { method: "GET",  path: "/sending-jobs" },
  metrics:            { method: "GET",  path: "/sending-jobs/{batch_id}/metrics" },
  email_details:      { method: "GET",  path: "/email-details" },
  scheduled_list:     { method: "GET",  path: "/scheduled-jobs" },
  scheduled_create:   { method: "POST", path: "/scheduled-jobs" },
  scheduled_toggle:   { method: "PUT",  path: "/scheduled-jobs/{job_id}" },
  scheduled_delete:   { method: "DELETE",path:"/scheduled-jobs/{job_id}" },
  unsubscribes:       { method: "GET",  path: "/unsubscribe-list" },
  group_create:       { method: "POST", path: "/groups" },
  group_delete:       { method: "DELETE",path:"/groups/{group_id}" },
  users_list:         { method: "GET",  path: "/admin/users" },
  user_create:        { method: "POST", path: "/admin/users" },
  user_update:        { method: "PUT",  path: "/admin/users/{user_id}" },
  users_quotas:       { method: "GET",  path: "/admin/users/quotas" },
};

function registerTools(server) {
  server.tool(
    "ses",
    `操作 SES 邮件发送平台。action: ${Object.keys(ACTIONS).join(", ")}。params 为 JSON 字符串。`,
    { action: z.string().describe("操作名称"), params: z.string().optional().describe("操作参数（JSON 字符串）") },
    async ({ action, params: paramsStr }, extra) => {
      let params = {};
      if (paramsStr) { try { params = JSON.parse(paramsStr); } catch {} }

      const act = ACTIONS[action];
      if (!act) return { content: [{ type: "text", text: `未知操作: ${action}\n可用: ${Object.keys(ACTIONS).join(", ")}` }] };

      let path = act.path;
      for (const [key, val] of Object.entries(params)) {
        if (path.includes(`{${key}}`)) { path = path.replace(`{${key}}`, encodeURIComponent(String(val))); delete params[key]; }
      }

      if (act.method === "GET" && Object.keys(params).length > 0) {
        const qs = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) { if (v != null && v !== "") qs.set(k, String(v)); }
        path += `?${qs}`;
      }

      const body = act.method !== "GET" ? params : undefined;
      const sid = extra?.sessionId || "default";

      if (action === "login") {
        const data = await api(sid, "POST", path, body);
        sessionTokens.set(sid, data.access_token);
        return { content: [{ type: "text", text: `登录成功！${data.user.display_name}（${data.user.is_admin ? "管理员" : "用户"}）` }] };
      }
      if (action === "send") {
        const data = await api(sid, "POST", path, { TemplateId: params.template_id, GroupId: params.group_id });
        return { content: [{ type: "text", text: `任务已创建！批次: ${data.batch_id} 联系人: ${data.total_contacts}` }] };
      }

      const data = await api(sid, act.method, path, body);
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    }
  );
}

// ==================== Session Management ====================

const sessions = new Map();

// ==================== Express ====================

const app = express();

app.use("/health", express.json());

function authMiddleware(req, res, next) {
  if (!API_KEY) return next();
  const key = req.headers["x-api-key"]
    || (req.headers["authorization"] || "").replace(/^Bearer\s+/i, "")
    || req.query.key;
  if (!key || key !== API_KEY) {
    return res.status(401).json({ error: "Unauthorized — invalid or missing API key" });
  }
  next();
}

app.post("/mcp", authMiddleware, async (req, res) => {
  try {
    const sessionId = req.headers["mcp-session-id"];

    if (sessionId && sessions.has(sessionId)) {
      const { transport } = sessions.get(sessionId);
      await transport.handleRequest(req, res, req.body);
      return;
    }

    const server = new McpServer({ name: "ses-sender", version: "2.0.0" });
    registerTools(server);
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: () => randomUUID() });

    transport.onclose = () => {
      const sid = transport.sessionId;
      if (sid) { sessions.delete(sid); sessionTokens.delete(sid); }
    };

    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);

    const sid = transport.sessionId;
    if (sid) sessions.set(sid, { server, transport });
  } catch (e) {
    console.error("[MCP Error]", e.message);
    if (!res.headersSent) res.status(500).json({ error: e.message });
  }
});

app.get("/mcp", authMiddleware, async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  if (sessionId && sessions.has(sessionId)) {
    const { transport } = sessions.get(sessionId);
    await transport.handleRequest(req, res);
  } else {
    res.status(400).json({ error: "Invalid session. POST /mcp first." });
  }
});

app.delete("/mcp", authMiddleware, async (req, res) => {
  const sid = req.headers["mcp-session-id"];
  if (sid && sessions.has(sid)) {
    const { transport } = sessions.get(sid);
    await transport.handleRequest(req, res);
    sessions.delete(sid);
    sessionTokens.delete(sid);
  } else {
    res.status(200).json({ ok: true });
  }
});

app.get("/health", (req, res) => {
  res.json({ status: "ok", name: "ses-sender-mcp", version: "2.0.0", sessions: sessions.size, backend: BASE_URL });
});

app.listen(PORT, () => {
  console.log(`[SES Sender MCP] Remote server: http://0.0.0.0:${PORT}/mcp`);
  console.log(`[SES Sender MCP] Health: http://0.0.0.0:${PORT}/health`);
  console.log(`[SES Sender MCP] Backend: ${BASE_URL}`);
  console.log(`[SES Sender MCP] Auth: ${API_KEY ? "API Key enabled" : "OPEN (no auth — set MCP_API_KEY to enable)"}`);
});
