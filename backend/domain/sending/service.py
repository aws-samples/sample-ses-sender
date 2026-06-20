import uuid
import math
import json
from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException

from core.ses import ses_client, sesv2_client, SES_MAX_SEND_RATE
from core.config import SES_CONFIGURATION_SET, UNSUBSCRIBE_BASE_URL
from domain.audience.models import ContactGroup, Contact
from domain.template.models import EmailTemplate
from domain.template.service import get_ses_template_name
from domain.sending.models import SendingJob, SendingJobDetail
from domain.sending.schemas import TestEmailRequest, SendingJobOut, SendingJobDetailOut


def get_user_dashboard(db: Session, user_id: int) -> dict:
    """获取用户的发送统计 Dashboard 数据"""
    from datetime import datetime, timedelta
    from sqlalchemy import func, case

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    base = db.query(SendingJob).filter(SendingJob.user_id == user_id)

    stats = base.with_entities(
        func.count(SendingJob.id),
        func.coalesce(func.sum(SendingJob.total_contacts), 0),
        func.sum(case((SendingJob.status == "success", 1), else_=0)),
        func.sum(case((SendingJob.status == "failed", 1), else_=0)),
    ).first()
    total_jobs, total_emails, success_jobs, failed_jobs = (
        stats[0] or 0, int(stats[1] or 0), int(stats[2] or 0), int(stats[3] or 0)
    )

    today_sent = int(base.filter(SendingJob.created_at >= today_start).with_entities(
        func.coalesce(func.sum(SendingJob.total_contacts), 0)
    ).scalar())
    month_sent = int(base.filter(SendingJob.created_at >= month_start).with_entities(
        func.coalesce(func.sum(SendingJob.total_contacts), 0)
    ).scalar())

    user_batches = [r[0] for r in base.with_entities(SendingJob.batch_id).all()]
    delivery = {"total": 0, "delivered": 0, "bounced": 0, "opened": 0, "clicked": 0, "complained": 0}
    if user_batches:
        dq = db.query(SendingJobDetail).filter(SendingJobDetail.batch_id.in_(user_batches))
        delivery["total"] = dq.count()
        delivery["delivered"] = dq.filter(SendingJobDetail.delivery_status == "Delivery").count()
        delivery["bounced"] = dq.filter(SendingJobDetail.delivery_status == "Bounce").count()
        delivery["opened"] = dq.filter(SendingJobDetail.open_count > 0).count()
        delivery["clicked"] = dq.filter(SendingJobDetail.click_count > 0).count()
        delivery["complained"] = dq.filter(SendingJobDetail.complaint_time.isnot(None)).count()

    daily_trend = []
    for i in range(7):
        day = today_start - timedelta(days=6 - i)
        next_day = day + timedelta(days=1)
        count = int(base.filter(
            SendingJob.created_at >= day, SendingJob.created_at < next_day
        ).with_entities(func.coalesce(func.sum(SendingJob.total_contacts), 0)).scalar())
        daily_trend.append({"date": day.strftime("%m-%d"), "count": count})

    from domain.auth.models import User as UserModel
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    daily_limit = user.daily_send_limit if user and user.daily_send_limit else 1000

    recent_jobs = base.order_by(SendingJob.id.desc()).limit(5).all()
    recent = [{
        "batch_id": j.batch_id, "template_name": j.template_name,
        "group_name": j.group_name, "total_contacts": j.total_contacts,
        "status": j.status, "created_at": j.created_at.isoformat() if j.created_at else None,
    } for j in recent_jobs]

    return {
        "summary": {
            "total_jobs": total_jobs, "total_emails": total_emails,
            "today_sent": today_sent, "month_sent": month_sent,
            "success_jobs": success_jobs, "failed_jobs": failed_jobs,
            "daily_limit": daily_limit, "daily_remaining": max(0, daily_limit - today_sent),
        },
        "delivery": delivery,
        "daily_trend": daily_trend,
        "recent_jobs": recent,
    }


