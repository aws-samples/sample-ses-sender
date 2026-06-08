# SES Sender — AI Coding Guide

> This file provides project context for AI coding assistants (Claude Code, Cursor, Copilot, Kiro, etc.)

## Project Overview

AWS SES bulk email management platform with separated frontend/backend architecture. Multi-user, role-based access, contact group management, scheduled/bulk sending, and full deliverability tracking.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 / FastAPI / SQLAlchemy / Alembic / Boto3 |
| Frontend | Next.js 16 / React 19 / Tailwind CSS / TypeScript |
| Database | MySQL 8 |
| Auth | JWT (python-jose) + bcrypt |
| AWS Services | SES v2, CloudWatch, SNS, SQS, Bedrock (Claude) |
| Deployment | Docker Compose (MySQL + Backend + Frontend) |

## Architecture

```
Frontend (Next.js :3000)  ──/api proxy──▶  Backend (FastAPI :8000)  ──▶  MySQL 8
                                                   │
                                          ┌────────┼────────┐
                                          ▼        ▼        ▼
                                       AWS SES  CloudWatch  SQS
                                          │                  ▲
                                          └──▶ SNS ─────────┘
```

- Frontend reverse-proxies all `/api/*` requests to backend (only port 3000 exposed)
- Backend runs SQS polling thread + scheduled job scheduler thread as daemon threads
- DDD domain structure: `auth`, `identity`, `template`, `audience`, `sending`

## Project Structure

```
ses-sender/
├── docker-compose.yml          # 3 services: mysql, backend, frontend
├── setup-ses-events.sh         # One-click SNS+SQS AWS CLI setup
├── backend/
│   ├── main.py                 # FastAPI app + SQS worker + scheduler thread
│   ├── alembic/                # DB migrations (auto-run on startup)
│   ├── core/
│   │   ├── config.py           # All env vars
│   │   ├── database.py         # SQLAlchemy engine/session
│   │   ├── deps.py             # Auth dependencies (get_current_user, require_admin)
│   │   ├── ses.py              # SES v1/v2 clients + send quota
│   │   └── unsubscribe.py      # HMAC-SHA256 token gen/verify
│   └── domain/
│       ├── auth/               # User CRUD, JWT login, password hashing
│       ├── identity/           # SES email/domain verification
│       ├── template/           # Email template CRUD + Bedrock AI optimization
│       ├── audience/           # Contact groups, contacts, Excel import/export
│       └── sending/            # Bulk send, scheduling, metrics, events, unsubscribe
└── frontend/
    └── app/
        ├── api/[...path]/route.ts   # Reverse proxy to backend (120s timeout)
        ├── components/shared.tsx     # Shared UI: Modal, Card, Btn, Badge, Toast, etc.
        └── pages/                    # Admin/User panels
```

Each domain contains: `models.py` (SQLAlchemy), `schemas.py` (Pydantic), `service.py` (business logic), `router.py` (API routes).

## Data Models (7 tables)

### users
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| username | String(100) UNIQUE | Login name |
| display_name | String(255) | |
| hashed_password | String(255) | bcrypt |
| email | String(255) | Sending email (assigned by admin) |
| is_admin | Boolean | |
| is_active | Boolean | |
| daily_send_limit | Integer | Default 1000 |
| created_at | DateTime | |

### email_templates
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| name | String(255) | User-facing name |
| ses_name | String(255) UNIQUE | SES name: `u{user_id}_{name}` |
| subject | String(500) | Supports `{{var}}` |
| html_body | Text | Supports `{{var}}`, `{{unsubscribe_url}}` |
| text_body | Text | |
| user_id | Integer FK→users | |

### contact_groups
id, name, description, user_id (FK→users). Has cascade-delete relationship to contacts.

### contacts
id, email, name, attributes (JSON Text), group_id (FK→contact_groups).
- `attributes`: JSON string of custom key-value pairs, used for `{{var}}` replacement in templates.

### sending_jobs
id, user_id, batch_id (unique), template_name, group_name, source_email, total_contacts, sent_count, total_batches, status (queued/sending/success/partial/failed), error_message, configuration_set, created_at, finished_at.

### sending_job_details
id, job_id, batch_id, message_id, recipient, send_status, send_error, delivery_status (Delivery/Bounce/Reject), delivery_time, bounce_type, bounce_subtype, bounce_message, open_count, first_open_time, click_count, first_click_time, complaint_time, created_at.

### unsubscribe_list
id, email, source_email, reason (one-click/manual/complaint), unsubscribed_at.

### scheduled_jobs
id, user_id, template_id, group_id, template_name, group_name, schedule_type (once/daily/weekly/monthly), scheduled_time, cron_hour, cron_minute, day_of_week, day_of_month, status (active/paused/completed/cancelled), next_run_at, last_run_at, run_count, last_batch_id, error_message, created_at, updated_at.

## API Endpoints (40+)

