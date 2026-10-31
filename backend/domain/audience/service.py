import io
import json
import math
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from typing import List
from sqlalchemy import func, case, insert, literal, select
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
import openpyxl

from domain.audience.models import ContactGroup, Contact, ContactSelection, ContactSelectionItem
from domain.audience.status import ContactStatusQuery
from domain.audience.schemas import GroupCreate, GroupUpdate, ContactCreate, GroupOut, PaginatedResponse, ContactListResponse


# ========== 客群操作 ==========
def list_groups(db: Session, user_id: int, search: str = "", page: int = 1, page_size: int = 20) -> PaginatedResponse:
    query = db.query(ContactGroup).filter(ContactGroup.user_id == user_id)
    if search:
        query = query.filter(ContactGroup.name.ilike(f"%{search}%"))

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    groups = query.order_by(ContactGroup.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for g in groups:
        count = db.query(func.count(Contact.id)).filter(Contact.group_id == g.id).scalar()
        items.append(GroupOut(
            id=g.id, name=g.name, description=g.description,
            user_id=g.user_id, contact_count=count
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


def create_group(db: Session, data: GroupCreate, user_id: int) -> ContactGroup:
    group = ContactGroup(name=data.name, description=data.description, user_id=user_id)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def update_group(db: Session, group_id: int, data: GroupUpdate, user_id: int) -> ContactGroup:
    group = _get_user_group(db, group_id, user_id)
    if data.name is not None:
        group.name = data.name
    if data.description is not None:
        group.description = data.description
    db.commit()
    db.refresh(group)
    return group


def delete_group(db: Session, group_id: int, user_id: int) -> dict:
    group = _get_user_group(db, group_id, user_id)
    db.delete(group)
    db.commit()
    return {"message": "客群已删除"}


# ========== 联系人操作 ==========
def list_contacts(db: Session, group_id: int, user_id: int, search: str = "", page: int = 1,
                  page_size: int = 20, flags=None) -> ContactListResponse:
    group = _get_user_group(db, group_id, user_id)
    statuses = ContactStatusQuery(db, user_id, group.owner.email)
    query = statuses.filter_query(db.query(Contact).filter(Contact.group_id == group_id), search, flags)
    total = query.count()
    rows = query.add_columns(*statuses.columns()).order_by(Contact.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [{"id": row[0].id, "email": row[0].email, "name": row[0].name, "attributes": row[0].attributes,
              "group_id": row[0].group_id, **statuses.status_dict(row)} for row in rows]
    return ContactListResponse(items=items, total=total, page=page, page_size=page_size,
                               total_pages=max(1, math.ceil(total / page_size)), suppression_sync=statuses.sync_info)


def validate_group(db: Session, group_id: int, user_id: int) -> dict:
    group = _get_user_group(db, group_id, user_id)
    statuses = ContactStatusQuery(db, user_id, group.owner.email)
    # Aggregate the entire group in SQL; never load all contacts into a web worker.
    row = db.query(func.count(Contact.id), *[
        func.coalesce(func.sum(case((predicate, 1), else_=0)), 0).label(flag)
        for flag, predicate in statuses.predicates.items()
    ]).filter(Contact.group_id == group_id).one()
    return {"total": row[0], "checked_at": datetime.now(timezone.utc).isoformat(),
            "counts": {flag: int(getattr(row, flag)) for flag in statuses.predicates},
            "suppression_sync": statuses.sync_info}


def create_contact_selection(db: Session, group_id: int, user_id: int, search: str = "", flags=None) -> dict:
    group = _get_user_group(db, group_id, user_id, for_update=True)
    statuses = ContactStatusQuery(db, user_id, group.owner.email)
    query = statuses.filter_query(db.query(Contact.id).filter(Contact.group_id == group_id), search, flags)
    now = datetime.utcnow()
    # Keep one active snapshot per owner/group and remove the owner's expired
    # snapshots. Item IDs are indexed by selection_id, so cleanup stays bounded.
    obsolete_condition = ((ContactSelection.expires_at <= now) |
                          (ContactSelection.group_id == group_id))
    obsolete = select(ContactSelection.id).where(
        ContactSelection.user_id == user_id, obsolete_condition,
    )
    db.query(ContactSelectionItem).filter(
        ContactSelectionItem.selection_id.in_(obsolete)
    ).delete(synchronize_session=False)
    db.query(ContactSelection).filter(
        ContactSelection.user_id == user_id, obsolete_condition,
    ).delete(synchronize_session=False)
    selection = ContactSelection(id=str(uuid4()), user_id=user_id, group_id=group_id,
                                 created_at=now, expires_at=now + timedelta(minutes=15))
    db.add(selection)
    db.flush()
    # INSERT ... SELECT freezes exact IDs atomically without a giant Python list.
    db.execute(insert(ContactSelectionItem).from_select(
        [ContactSelectionItem.selection_id, ContactSelectionItem.contact_id],
        query.with_entities(literal(selection.id), Contact.id).statement,
    ))
    selected_count = db.query(ContactSelectionItem).filter_by(selection_id=selection.id).count()
    if not selected_count:
        db.rollback()
        raise HTTPException(status_code=400, detail="没有符合条件的联系人")
    result = {"selection_id": selection.id, "selected_count": selected_count,
              "expires_at": selection.expires_at.replace(tzinfo=timezone.utc).isoformat()}
    db.commit()
    return result


def bulk_delete_contacts(db: Session, group_id: int, user_id: int, *, contact_ids=None, selection_id=None) -> dict:
    _get_user_group(db, group_id, user_id)
    if (contact_ids is None) == (selection_id is None):
        raise HTTPException(status_code=400, detail="请选择联系人或筛选结果，不能同时指定")
    query = db.query(Contact).filter(Contact.group_id == group_id)
    if contact_ids is not None:
        if not contact_ids or len(contact_ids) > 1000 or any(type(value) is not int or value <= 0 for value in contact_ids):
            raise HTTPException(status_code=400, detail="请选择 1 到 1000 个有效联系人")
        ids = set(contact_ids)
        existing = query.with_entities(Contact.id).filter(Contact.id.in_(ids)).with_for_update().all()
        if {row.id for row in existing} != ids:
            raise HTTPException(status_code=404, detail="部分联系人不存在或不属于当前客群，请刷新后重试")
        query = query.filter(Contact.id.in_(ids))
        selection = None
    else:
        if not isinstance(selection_id, str) or not selection_id or len(selection_id) > 36:
            raise HTTPException(status_code=400, detail="无效的选择记录")
        # A row lock serializes concurrent consumes of the same snapshot.
        selection = db.query(ContactSelection).filter_by(id=selection_id, group_id=group_id, user_id=user_id).with_for_update().first()
        if not selection:
            raise HTTPException(status_code=404, detail="选择记录不存在或已使用，请重新选择")
        if selection.expires_at <= datetime.utcnow():
            raise HTTPException(status_code=410, detail="选择已过期，请重新选择联系人")
        selected_ids = select(ContactSelectionItem.contact_id).where(ContactSelectionItem.selection_id == selection.id)
        query = query.filter(Contact.id.in_(selected_ids))
    deleted_count = query.delete(synchronize_session=False)
    if selection is not None:
        db.query(ContactSelectionItem).filter_by(selection_id=selection.id).delete(synchronize_session=False)
        db.delete(selection)
    db.commit()
    # The bulk operation bypasses the ORM; don't leave already-loaded contacts stale.
    db.expire_all()
    return {"deleted_count": deleted_count}


def create_contact(db: Session, data: ContactCreate, user_id: int) -> Contact:
    _get_user_group(db, data.group_id, user_id)
    contact = Contact(email=data.email, name=data.name, attributes=data.attributes, group_id=data.group_id)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, contact_id: int, user_id: int) -> dict:
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    _get_user_group(db, contact.group_id, user_id)
    db.delete(contact)
    db.commit()
    return {"message": "联系人已删除"}


# ========== Excel 操作 ==========
def download_contacts_excel(db: Session, group_id: int, user_id: int) -> StreamingResponse:
    group = _get_user_group(db, group_id, user_id)
    contacts = db.query(Contact).filter(Contact.group_id == group_id).all()

    # Collect all attribute keys across contacts
    all_attr_keys = []
    for c in contacts:
        if c.attributes:
            try:
                attrs = json.loads(c.attributes)
                for k in attrs:
                    if k not in all_attr_keys:
                        all_attr_keys.append(k)
            except (json.JSONDecodeError, TypeError):
                pass

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "联系人"
    ws.append(["姓名", "邮箱"] + all_attr_keys)
    for c in contacts:
        attrs = {}
        if c.attributes:
            try:
                attrs = json.loads(c.attributes)
            except (json.JSONDecodeError, TypeError):
                pass
        row = [c.name or "", c.email] + [str(attrs.get(k, "")) for k in all_attr_keys]
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={group.name}_contacts.xlsx"},
    )


def download_template_excel() -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "联系人模版"
    ws.append(["姓名", "邮箱", "company", "city"])
    ws.append(["张三", "zhangsan@example.com", "Acme Inc", "Shanghai"])
    ws.append(["李四", "lisi@example.com", "Tech Corp", "Beijing"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contact_template.xlsx"},
    )


def upload_contacts_excel(db: Session, group_id: int, user_id: int, file: UploadFile) -> dict:
    _get_user_group(db, group_id, user_id)

    try:
        wb = openpyxl.load_workbook(file.file)
        ws = wb.active

        # Read header row to get attribute column names
        headers = [str(cell.value or "").strip() for cell in ws[1]]
        attr_keys = headers[2:]  # columns after 姓名, 邮箱

        # Deduplicate both against existing group contacts and within this file.
        # Email matching is case-insensitive while preserving the imported value.
        seen_emails = {
            email.casefold()
            for (email,) in db.query(Contact.email).filter(Contact.group_id == group_id).all()
            if email
        }
        contact_rows = []
        duplicate_count = 0
        empty_count = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            name = str(row[0] or "").strip() if row[0] else ""
            email = str(row[1] or "").strip() if len(row) > 1 and row[1] else ""
            if not email:
                empty_count += 1
                continue
            email_key = email.casefold()
            if email_key in seen_emails:
                duplicate_count += 1
                continue
            seen_emails.add(email_key)

            # Build attributes JSON from extra columns
            attrs = {}
            for i, key in enumerate(attr_keys):
                if key and len(row) > i + 2 and row[i + 2]:
                    attrs[key] = str(row[i + 2]).strip()

            contact_rows.append({
                "name": name,
                "email": email,
                "attributes": json.dumps(attrs, ensure_ascii=False) if attrs else None,
                "group_id": group_id,
            })
        if contact_rows:
            db.bulk_insert_mappings(Contact, contact_rows)
        db.commit()
        imported_count = len(contact_rows)
        return {
            "message": (
                f"成功导入 {imported_count} 个联系人，"
                f"跳过 {duplicate_count} 个重复邮箱和 {empty_count} 个空邮箱"
            ),
            "imported_count": imported_count,
            "duplicate_count": duplicate_count,
            "empty_count": empty_count,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")


# ========== 内部工具 ==========
def _get_user_group(db: Session, group_id: int, user_id: int, *, for_update: bool = False) -> ContactGroup:
    """获取属于指定用户的客群，不存在则抛异常"""
    query = db.query(ContactGroup).filter(
        ContactGroup.id == group_id, ContactGroup.user_id == user_id
    )
    if for_update:
        query = query.with_for_update()
    group = query.first()
    if not group:
        raise HTTPException(status_code=404, detail="客群不存在或无权操作")
    return group
