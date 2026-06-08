from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from core.database import get_db
from core.deps import get_current_user, require_admin
from domain.auth.models import User
from domain.template.schemas import TemplateCreate, TemplateUpdate, TemplateOut, OptimizeRequest, EvaluateRequest, DimensionFixRequest
from domain.template import service

router = APIRouter(tags=["邮件模版管理"])


# ========== AI 优化 ==========
@router.post("/ai/optimize-template")
def optimize_template(req: OptimizeRequest, current_user: User = Depends(get_current_user)):
    """调用 Bedrock AI 优化邮件模板"""
    return service.optimize_template_with_ai(req.subject, req.html_body, req.user_feedback, req.images, req.model_id)


@router.post("/ai/evaluate-template")
def evaluate_template(req: EvaluateRequest, current_user: User = Depends(get_current_user)):
    """AI 评测邮件模板"""
    return service.evaluate_template_with_ai(req.subject, req.html_body, req.model_ids)


@router.post("/ai/dimension-fix")
def dimension_fix(req: DimensionFixRequest, current_user: User = Depends(get_current_user)):
    """获取单个维度的 AI 修复建议"""
    return service.get_dimension_fix(req.subject, req.html_body, req.dimension, req.issues, req.model_id)


# ========== 通用：按用户隔离的模版管理 ==========
@router.get("/user/templates", response_model=List[TemplateOut])
def list_templates(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_templates(db, current_user.id)


@router.post("/user/templates")
def create_template(data: TemplateCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.create_template(db, data, current_user.id)


@router.put("/user/templates/{template_id}")
def update_template(template_id: int, data: TemplateUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.update_template(db, template_id, data, current_user.id)


@router.delete("/user/templates/{template_id}")
def delete_template(template_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.delete_template(db, template_id, current_user.id)


# ========== 管理员：可以查看所有用户的模版（保留兼容） ==========
@router.get("/admin/templates", response_model=List[TemplateOut])
def admin_list_templates(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return service.list_templates(db, admin.id)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/templates")
def admin_create_template(data: TemplateCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_template(db, data, admin.id)


@router.put("/admin/templates/{template_id}")
def admin_update_template(template_id: int, data: TemplateUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.update_template(db, template_id, data, admin.id)


@router.delete("/admin/templates/{template_id}")
def admin_delete_template(template_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.delete_template(db, template_id, admin.id)


# ========== 模板附件管理 ==========
import os
import uuid as _uuid
import mimetypes

ATTACHMENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "attachments")
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ATTACHMENTS_PER_TEMPLATE = 5


def _get_user_template(db: Session, template_id: int, user_id: int):
    from domain.template.models import EmailTemplate
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id, EmailTemplate.user_id == user_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模版不存在")
    return tpl


@router.get("/user/templates/{template_id}/attachments")
def list_attachments(template_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_user_template(db, template_id, current_user.id)
    from domain.template.models import TemplateAttachment
    rows = db.query(TemplateAttachment).filter(TemplateAttachment.template_id == template_id).order_by(TemplateAttachment.id).all()
    return [{"id": r.id, "file_name": r.file_name, "content_type": r.content_type, "file_size": r.file_size, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.post("/user/templates/{template_id}/attachments")
async def upload_attachment(template_id: int, file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_user_template(db, template_id, current_user.id)
    from domain.template.models import TemplateAttachment

    existing_count = db.query(TemplateAttachment).filter(TemplateAttachment.template_id == template_id).count()
    if existing_count >= MAX_ATTACHMENTS_PER_TEMPLATE:
        raise HTTPException(status_code=400, detail=f"每个模板最多 {MAX_ATTACHMENTS_PER_TEMPLATE} 个附件")

    contents = await file.read()
    if len(contents) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail=f"附件大小不能超过 10MB，当前 {len(contents)/1024/1024:.1f}MB")

    tpl_dir = os.path.join(ATTACHMENT_DIR, str(template_id))
    os.makedirs(tpl_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "file")[1]
    stored_name = f"{_uuid.uuid4().hex[:12]}{ext}"
    file_path = os.path.join(tpl_dir, stored_name)

    with open(file_path, "wb") as fp:
        fp.write(contents)

    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

    att = TemplateAttachment(
        template_id=template_id,
        file_name=file.filename or "attachment",
        file_path=file_path,
        content_type=content_type,
        file_size=len(contents),
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    return {"id": att.id, "file_name": att.file_name, "content_type": att.content_type, "file_size": att.file_size}


@router.delete("/user/templates/{template_id}/attachments/{att_id}")
def delete_attachment(template_id: int, att_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_user_template(db, template_id, current_user.id)
    from domain.template.models import TemplateAttachment

    att = db.query(TemplateAttachment).filter(TemplateAttachment.id == att_id, TemplateAttachment.template_id == template_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="附件不存在")

    if att.file_path and os.path.exists(att.file_path):
        os.remove(att.file_path)

    db.delete(att)
    db.commit()
    return {"message": "附件已删除"}