def get_user_daily_quota(db: Session, user_id: int) -> dict:
    """获取用户当日发送配额使用情况"""
    from datetime import datetime
    from sqlalchemy import func
    from domain.auth.models import User as UserModel

    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    daily_limit = (user.daily_send_limit if user and user.daily_send_limit else 1000)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sent = db.query(func.coalesce(func.sum(SendingJob.total_contacts), 0)).filter(
        SendingJob.user_id == user_id,
        SendingJob.created_at >= today_start,
    ).scalar()
    return {
        "daily_limit": daily_limit,
        "today_sent": today_sent,
        "remaining": max(0, daily_limit - today_sent),
    }


def get_all_users_daily_quota(db: Session) -> dict:
    """管理员：批量获取所有用户的当日发送配额"""
    from datetime import datetime
    from sqlalchemy import func

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(
        SendingJob.user_id,
        func.coalesce(func.sum(SendingJob.total_contacts), 0),
    ).filter(
        SendingJob.created_at >= today_start,
    ).group_by(SendingJob.user_id).all()

    return {uid: int(sent) for uid, sent in rows}


def send_test_email(req: TestEmailRequest) -> dict:
    """管理员发送测试邮件"""
    params = {
        "Source": req.source,
        "Destination": {"ToAddresses": [req.to]},
        "Message": {
            "Subject": {"Data": req.subject, "Charset": "UTF-8"},
            "Body": {"Html": {"Data": req.html_body, "Charset": "UTF-8"}},
        },
    }
    # 如果配置了 Configuration Set，附加到测试邮件
    # if SES_CONFIGURATION_SET:
    #     params["ConfigurationSetName"] = SES_CONFIGURATION_SET
    #     params["Tags"] = [{"Name": "batch_id", "Value": "test"}]

    response = ses_client.send_email(**params)
    return {"message": "测试邮件发送成功", "message_id": response.get("MessageId")}


def send_bulk_email(
    db: Session,
    source_email: str,
    template_id: int,
    group_id: int,
    user_id: int,
) -> dict:
    """普通用户批量发送邮件（异步模式：立即返回，后台线程执行发送）"""
    import threading
    import logging
    from sqlalchemy import func
    logger = logging.getLogger("ses-sender.sending")

    if not source_email:
        raise HTTPException(status_code=400, detail="您尚未配置发送邮箱，请联系管理员")

    # 检查每日发送限额
    quota = get_user_daily_quota(db, user_id)
    daily_limit = quota["daily_limit"]
    today_sent = quota["today_sent"]
    remaining = quota["remaining"]

    # 获取模版信息
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id, EmailTemplate.user_id == user_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模版不存在")

    # 校验客群归属
    group = db.query(ContactGroup).filter(
        ContactGroup.id == group_id, ContactGroup.user_id == user_id
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="客群不存在或无权操作")

    # 统计客群联系人数（不全量加载，仅 count）
    total_in_group = db.query(func.count(Contact.id)).filter(Contact.group_id == group_id).scalar() or 0
    if total_in_group == 0:
        raise HTTPException(status_code=404, detail="客群中没有联系人")

    remaining = daily_limit - today_sent
    if remaining <= 0:
        raise HTTPException(status_code=429, detail=f"今日发送配额已用完（限额 {daily_limit} 封），请明天再试")
    if total_in_group > remaining:
        raise HTTPException(
            status_code=429,
            detail=f"今日剩余配额 {remaining} 封（限额 {daily_limit}，已用 {today_sent}），该客群有 {total_in_group} 个联系人，超出配额"
        )

    # 生成唯一批次 ID
    batch_id = f"batch-{uuid.uuid4().hex[:12]}"

    tpl_name = tpl.name if tpl else "unknown"
    group_name = group.name

    # 过滤已退订的邮箱（集合查询，一次性拿退订列表）
    from domain.sending.models import UnsubscribeRecord
    unsub_emails = set(
        r[0] for r in db.query(UnsubscribeRecord.email).filter(
            UnsubscribeRecord.source_email == source_email
        ).all()
    )

    # 获取用户的收件邮箱作为 reply_to
    from domain.auth.models import User as UserModel
    _user = db.query(UserModel).filter(UserModel.id == user_id).first()
    reply_to_email = (_user.contact_email if _user and _user.contact_email else source_email) or source_email

    # 创建发送任务（状态：排队中），total_contacts 先占位，detail 写完后回填
    job = SendingJob(
        user_id=user_id,
        batch_id=batch_id,
        template_name=tpl_name,
        template_id=template_id,
        group_name=group_name,
        group_id=group_id,
        source_email=source_email,
        reply_to=reply_to_email,
        total_contacts=0,
        sent_count=0,
        total_batches=0,
        status="queued",
        configuration_set=SES_CONFIGURATION_SET or None,
    )
    db.add(job)
    db.flush()
    job_id = job.id

    # ===== 流式 + 分批 bulk insert 明细（避免全量内存 / 超大单事务）=====
    # 用 yield_per 流式遍历联系人，按邮箱去重，分批 bulk_insert_mappings 写入。
    INSERT_BATCH = 2000
    seen_emails: set = set()
    active_count = 0
    skipped_count = 0
    detail_rows: list[dict] = []

    def _flush_rows():
        if detail_rows:
            db.bulk_insert_mappings(SendingJobDetail, detail_rows)
            db.commit()
            detail_rows.clear()

    contact_q = (
        db.query(Contact.email)
        .filter(Contact.group_id == group_id)
        .yield_per(INSERT_BATCH)
    )
    for (email,) in contact_q:
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        if email in unsub_emails:
            status = "Unsubscribed"
            skipped_count += 1
        else:
            status = "Pending"
            active_count += 1
        detail_rows.append({
            "job_id": job_id,
            "batch_id": batch_id,
            "recipient": email,
            "send_status": status,
        })
        if len(detail_rows) >= INSERT_BATCH:
            _flush_rows()
    _flush_rows()

    # 回填真实联系人总数
    job.total_contacts = active_count + skipped_count
    db.commit()

    # Sender Engine（Scanner）会自动拾取 status=queued 的 job 并按 detail 分页发送。
    # 不再在请求线程里同步发送，避免大批量阻塞 HTTP / 占用内存。
    from core.sender import get_engine
    engine = get_engine()
    if engine and engine.running:
        logger.info(f"[Send] batch={batch_id} 已入队（{active_count} 待发 / {skipped_count} 跳过退订），等待 Sender Engine 处理")
    else:
        logger.warning(f"[Send] batch={batch_id} 已写入 DB(queued)，但 Sender Engine 未运行；将在引擎启动后被 Scanner 自动拾取")

    return {
        "status": "queued",
        "batch_id": batch_id,
        "source": source_email,
        "total_contacts": active_count + skipped_count,
        "active_contacts": active_count,
        "skipped_unsubscribed": skipped_count,
        "message": "发送任务已创建，正在后台执行",
    }


