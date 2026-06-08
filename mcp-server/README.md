# SES Sender MCP Server

将 SES Sender 邮件管理平台的功能暴露为 MCP 工具，让 AI 助手通过自然语言直接操作邮件系统。

## 三种运行模式

| 模式 | 文件 | 说明 |
|------|------|------|
| **完整 stdio** | `index.js` | 15 个独立工具，参数提示精确，上下文 ~1776 tokens |
| **精简 stdio** | `index-lite.js` | 1 个路由工具 + Skill 文档，上下文 ~204 tokens（推荐） |
| **Remote HTTP** | `index-remote.js` | HTTP 服务器模式（端口 8808），远程 AI 工具通过 URL 连接 |

## Remote 模式部署

### 独立启动

```bash
cd mcp-server
npm install
SES_SENDER_URL=http://your-server:3000/api MCP_PORT=8808 node index-remote.js
```

### Docker Compose（随 SES Sender 一起启动）

已集成到 `docker-compose.yml`，启动后自动可用：

```bash
docker-compose up -d
# MCP endpoint: http://your-server:8808/mcp
# Health check: http://your-server:8808/health
```

### 各工具连接 Remote MCP

**Claude Desktop**（`claude_desktop_config.json`）：
```json
{
  "mcpServers": {
    "ses-sender": {
      "url": "http://your-server:8808/mcp",
      "headers": {
        "x-api-key": "sk-ses-mcp-2026"
      }
    }
  }
}
```

**Claude Code**：
```bash
claude mcp add --transport http ses-sender http://your-server:8808/mcp --header "x-api-key: sk-ses-mcp-2026"
```

**Cursor**（`.cursor/mcp.json`）：
```json
{
  "mcpServers": {
    "ses-sender": {
      "url": "http://your-server:8808/mcp",
      "headers": {
        "x-api-key": "sk-ses-mcp-2026"
      }
    }
  }
}
```

**Kiro**（`.kiro/settings/mcp.json`）：
```json
{
  "mcpServers": {
    "ses-sender": {
      "url": "http://your-server:8808/mcp",
      "headers": {
        "x-api-key": "sk-ses-mcp-2026"
      }
    }
  }
}
```

> 将 `your-server` 替换为实际服务器 IP 或域名，`sk-ses-mcp-2026` 替换为 `.env` 中配置的 `MCP_API_KEY` 值。

### API Key 认证

MCP Server 通过 `MCP_API_KEY` 环境变量启用访问控制：

```bash
# .env 文件
MCP_API_KEY=sk-ses-mcp-2026
```

| 配置 | 行为 |
|------|------|
| `MCP_API_KEY` 有值 | 所有 `/mcp` 请求必须携带 API Key |
| `MCP_API_KEY` 为空 | 开放访问，无需认证（仅限开发环境） |

支持三种传递 Key 的方式：

| 方式 | 示例 |
|------|------|
| `x-api-key` 头 | `x-api-key: sk-ses-mcp-2026` |
| `Authorization` 头 | `Authorization: Bearer sk-ses-mcp-2026` |
| URL 参数 | `?key=sk-ses-mcp-2026` |

`/health` 端点无需认证，可用于监控检查。
```

## 支持的 AI 工具

| 工具 | 配置方式 |
|------|---------|
| Claude Desktop | `claude_desktop_config.json` |
| Claude Code | `claude code mcp add` |
| Cursor | `.cursor/mcp.json` |
| Cline | MCP settings |

## 可用工具（16 个）

| 工具 | 说明 | 示例自然语言 |
|------|------|-------------|
| `login` | 登录系统 | "用 admin/admin123 登录邮件系统" |
| `get_dashboard` | 查看发送数据概览 | "看一下今天的发送数据" |
| `get_daily_quota` | 查看今日配额 | "今天还能发多少封邮件" |
| `list_groups` | 查看客群列表 | "有哪些客群" |
| `list_contacts` | 查看客群联系人 | "看一下 VIP 客群的联系人" |
| `list_templates` | 查看邮件模版 | "我有哪些邮件模版" |
| `send_bulk_email` | 批量发送邮件 | "用欢迎模版给 VIP 客群发邮件" |
| `get_sending_progress` | 查看发送进度 | "刚才那批邮件发到哪了" |
| `list_sending_history` | 查看发送历史 | "最近的发送记录" |
| `get_batch_metrics` | 查看批次指标 | "上次发送的打开率多少" |
| `search_email_details` | 搜索邮件明细 | "查一下 test@gmail.com 的邮件状态" |
| `list_scheduled_jobs` | 查看定时任务 | "有哪些定时发送任务" |
| `create_scheduled_job` | 创建定时任务 | "每周一早上9点给会员发促销邮件" |
| `toggle_scheduled_job` | 暂停/恢复任务 | "暂停那个每周发送的任务" |
| `list_unsubscribes` | 查看退订列表 | "有哪些人退订了" |

## 安装配置

### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
{
  "mcpServers": {
    "ses-sender": {
      "command": "node",
      "args": ["/path/to/ses-sender/mcp-server/index.js"],
      "env": {
        "SES_SENDER_URL": "http://your-server:3000/api"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add ses-sender -- node /path/to/ses-sender/mcp-server/index.js
# 或指定服务器地址
SES_SENDER_URL=http://your-server:3000/api claude mcp add ses-sender -- node /path/to/ses-sender/mcp-server/index.js
```

### Cursor

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "ses-sender": {
      "command": "node",
      "args": ["./mcp-server/index.js"],
      "env": {
        "SES_SENDER_URL": "http://your-server:3000/api"
      }
    }
  }
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `SES_SENDER_URL` | `http://localhost:3000/api` | SES Sender 后端 API 地址 |

## 使用示例

配置好 MCP 后，可以直接用自然语言与 AI 对话：

```
用户: 登录邮件系统，用户名 admin，密码 admin123
AI: [调用 login] 登录成功！欢迎管理员...

用户: 今天发了多少邮件
AI: [调用 get_dashboard] 📊 今日发送 256 / 1000...

用户: 用"促销活动"模版给"VIP客户"客群发邮件
AI: [调用 list_templates + list_groups] 找到模版 #3 和客群 #5
    [调用 send_bulk_email] 发送任务已创建，批次 batch-a1b2c3...

用户: 发送进度怎么样
AI: [调用 get_sending_progress] 已发送 150/200（75%），发送中...

用户: 查一下 test@gmail.com 的邮件送达情况
AI: [调用 search_email_details] 已送达，打开 2 次，点击 1 次

用户: 设一个定时任务，每周一上午9点给会员发周报
AI: [调用 create_scheduled_job] 定时任务创建成功！每周一 09:00 UTC...
```