### Auth
- `POST /auth/login` → JWT token
- `GET /auth/me` → current user
- `GET/POST/PUT /admin/users` → user CRUD (admin)

### Identity (admin)
- `GET /admin/identities` → list SES identities
- `POST /admin/identities/verify-email` / `verify-domain`

### Templates
- `GET/POST/PUT/DELETE /user/templates` → user template CRUD
- `GET/POST/PUT/DELETE /admin/templates` → admin template CRUD
- `POST /ai/optimize-template` → Bedrock AI optimization (supports iterative feedback via `user_feedback` field)

### Audience
- `GET/POST/PUT/DELETE /groups` → group CRUD
- `GET/POST/DELETE /contacts` → contact CRUD
- `POST /groups/{id}/contacts/upload` → Excel import
- `GET /groups/{id}/contacts/download` → Excel export

### Sending
- `POST /send-bulk` → async bulk send (checks daily quota, filters unsubscribed, rate-limited by SES MaxSendRate)
- `GET /sending-jobs` → user's send history
- `GET /sending-jobs/{batch_id}/progress` → real-time progress
- `GET /sending-jobs/{batch_id}/metrics` → CloudWatch metrics
- `GET /sending-jobs/{batch_id}/details` → per-email details
- `GET /email-details` → global email detail search (filter by recipient/batch/status)
- `GET /user/daily-quota` → today's quota usage
- `GET /user/dashboard` → stats dashboard (today/month/total, delivery rates, 7-day trend)

### Scheduled Sending
- `GET/POST/PUT/DELETE /scheduled-jobs` → CRUD for scheduled tasks
- Scheduler thread polls every 30s for due `next_run_at` tasks

### Unsubscribe (RFC 8058)
- `POST /unsubscribe` → one-click handler (no auth, called by email clients)
- `GET /unsubscribe` → confirmation page
- `GET /unsubscribe-list` → list unsubscribed (paginated)
- `DELETE /unsubscribe-list/{id}` → restore sending

### Other
- `POST /upload/image` → image upload (5MB max)
- `GET /ses-quota` → SES account quota
- `GET /admin/users/quotas` → all users' daily usage
- `GET /admin/sending-stats` → admin stats overview

## Key Implementation Details

### Async Bulk Sending
`send_bulk_email()` returns immediately with batch_id. A background thread (`_do_send`) sends emails one-by-one via SES v2 `send_email()` API. Rate limited to `min(MaxSendRate, 50)` per second with 1s pause between batches.

### Daily Quota Enforcement
Before sending, checks `SUM(total_contacts)` from `sending_jobs` where `created_at >= today`. Rejects with HTTP 429 if limit exceeded.

### Variable Replacement
Templates support `{{name}}`, `{{email}}`, `{{unsubscribe_url}}`, and any custom contact attribute keys. Replacement happens in `_replace_vars()` before SES send.

### One-Click Unsubscribe
Adds `List-Unsubscribe` and `List-Unsubscribe-Post` headers (only when `UNSUBSCRIBE_BASE_URL` is configured). Token is HMAC-SHA256 signed with `SECRET_KEY`.

### AI Template Optimization
Calls Bedrock with email content, returns suggestions + optimized subject/HTML. Supports iterative refinement via `user_feedback` parameter. Uses custom JSON parser `_parse_ai_json()` for robust extraction from AI response.

### SQS Event Tracking
Background thread polls SQS queue for SNS-wrapped SES events. Updates `sending_job_details` with delivery/bounce/open/click/complaint data.

### Scheduled Sending
`_calc_next_run()` computes next execution time based on schedule_type. Scheduler thread runs every 30s, finds due jobs, calls `execute_scheduled_job()` which invokes `send_bulk_email()`.

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `AWS_REGION` | Yes | `us-east-1` | AWS region for all services |
| `SECRET_KEY` | Yes | (hardcoded dev key) | JWT + HMAC signing |
| `DATABASE_URL` | Yes | MySQL connection string | Database |
| `SES_CONFIGURATION_SET` | No | `""` | VDM tracking (CloudWatch metrics) |
| `SQS_QUEUE_URL` | No | `""` | Per-email event tracking |
| `UNSUBSCRIBE_BASE_URL` | No | `""` | Public URL for unsubscribe links |
| `BEDROCK_MODEL_ID` | No | `global.anthropic.claude-opus-4-6-v1` | AI model |
| `BEDROCK_REGION` | No | same as AWS_REGION | Bedrock region |

## Conventions

- Backend: DDD domain structure, each domain self-contained
- Migrations: Alembic, auto-run on startup (`main.py`), manual revision IDs
- Auth: JWT in `Authorization: Bearer <token>` header, `get_current_user` / `require_admin` dependencies
- Frontend: Single-page app, `shared.tsx` provides all UI primitives, `API` constant points to `/api`
- API responses: paginated endpoints return `{items, total, page, page_size, total_pages}`
- Error responses: `HTTPException` with `detail` field