def get_batch_metrics(batch_id: str) -> dict:
    """从 CloudWatch 获取指定批次的送达指标"""
    import boto3
    import logging
    from datetime import datetime, timedelta
    from core.config import AWS_REGION

    logger = logging.getLogger("ses-sender.metrics")
    logger.setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info(f"[Metrics] 开始查询 batch_id={batch_id}")
    logger.info(f"[Metrics] AWS_REGION={AWS_REGION}")

    cw = boto3.client("cloudwatch", region_name=AWS_REGION)

    now = datetime.utcnow()
    start = now - timedelta(days=14)  # 查最近14天

    logger.info(f"[Metrics] 查询时间范围: {start.isoformat()} ~ {now.isoformat()}")

    # 先列出 AWS/SES 命名空间下 batch_id 维度有哪些指标，帮助排查
    try:
        list_resp = cw.list_metrics(
            Namespace="AWS/SES",
            Dimensions=[{"Name": "batch_id", "Value": batch_id}],
        )
        available_metrics = [m["MetricName"] for m in list_resp.get("Metrics", [])]
        logger.info(f"[Metrics] CloudWatch 中该 batch_id 可用的指标: {available_metrics}")
        if not available_metrics:
            logger.warning(f"[Metrics] ⚠️ CloudWatch 中没有找到 batch_id={batch_id} 的任何指标!")
            logger.warning(f"[Metrics] 可能原因: 1) Event Destination 未配置 2) Region 不匹配 3) 数据尚未到达")

            # 额外检查: 列出 AWS/SES 下所有 batch_id 维度的指标（取前5个）
            all_batch_resp = cw.list_metrics(
                Namespace="AWS/SES",
                MetricName="Send",
                Dimensions=[{"Name": "batch_id"}],
            )
            all_batches = [
                next((d["Value"] for d in m["Dimensions"] if d["Name"] == "batch_id"), "?")
                for m in all_batch_resp.get("Metrics", [])[:5]
            ]
            logger.info(f"[Metrics] CloudWatch 中存在的 batch_id 样本 (前5个): {all_batches}")
    except Exception as e:
        logger.error(f"[Metrics] list_metrics 调用失败: {e}")

    metrics_to_fetch = ["Send", "Delivery", "Bounce", "Complaint", "Open", "Click", "Reject"]
    result = {}
    debug_raw = {}

    for metric_name in metrics_to_fetch:
        try:
            query_params = {
                "Namespace": "AWS/SES",
                "MetricName": metric_name,
                "Dimensions": [{"Name": "batch_id", "Value": batch_id}],
                "StartTime": start,
                "EndTime": now,
                "Period": 86400 * 14,
                "Statistics": ["Sum"],
            }
            resp = cw.get_metric_statistics(**query_params)
            datapoints = resp.get("Datapoints", [])
            total = sum(dp.get("Sum", 0) for dp in datapoints)
            result[metric_name.lower()] = int(total)

            # 记录原始响应
            debug_raw[metric_name] = {
                "datapoints_count": len(datapoints),
                "datapoints": [{"Sum": dp.get("Sum"), "Timestamp": str(dp.get("Timestamp"))} for dp in datapoints],
                "total": int(total),
            }
            if datapoints:
                logger.info(f"[Metrics] {metric_name}: {int(total)} (datapoints={len(datapoints)})")
            else:
                logger.debug(f"[Metrics] {metric_name}: 0 (无数据点)")
        except Exception as e:
            logger.error(f"[Metrics] 查询 {metric_name} 失败: {e}")
            result[metric_name.lower()] = 0
            debug_raw[metric_name] = {"error": str(e)}

    # 计算比率
    send = result.get("send", 0)
    delivery = result.get("delivery", 0)
    opens = result.get("open", 0)
    result["delivery_rate"] = round(delivery / send * 100, 1) if send > 0 else 0
    result["open_rate"] = round(opens / delivery * 100, 1) if delivery > 0 else 0
    result["bounce_rate"] = round(result.get("bounce", 0) / send * 100, 1) if send > 0 else 0

    logger.info(f"[Metrics] 最终结果: send={send}, delivery={delivery}, open={opens}, bounce={result.get('bounce', 0)}")
    logger.info("=" * 60)

    # 将 debug 信息附加到返回结果中，方便前端/API 排查
    result["_debug"] = {
        "region": AWS_REGION,
        "batch_id": batch_id,
        "time_range": f"{start.isoformat()} ~ {now.isoformat()}",
        "available_metrics_in_cloudwatch": available_metrics if 'available_metrics' in dir() else "查询失败",
        "raw_responses": debug_raw,
    }

    return result


