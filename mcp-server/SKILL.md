---
name: ses-email-platform
description: >-
  Operate the SES Sender email management platform via its API or MCP tool.
  Use when the user wants to send emails, check sending stats, manage contacts,
  view email delivery details, manage scheduled tasks, or any email marketing operations.
  Supports both direct API calls and the "ses" MCP tool.
---

# SES Sender 邮件平台操作指南

通过 MCP tool `ses` 或直接 HTTP API 操作 SES 邮件平台。

## MCP 工具调用方式

只有一个工具 `ses`，通过 `action` + `params` 路由：

```
ses(action="dashboard", params={})
ses(action="send", params={"template_id": 3, "group_id": 5})
```

## 操作速查表

### 认证（必须先执行）

| action | params | 说明 |
|--------|--------|------|
| `login` | `{"username":"admin","password":"admin123"}` | 登录获取权限 |

### 数据查看

| action | params | 说明 |
|--------|--------|------|
| `dashboard` | `{}` | 今日/本月/总量、配额、送达率、7天趋势 |
| `quota` | `{}` | 今日配额：已用/剩余/总限额 |
| `history` | `{"page":1}` | 发送历史记录 |
| `metrics` | `{"batch_id":"batch-xxx"}` | 批次送达率/打开率指标 |
| `progress` | `{"batch_id":"batch-xxx"}` | 发送任务实时进度 |

### 邮件明细

| action | params | 说明 |
|--------|--------|------|
| `email_details` | `{"recipient":"test@gmail.com"}` | 按收件人搜索 |
| `email_details` | `{"batch_id":"batch-xxx"}` | 按批次搜索 |
| `email_details` | `{"send_status":"Success","delivery_status":"Bounce"}` | 按状态筛选 |

### 客群与联系人

| action | params | 说明 |
|--------|--------|------|
| `groups` | `{"search":"VIP","page":1}` | 搜索客群 |
| `group_create` | `{"name":"VIP客户","description":"高价值客户"}` | 创建客群 |
| `group_delete` | `{"group_id":5}` | 删除客群（含所有联系人） |
| `contacts` | `{"group_id":5,"search":"gmail","page":1}` | 查看联系人 |
| `contact_add` | `{"group_id":5,"email":"test@example.com","name":"张三"}` | 添加联系人 |
| `contact_add` | `{"group_id":5,"email":"test@example.com","name":"张三","attributes":"{\"company\":\"Acme\"}"}` | 添加联系人（带属性） |
| `contact_delete` | `{"contact_id":10}` | 删除联系人 |

### 邮件模版

| action | params | 说明 |
|--------|--------|------|
| `templates` | `{}` | 列出所有模版（返回 id, name, subject） |

### 发送邮件

| action | params | 说明 |
|--------|--------|------|
| `send` | `{"template_id":3,"group_id":5}` | 异步发送，返回 batch_id |

发送流程：
1. `templates` → 获取模版 ID
2. `groups` → 获取客群 ID
3. `send` → 创建发送任务
4. `progress` → 轮询进度直到完成

### 定时发送

| action | params | 说明 |
|--------|--------|------|
| `scheduled_list` | `{}` | 查看所有定时任务 |
| `scheduled_create` | 见下方 | 创建定时任务 |
| `scheduled_toggle` | `{"job_id":1,"status":"paused"}` | 暂停任务 |
| `scheduled_toggle` | `{"job_id":1,"status":"active"}` | 恢复任务 |
| `scheduled_delete` | `{"job_id":1}` | 删除任务 |

创建定时任务参数：
```json
// 单次：2026-04-20 上午9点发送
{"template_id":3,"group_id":5,"schedule_type":"once","scheduled_time":"2026-04-20T09:00:00"}

// 每天 UTC 9:00
{"template_id":3,"group_id":5,"schedule_type":"daily","cron_hour":9,"cron_minute":0,"scheduled_time":"2026-04-15T09:00:00"}

// 每周一 UTC 9:00
{"template_id":3,"group_id":5,"schedule_type":"weekly","cron_hour":9,"cron_minute":0,"day_of_week":0,"scheduled_time":"2026-04-15T09:00:00"}

// 每月1号 UTC 9:00
{"template_id":3,"group_id":5,"schedule_type":"monthly","cron_hour":9,"cron_minute":0,"day_of_month":1,"scheduled_time":"2026-04-15T09:00:00"}
```

### 退订管理

| action | params | 说明 |
|--------|--------|------|
| `unsubscribes` | `{"search":"gmail","page":1}` | 查看退订列表 |

### 用户管理（需管理员登录）

| action | params | 说明 |
|--------|--------|------|
| `users_list` | `{}` | 查看所有用户 |
| `user_create` | `{"username":"test","display_name":"测试","password":"123456","email":"test@example.com"}` | 创建用户 |
| `user_update` | `{"user_id":2,"display_name":"新名称","email":"new@example.com","daily_send_limit":2000}` | 更新用户信息 |
| `user_update` | `{"user_id":2,"is_active":false}` | 禁用用户 |
| `user_update` | `{"user_id":2,"password":"newpass"}` | 重置密码 |
| `users_quotas` | `{}` | 查看所有用户当日发送量 |

## 直接 HTTP API 调用方式（无 MCP 时）

如果 MCP 不可用，可通过 curl/fetch 直接调用：

```bash
# 基础 URL
API="http://your-server:3000/api"

# 登录
TOKEN=$(curl -s -X POST $API/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)

# 带认证请求
curl -s $API/user/dashboard -H "Authorization: Bearer $TOKEN" | jq .

# 发送邮件
curl -s -X POST $API/send-bulk \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"TemplateId":3,"GroupId":5}'
```

## 常见自然语言 → 操作映射

| 用户说 | 执行 |
|--------|------|
| "看看今天的发送数据" | `dashboard` |
| "今天还能发多少" | `quota` |
| "有哪些客群" | `groups` |
| "VIP 客群有哪些人" | `groups` → 找到 ID → `contacts` |
| "用欢迎模版给 VIP 发邮件" | `templates` → `groups` → `send` |
| "刚才发到哪了" | `progress` |
| "最近的发送记录" | `history` |
| "上次的打开率多少" | `history` → 取 batch_id → `metrics` |
| "查一下 test@gmail.com" | `email_details` |
| "每周一9点发周报" | `scheduled_create` |
| "暂停那个定时任务" | `scheduled_list` → `scheduled_toggle` |
| "谁退订了" | `unsubscribes` |
