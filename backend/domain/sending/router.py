from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
import json
import logging

from core.database import get_db
from core.deps import get_current_user, require_admin
from domain.auth.models import User
from domain.sending.schemas import BulkSendRequest, TestEmailRequest
from domain.sending import service

router = APIRouter(tags=["邮件发送"])
logger = logging.getLogger("ses-sender.webhook")


# ========== 退订端点（无需鉴权） ==========
@router.post("/unsubscribe", response_class=PlainTextResponse)
async def unsubscribe_post(request: Request, db: Session = Depends(get_db)):
    """RFC 8058 one-click unsubscribe POST handler (called by email clients)"""
    from core.unsubscribe import verify_unsubscribe_token
    from domain.sending.models import UnsubscribeRecord

    # token 可能在 query params 或 form body 中
    token = request.query_params.get("token", "")
    reason = "one-click"
    if not token:
        try:
            form = await request.form()
            token = form.get("token", "") or form.get("List-Unsubscribe", "")
            reason = form.get("reason", "") or "one-click"
        except Exception:
            pass
    if not token:
        return PlainTextResponse("missing token", status_code=400)

    result = verify_unsubscribe_token(token)
    if not result:
        return PlainTextResponse("invalid token", status_code=400)

    email, source_email = result

    existing = db.query(UnsubscribeRecord).filter(
        UnsubscribeRecord.email == email,
        UnsubscribeRecord.source_email == source_email,
    ).first()
    if not existing:
        db.add(UnsubscribeRecord(email=email, source_email=source_email, reason=reason[:64]))
        db.commit()
        from core import redis_cache
        redis_cache.sadd(f"unsub:{source_email}", email)
        logger.info(f"[Unsubscribe] {email} unsubscribed from {source_email} reason={reason}")

    return PlainTextResponse("ok", status_code=200)


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(token: str = Query(""), db: Session = Depends(get_db)):
    """退订页面 (GET) — 用户点击邮件中退订链接后到达，选择原因后确认"""
    from core.unsubscribe import verify_unsubscribe_token
    from domain.sending.models import UnsubscribeRecord
    from domain.settings.service import get_unsub_page_config
    import json as _json

    if not token:
        return HTMLResponse("<h2>Invalid link</h2>", status_code=400)

    result = verify_unsubscribe_token(token)
    if not result:
        return HTMLResponse("<h2>Invalid or expired link</h2>", status_code=400)

    email, source_email = result
    cfg = get_unsub_page_config(db, source_email=source_email)
    color = cfg["color"]
    logo_html = f'<img src="{cfg["logo"]}" alt="Logo" style="max-height:48px;margin-bottom:16px;">' if cfg["logo"] else ""

    existing = db.query(UnsubscribeRecord).filter(
        UnsubscribeRecord.email == email,
        UnsubscribeRecord.source_email == source_email,
    ).first()

    if existing:
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Already Unsubscribed</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f8f9fa}}
.card{{background:#fff;border-radius:16px;padding:48px;max-width:480px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.08)}}
h1{{color:#6b7280;font-size:24px;margin-bottom:12px}} p{{color:#9ca3af;line-height:1.6}}</style>
</head><body><div class="card">
{logo_html}
<p style="font-size:48px;margin-bottom:16px">📭</p>
<h1>您已退订</h1>
<p><strong>{email}</strong> 已不再接收来自 <strong>{source_email}</strong> 的邮件。</p>
</div></body></html>"""
        return HTMLResponse(html)

    reasons_html = ""
    for r in cfg["reasons"]:
        reasons_html += f"""<div class="reason" onclick="selectReason(this,'{r["value"]}')"><input type="radio" name="reason" value="{r["value"]}"><label>{r["label"]}</label></div>\n"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cfg["title"]}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:linear-gradient(135deg,{color} 0%,{color}cc 100%);padding:20px}}
.card{{background:#fff;border-radius:20px;padding:40px;max-width:520px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.15)}}
h1{{font-size:22px;color:#1f2937;margin-bottom:8px}}
.subtitle{{color:#6b7280;font-size:14px;margin-bottom:24px;line-height:1.5}}
.email-info{{background:#f3f4f6;border-radius:10px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:#4b5563}}
.email-info strong{{color:#111827}}
h3{{font-size:14px;color:#374151;margin-bottom:12px}}
.reasons{{display:flex;flex-direction:column;gap:8px;margin-bottom:20px}}
.reason{{display:flex;align-items:center;gap:10px;padding:12px 16px;border:2px solid #e5e7eb;border-radius:10px;cursor:pointer;transition:all .2s}}
.reason:hover{{border-color:{color}88;background:{color}08}}
.reason input{{accent-color:{color};width:16px;height:16px}}
.reason label{{font-size:14px;color:#374151;cursor:pointer;flex:1}}
.reason.selected{{border-color:{color};background:{color}08}}
.other-input{{width:100%;border:2px solid #e5e7eb;border-radius:8px;padding:10px 14px;font-size:13px;margin-top:8px;display:none;outline:none;transition:border .2s}}
.other-input:focus{{border-color:{color}}}
.btn{{width:100%;padding:14px;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:all .2s}}
.btn-primary{{background:#ef4444;color:#fff}}.btn-primary:hover{{background:#dc2626}}
.btn-primary:disabled{{background:#d1d5db;cursor:not-allowed}}
.btn-secondary{{background:#f3f4f6;color:#6b7280;margin-top:10px}}.btn-secondary:hover{{background:#e5e7eb}}
.success{{display:none;text-align:center}}
.success h2{{color:#10b981;font-size:24px;margin:16px 0 8px}}
.success p{{color:#6b7280;font-size:14px;line-height:1.6}}
</style>
</head><body>
<div class="card">
  <div id="form-view">
    {logo_html}
    <h1>{cfg["title"]}</h1>
    <p class="subtitle">{cfg["subtitle"]}</p>
    <div class="email-info">
      退订邮箱：<strong>{email}</strong><br>
      发送方：<strong>{source_email}</strong>
    </div>
    <h3>退订原因（可选）</h3>
    <div class="reasons">
      {reasons_html}
    </div>
    <input id="other-text" class="other-input" placeholder="请输入其他原因..." maxlength="200">
    <button class="btn btn-primary" id="confirm-btn" onclick="doUnsubscribe()">{cfg.get("buttonText","确认退订")}</button>
    <button class="btn btn-secondary" onclick="window.close()">取消</button>
  </div>
  <div class="success" id="success-view">
    {logo_html}
    <p style="font-size:48px">✅</p>
    <h2>{cfg["success"]}</h2>
    <p><strong>{email}</strong> 已不再接收来自 <strong>{source_email}</strong> 的邮件。</p>
    <p style="margin-top:16px;color:#9ca3af;font-size:13px">感谢您的反馈，我们会持续改进。</p>
  </div>
</div>
<script>
let selectedReason='';
function selectReason(el,val){{
  document.querySelectorAll('.reason').forEach(r=>r.classList.remove('selected'));
  el.classList.add('selected');
  el.querySelector('input').checked=true;
  selectedReason=val;
  document.getElementById('other-text').style.display=val==='other'?'block':'none';
}}
async function doUnsubscribe(){{
  const btn=document.getElementById('confirm-btn');
  btn.disabled=true;btn.textContent='处理中...';
  const reason=selectedReason==='other'?('other:'+document.getElementById('other-text').value):selectedReason;
  try{{
    const fd=new FormData();
    fd.append('token','{token}');
    fd.append('reason',reason||'web-unsubscribe');
    await fetch(window.location.pathname,{{method:'POST',body:fd}});
    document.getElementById('form-view').style.display='none';
    document.getElementById('success-view').style.display='block';
  }}catch{{btn.disabled=false;btn.textContent='{cfg.get("buttonText","确认退订")}';alert('操作失败，请重试');}}
}}
</script>
</div></body></html>"""
    return HTMLResponse(html)


# ========== SES 配额信息 ==========
@router.get("/ses-quota")
def get_ses_quota(current_user: User = Depends(get_current_user)):
    """获取当前 SES 账户的发送配额（实时）"""
    from core.ses import get_send_quota
    return get_send_quota()


@router.get("/user/daily-quota")
def get_daily_quota(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户的每日发送配额使用情况"""
    return service.get_user_daily_quota(db, current_user.id)


@router.get("/user/dashboard")
def get_user_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户的发送统计 Dashboard"""
    return service.get_user_dashboard(db, current_user.id)


# ========== 管理员：测试邮件 ==========
@router.post("/admin/test-email")
def send_test_email(req: TestEmailRequest, admin: User = Depends(require_admin)):
    try:
        return service.send_test_email(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 管理员：发送统计 ==========
@router.get("/admin/users/quotas")
def admin_users_quotas(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员：获取所有用户的当日发送量"""
    return service.get_all_users_daily_quota(db)


@router.get("/admin/sending-stats")
def admin_sending_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.get_admin_stats(db)


@router.get("/admin/sending-jobs")
def admin_all_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.get_admin_all_jobs(db, page, page_size)


# ========== 普通用户：批量发送 ==========
@router.post("/send-bulk")
def send_bulk_email(
    request: BulkSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return service.send_bulk_email(
            db=db,
            source_email=current_user.email,
            template_id=request.TemplateId,
            group_id=request.GroupId,
            user_id=current_user.id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 发送历史 ==========
@router.get("/sending-jobs/{batch_id}/metrics")
def get_batch_metrics(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定批次的 CloudWatch 指标"""
    from domain.sending.models import SendingJob
    if current_user.is_admin:
        job = db.query(SendingJob).filter(SendingJob.batch_id == batch_id).first()
    else:
        job = db.query(SendingJob).filter(SendingJob.batch_id == batch_id, SendingJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="批次不存在")
    return service.get_batch_metrics(batch_id)


@router.get("/sending-jobs/{batch_id}/details")
def get_batch_details(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定批次的每封邮件发送明细"""
    from domain.sending.models import SendingJob
    if current_user.is_admin:
        job = db.query(SendingJob).filter(SendingJob.batch_id == batch_id).first()
    else:
        job = db.query(SendingJob).filter(SendingJob.batch_id == batch_id, SendingJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="批次不存在")
    return service.get_batch_details(db, batch_id)


@router.get("/sending-jobs")
def list_sending_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_sending_jobs(db, current_user.id, page, page_size)


@router.get("/email-details")
def list_email_details(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    recipient: str = Query("", description="收件人搜索"),
    batch_id: str = Query("", description="批次ID搜索"),
    send_status: str = Query("", description="发送状态筛选"),
    delivery_status: str = Query("", description="送达状态筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """全局邮件明细查询（支持搜索、筛选、分页）"""
    return service.list_email_details(
        db=db,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
        page=page,
        page_size=page_size,
        recipient=recipient.strip(),
        batch_id=batch_id.strip(),
        send_status=send_status.strip(),
        delivery_status=delivery_status.strip(),
    )


@router.get("/email-details/export")
def export_email_details(
    recipient: str = Query(""),
    batch_id: str = Query(""),
    send_status: str = Query(""),
    delivery_status: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出邮件明细为 Excel"""
    buf = service.export_email_details(
        db=db, user_id=current_user.id, is_admin=current_user.is_admin,
        recipient=recipient.strip(), batch_id=batch_id.strip(),
        send_status=send_status.strip(), delivery_status=delivery_status.strip(),
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=email-details.xlsx"},
    )


@router.get("/sending-jobs/{batch_id}/progress")
def get_job_progress(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询发送任务的实时进度"""
    from domain.sending.models import SendingJob
    if current_user.is_admin:
        job = db.query(SendingJob).filter(SendingJob.batch_id == batch_id).first()
    else:
        job = db.query(SendingJob).filter(SendingJob.batch_id == batch_id, SendingJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {
        "batch_id": job.batch_id,
        "status": job.status,
        "total_contacts": job.total_contacts,
        "sent_count": job.sent_count or 0,
        "total_batches": job.total_batches or 0,
        "progress": round((job.sent_count or 0) / max(job.total_contacts, 1) * 100, 1),
        "error_message": job.error_message,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/unsubscribe-list")
def list_unsubscribes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="搜索邮箱"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前用户发送邮箱的退订列表"""
    import math
    from domain.sending.models import UnsubscribeRecord
    query = db.query(UnsubscribeRecord)
    if current_user.is_admin:
        pass
    else:
        if not current_user.email:
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 1}
        query = query.filter(UnsubscribeRecord.source_email == current_user.email)
    if search:
        query = query.filter(UnsubscribeRecord.email.contains(search))
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    rows = query.order_by(UnsubscribeRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [{"id": r.id, "email": r.email, "source_email": r.source_email, "reason": r.reason, "unsubscribed_at": r.unsubscribed_at.isoformat() if r.unsubscribed_at else None} for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.delete("/unsubscribe-list/{record_id}")
def delete_unsubscribe(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除退订记录（恢复发送）"""
    from domain.sending.models import UnsubscribeRecord
    record = db.query(UnsubscribeRecord).filter(UnsubscribeRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not current_user.is_admin and record.source_email != current_user.email:
        raise HTTPException(status_code=403, detail="无权操作")
    _src, _email = record.source_email, record.email
    db.delete(record)
    db.commit()
    from core import redis_cache
    redis_cache.srem(f"unsub:{_src}", _email)
    return {"message": "已恢复，该邮箱将重新接收邮件"}


@router.post("/unsubscribe-list/batch-delete")
def batch_delete_unsubscribe(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量删除退订记录（批量恢复发送）"""
    from domain.sending.models import UnsubscribeRecord
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="未选择记录")
    query = db.query(UnsubscribeRecord).filter(UnsubscribeRecord.id.in_(ids))
    if not current_user.is_admin:
        query = query.filter(UnsubscribeRecord.source_email == current_user.email)
    affected = query.all()
    pairs = [(r.source_email, r.email) for r in affected]
    count = query.delete(synchronize_session=False)
    db.commit()
    from core import redis_cache
    for _src, _email in pairs:
        redis_cache.srem(f"unsub:{_src}", _email)
    return {"message": f"已恢复 {count} 条记录"}


# ========== 定时发送 ==========
from domain.sending.schemas import ScheduledJobCreate, ScheduledJobUpdate, ScheduledJobOut


@router.get("/scheduled-jobs", response_model=list[ScheduledJobOut])
def list_scheduled_jobs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_scheduled_jobs(db, current_user.id)


@router.post("/scheduled-jobs", response_model=ScheduledJobOut)
def create_scheduled_job(data: ScheduledJobCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.create_scheduled_job(db, current_user.id, data)


@router.put("/scheduled-jobs/{job_id}", response_model=ScheduledJobOut)
def update_scheduled_job(job_id: int, data: ScheduledJobUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.update_scheduled_job(db, job_id, current_user.id, data)


@router.delete("/scheduled-jobs/{job_id}")
def delete_scheduled_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.delete_scheduled_job(db, job_id, current_user.id)