def list_sending_jobs(db: Session, user_id: int, page: int = 1, page_size: int = 15) -> dict:
    """查询用户的发送历史"""
    query = db.query(SendingJob).filter(SendingJob.user_id == user_id)
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    rows = query.order_by(SendingJob.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = [SendingJobOut(
        id=r.id, batch_id=r.batch_id, template_name=r.template_name,
        group_name=r.group_name, source_email=r.source_email,
        reply_to=r.reply_to,
        total_contacts=r.total_contacts, sent_count=r.sent_count or 0,
        total_batches=r.total_batches,
        status=r.status, error_message=r.error_message,
        configuration_set=r.configuration_set, created_at=r.created_at,
        finished_at=r.finished_at,
    ) for r in rows]

    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


def get_admin_stats(db: Session) -> dict:
    """管理员：获取所有用户的发送统计"""
    from domain.auth.models import User as UserModel
    from sqlalchemy import func, case

    # 按用户汇总
    user_stats = db.query(
        SendingJob.user_id,
        func.count(SendingJob.id).label("total_jobs"),
        func.sum(SendingJob.total_contacts).label("total_contacts"),
        func.sum(case((SendingJob.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((SendingJob.status == "failed", 1), else_=0)).label("failed_count"),
        func.min(SendingJob.created_at).label("first_send"),
        func.max(SendingJob.created_at).label("last_send"),
    ).group_by(SendingJob.user_id).all()

    # 查用户信息
    user_map = {}
    user_ids = [s.user_id for s in user_stats]
    if user_ids:
        users = db.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
        user_map = {u.id: u for u in users}

    items = []
    for s in user_stats:
        u = user_map.get(s.user_id)
        items.append({
            "user_id": s.user_id,
            "username": u.username if u else "unknown",
            "display_name": u.display_name if u else "unknown",
            "email": u.email if u else "",
            "total_jobs": s.total_jobs,
            "total_contacts": s.total_contacts or 0,
            "success_count": s.success_count or 0,
            "failed_count": s.failed_count or 0,
            "first_send": s.first_send.isoformat() if s.first_send else None,
            "last_send": s.last_send.isoformat() if s.last_send else None,
        })

    # 全局汇总
    total_jobs = sum(i["total_jobs"] for i in items)
    total_contacts = sum(i["total_contacts"] for i in items)
    total_success = sum(i["success_count"] for i in items)

    return {
        "summary": {
            "total_users": len(items),
            "total_jobs": total_jobs,
            "total_contacts": total_contacts,
            "success_rate": round(total_success / total_jobs * 100, 1) if total_jobs > 0 else 0,
        },
        "users": sorted(items, key=lambda x: x["total_contacts"], reverse=True),
    }


def get_admin_all_jobs(db: Session, page: int = 1, page_size: int = 15) -> dict:
    """管理员：查看所有用户的发送历史"""
    from domain.auth.models import User as UserModel

    query = db.query(SendingJob)
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    rows = query.order_by(SendingJob.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 查用户信息
    user_ids = list(set(r.user_id for r in rows))
    user_map = {}
    if user_ids:
        users = db.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
        user_map = {u.id: u for u in users}

    items = []
    for r in rows:
        u = user_map.get(r.user_id)
        items.append({
            "id": r.id,
            "batch_id": r.batch_id,
            "username": u.username if u else "unknown",
            "display_name": u.display_name if u else "unknown",
            "template_name": r.template_name,
            "group_name": r.group_name,
            "source_email": r.source_email,
            "total_contacts": r.total_contacts,
            "status": r.status,
            "configuration_set": r.configuration_set,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


# ========================
# SNS Webhook: 处理 SES 事件
# ========================

def process_ses_event(event_data: dict, db: Session):
    """处理来自 SNS 的 SES 事件通知"""
    import logging
    logger = logging.getLogger("ses-sender.webhook")

    event_type = event_data.get("eventType") or event_data.get("notificationType")
    mail = event_data.get("mail", {})
    message_id = mail.get("messageId")

    if not message_id or not event_type:
        logger.warning(f"[Webhook] 忽略无效事件: eventType={event_type}, messageId={message_id}")
        return

    # 查找对应的邮件明细
    detail = db.query(SendingJobDetail).filter(SendingJobDetail.message_id == message_id).first()
    if not detail:
        logger.debug(f"[Webhook] 未找到 message_id={message_id} 的记录，跳过")
        return

    # 收到 SES 事件说明邮件已发出，修正可能卡住的 send_status
    if detail.send_status == "Pending":
        detail.send_status = "Success"

    from datetime import datetime

    event_type_upper = event_type.upper()

    if event_type_upper == "DELIVERY":
        delivery_info = event_data.get("delivery", {})
        detail.delivery_status = "Delivery"
        ts = delivery_info.get("timestamp")
        if ts:
            try:
                detail.delivery_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                detail.delivery_time = datetime.utcnow()
        else:
            detail.delivery_time = datetime.utcnow()
        logger.info(f"[Webhook] Delivery: {detail.recipient} (msg={message_id[:16]}...)")

    elif event_type_upper == "BOUNCE":
        bounce_info = event_data.get("bounce", {})
        detail.delivery_status = "Bounce"
        detail.bounce_type = bounce_info.get("bounceType")
        detail.bounce_subtype = bounce_info.get("bounceSubType")
        recipients = bounce_info.get("bouncedRecipients", [])
        if recipients:
            detail.bounce_message = recipients[0].get("diagnosticCode", "")
        ts = bounce_info.get("timestamp")
        if ts:
            try:
                detail.delivery_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                detail.delivery_time = datetime.utcnow()
        logger.info(f"[Webhook] Bounce: {detail.recipient} type={detail.bounce_type}/{detail.bounce_subtype}")

    elif event_type_upper == "COMPLAINT":
        complaint_info = event_data.get("complaint", {})
        ts = complaint_info.get("timestamp")
        try:
            detail.complaint_time = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.utcnow()
        except Exception:
            detail.complaint_time = datetime.utcnow()
        logger.info(f"[Webhook] Complaint: {detail.recipient}")

    elif event_type_upper == "OPEN":
        detail.open_count = (detail.open_count or 0) + 1
        if not detail.first_open_time:
            open_info = event_data.get("open", {})
            ts = open_info.get("timestamp")
            try:
                detail.first_open_time = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.utcnow()
            except Exception:
                detail.first_open_time = datetime.utcnow()
        logger.info(f"[Webhook] Open: {detail.recipient} (count={detail.open_count})")

    elif event_type_upper == "CLICK":
        detail.click_count = (detail.click_count or 0) + 1
        if not detail.first_click_time:
            click_info = event_data.get("click", {})
            ts = click_info.get("timestamp")
            try:
                detail.first_click_time = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.utcnow()
            except Exception:
                detail.first_click_time = datetime.utcnow()
        logger.info(f"[Webhook] Click: {detail.recipient} (count={detail.click_count})")

    elif event_type_upper == "REJECT":
        detail.delivery_status = "Reject"
        logger.info(f"[Webhook] Reject: {detail.recipient}")

    elif event_type_upper == "SEND":
        if not detail.delivery_status:
            detail.delivery_status = "Sent"
        logger.debug(f"[Webhook] Send confirmed: {detail.recipient}")

    db.commit()


# ========================
# 查询批次邮件明细
# ========================

def get_batch_details(db: Session, batch_id: str) -> list:
    """获取指定批次的每封邮件明细"""
    details = db.query(SendingJobDetail).filter(
        SendingJobDetail.batch_id == batch_id
    ).order_by(SendingJobDetail.id.asc()).all()

    return [SendingJobDetailOut.model_validate(d) for d in details]


def list_email_details(
    db: Session,
    user_id: int,
    is_admin: bool,
    page: int = 1,
    page_size: int = 20,
    recipient: str = "",
    batch_id: str = "",
    send_status: str = "",
    delivery_status: str = "",
) -> dict:
    """全局邮件明细查询（支持搜索、筛选、分页）"""
    query = db.query(SendingJobDetail)

    # 非管理员只能看自己的
    if not is_admin:
        user_batch_ids = [
            r[0] for r in db.query(SendingJob.batch_id).filter(SendingJob.user_id == user_id).all()
        ]
        query = query.filter(SendingJobDetail.batch_id.in_(user_batch_ids))

    # 搜索条件
    if recipient:
        query = query.filter(SendingJobDetail.recipient.contains(recipient))
    if batch_id:
        query = query.filter(SendingJobDetail.batch_id.contains(batch_id))
    if send_status:
        query = query.filter(SendingJobDetail.send_status == send_status)
    if delivery_status:
        query = query.filter(SendingJobDetail.delivery_status == delivery_status)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total else 1
    items = query.order_by(SendingJobDetail.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 补充 batch 的模版名和客群名
    batch_ids_in_page = list(set(d.batch_id for d in items))
    batch_info = {}
    if batch_ids_in_page:
        jobs = db.query(SendingJob).filter(SendingJob.batch_id.in_(batch_ids_in_page)).all()
        for j in jobs:
            batch_info[j.batch_id] = {"template_name": j.template_name, "group_name": j.group_name, "source_email": j.source_email}

    result_items = []
    for d in items:
        item = SendingJobDetailOut.model_validate(d).model_dump()
        info = batch_info.get(d.batch_id, {})
        item["template_name"] = info.get("template_name", "")
        item["group_name"] = info.get("group_name", "")
        item["source_email"] = info.get("source_email", "")
        result_items.append(item)

    return {
        "items": result_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def export_email_details(
    db: Session, user_id: int, is_admin: bool,
    recipient: str = "", batch_id: str = "", send_status: str = "", delivery_status: str = "",
):
    """导出邮件明细为 Excel"""
    import io
    from openpyxl import Workbook

    query = db.query(SendingJobDetail)
    if not is_admin:
        user_batch_ids = [r[0] for r in db.query(SendingJob.batch_id).filter(SendingJob.user_id == user_id).all()]
        query = query.filter(SendingJobDetail.batch_id.in_(user_batch_ids))
    if recipient:
        query = query.filter(SendingJobDetail.recipient.contains(recipient))
    if batch_id:
        query = query.filter(SendingJobDetail.batch_id.contains(batch_id))
    if send_status:
        query = query.filter(SendingJobDetail.send_status == send_status)
    if delivery_status:
        query = query.filter(SendingJobDetail.delivery_status == delivery_status)

    items = query.order_by(SendingJobDetail.id.desc()).limit(10000).all()

    batch_ids_all = list(set(d.batch_id for d in items))
    batch_info = {}
    if batch_ids_all:
        jobs = db.query(SendingJob).filter(SendingJob.batch_id.in_(batch_ids_all)).all()
        for j in jobs:
            batch_info[j.batch_id] = {"template_name": j.template_name, "group_name": j.group_name, "source_email": j.source_email}

    wb = Workbook()
    ws = wb.active
    ws.title = "邮件明细"
    headers = ["收件人", "批次ID", "模版", "客群", "发送邮箱", "发送状态", "送达状态", "退信类型", "打开次数", "点击次数", "送达时间", "首次打开", "首次点击", "投诉时间"]
    ws.append(headers)

    for d in items:
        info = batch_info.get(d.batch_id, {})
        ws.append([
            d.recipient,
            d.batch_id,
            info.get("template_name", ""),
            info.get("group_name", ""),
            info.get("source_email", ""),
            d.send_status,
            d.delivery_status or "",
            d.bounce_type or "",
            d.open_count or 0,
            d.click_count or 0,
            d.delivery_time.strftime("%Y-%m-%d %H:%M:%S") if d.delivery_time else "",
            d.first_open_time.strftime("%Y-%m-%d %H:%M:%S") if d.first_open_time else "",
            d.first_click_time.strftime("%Y-%m-%d %H:%M:%S") if d.first_click_time else "",
            d.complaint_time.strftime("%Y-%m-%d %H:%M:%S") if d.complaint_time else "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ==================== 定时发送 ====================

def _calc_next_run(schedule_type: str, scheduled_time, cron_hour: int, cron_minute: int,
                   day_of_week=None, day_of_month=None, after=None):
    """计算下次执行时间"""
    from datetime import datetime, timedelta
    now = after or datetime.utcnow()

    if schedule_type == "once":
        return scheduled_time if scheduled_time > now else None

    base = now.replace(hour=cron_hour, minute=cron_minute, second=0, microsecond=0)

    if schedule_type == "daily":
        nxt = base if base > now else base + timedelta(days=1)
        return nxt

    if schedule_type == "weekly":
        dow = day_of_week if day_of_week is not None else 0
        diff = (dow - now.weekday()) % 7
        nxt = base + timedelta(days=diff)
        if nxt <= now:
            nxt += timedelta(days=7)
        return nxt

    if schedule_type == "monthly":
        dom = day_of_month if day_of_month else 1
        import calendar
        try:
            nxt = base.replace(day=min(dom, calendar.monthrange(now.year, now.month)[1]))
        except ValueError:
            nxt = base.replace(day=28)
        if nxt <= now:
            m = now.month + 1
            y = now.year
            if m > 12:
                m, y = 1, y + 1
            try:
                nxt = nxt.replace(year=y, month=m, day=min(dom, calendar.monthrange(y, m)[1]))
            except ValueError:
                nxt = nxt.replace(year=y, month=m, day=28)
        return nxt

    return None


def create_scheduled_job(db: Session, user_id: int, data) -> "ScheduledJob":
    from datetime import datetime
    from domain.sending.models import ScheduledJob
    from domain.template.models import EmailTemplate
    from domain.audience.models import ContactGroup

    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == data.template_id, EmailTemplate.user_id == user_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模版不存在")
    group = db.query(ContactGroup).filter(ContactGroup.id == data.group_id, ContactGroup.user_id == user_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="客群不存在")

    try:
        sched_time = datetime.fromisoformat(data.scheduled_time.replace("Z", "+00:00").replace("+00:00", ""))
    except Exception:
        raise HTTPException(status_code=400, detail="时间格式无效")

    next_run = _calc_next_run(data.schedule_type, sched_time, data.cron_hour, data.cron_minute,
                              data.day_of_week, data.day_of_month)
    if not next_run:
        raise HTTPException(status_code=400, detail="计算下次执行时间失败，请检查时间设置")

    job = ScheduledJob(
        user_id=user_id,
        template_id=data.template_id,
        group_id=data.group_id,
        template_name=tpl.name,
        group_name=group.name,
        schedule_type=data.schedule_type,
        scheduled_time=sched_time,
        cron_hour=data.cron_hour,
        cron_minute=data.cron_minute,
        day_of_week=data.day_of_week,
        day_of_month=data.day_of_month,
        status="active",
        next_run_at=next_run,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_scheduled_job(db: Session, job_id: int, user_id: int, data) -> "ScheduledJob":
    from datetime import datetime
    from domain.sending.models import ScheduledJob

    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id, ScheduledJob.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    if data.status is not None:
        job.status = data.status
    if data.schedule_type is not None:
        job.schedule_type = data.schedule_type
    if data.scheduled_time is not None:
        try:
            job.scheduled_time = datetime.fromisoformat(data.scheduled_time.replace("Z", "+00:00").replace("+00:00", ""))
        except Exception:
            raise HTTPException(status_code=400, detail="时间格式无效")
    if data.cron_hour is not None:
        job.cron_hour = data.cron_hour
    if data.cron_minute is not None:
        job.cron_minute = data.cron_minute
    if data.day_of_week is not None:
        job.day_of_week = data.day_of_week
    if data.day_of_month is not None:
        job.day_of_month = data.day_of_month

    if job.status == "active":
        job.next_run_at = _calc_next_run(
            job.schedule_type, job.scheduled_time, job.cron_hour, job.cron_minute,
            job.day_of_week, job.day_of_month,
        )

    db.commit()
    db.refresh(job)
    return job


def delete_scheduled_job(db: Session, job_id: int, user_id: int):
    from domain.sending.models import ScheduledJob
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id, ScheduledJob.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.delete(job)
    db.commit()
    return {"message": "已删除"}


def list_scheduled_jobs(db: Session, user_id: int) -> list:
    from domain.sending.models import ScheduledJob
    rows = db.query(ScheduledJob).filter(ScheduledJob.user_id == user_id).order_by(ScheduledJob.id.desc()).all()
    return rows


def execute_scheduled_job(job_id: int):
    """由调度器调用：执行一个到期的定时任务"""
    import logging
    from datetime import datetime
    from core.database import SessionLocal
    from domain.sending.models import ScheduledJob
    from domain.auth.models import User

    logger = logging.getLogger("ses-sender.scheduler")
    db = SessionLocal()
    try:
        job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
        if not job or job.status != "active":
            return

        user = db.query(User).filter(User.id == job.user_id).first()
        if not user or not user.email:
            job.error_message = "用户不存在或未配置发送邮箱"
            db.commit()
            return

        logger.info(f"[Scheduler] 执行定时任务 #{job.id} type={job.schedule_type} user={user.username}")

        try:
            result = send_bulk_email(
                db=db,
                source_email=user.email,
                template_id=job.template_id,
                group_id=job.group_id,
                user_id=job.user_id,
            )
            job.last_batch_id = result.get("batch_id")
            job.error_message = None
        except HTTPException as e:
            job.error_message = e.detail
            logger.warning(f"[Scheduler] 任务 #{job.id} 发送失败: {e.detail}")
        except Exception as e:
            job.error_message = str(e)
            logger.error(f"[Scheduler] 任务 #{job.id} 异常: {e}")

        job.last_run_at = datetime.utcnow()
        job.run_count = (job.run_count or 0) + 1

        if job.schedule_type == "once":
            job.status = "completed"
            job.next_run_at = None
        else:
            job.next_run_at = _calc_next_run(
                job.schedule_type, job.scheduled_time, job.cron_hour, job.cron_minute,
                job.day_of_week, job.day_of_month, after=datetime.utcnow(),
            )

        db.commit()
    except Exception as e:
        logger.error(f"[Scheduler] execute_scheduled_job 异常: {e}")
    finally:
        db.close()
