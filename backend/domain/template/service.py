import uuid
from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException

from core.ses import sesv2_client
from domain.template.models import EmailTemplate
from domain.template.schemas import TemplateCreate, TemplateUpdate, TemplateOut


def _generate_ses_name(user_id: int) -> str:
    """生成唯一的 SES 模版名称"""
    short_id = uuid.uuid4().hex[:8]
    return f"u{user_id}_{short_id}"


def list_templates(db: Session, user_id: int) -> List[TemplateOut]:
    """列出用户的模版"""
    rows = db.query(EmailTemplate).filter(EmailTemplate.user_id == user_id).order_by(EmailTemplate.id.desc()).all()
    return [TemplateOut(id=r.id, name=r.name, subject=r.subject, html_body=r.html_body, created_at=r.created_at) for r in rows]


def create_template(db: Session, data: TemplateCreate, user_id: int) -> dict:
    """创建模版（同时写入 DB 和 SES v2）"""
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="模版名称不能为空")

    ses_name = _generate_ses_name(user_id)
    html = str(data.html_body or "")
    text = html or " "

    try:
        sesv2_client.create_email_template(
            TemplateName=ses_name,
            TemplateContent={
                "Subject": str(data.subject),
                "Html": html,
                "Text": text,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SES 模版创建失败: {str(e)}")

    tpl = EmailTemplate(
        name=data.name,
        ses_name=ses_name,
        subject=data.subject,
        html_body=html,
        text_body=text,
        user_id=user_id,
    )
    db.add(tpl)
    db.commit()
    return {"message": f"模版「{data.name}」创建成功"}


def update_template(db: Session, template_id: int, data: TemplateUpdate, user_id: int) -> dict:
    """更新模版（同时更新 DB 和 SES v2）"""
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id, EmailTemplate.user_id == user_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模版不存在")

    if data.subject is not None:
        tpl.subject = data.subject
    if data.html_body is not None:
        tpl.html_body = data.html_body
        tpl.text_body = data.html_body or " "

    try:
        sesv2_client.update_email_template(
            TemplateName=tpl.ses_name,
            TemplateContent={
                "Subject": tpl.subject,
                "Html": tpl.html_body,
                "Text": tpl.text_body,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SES 模版更新失败: {str(e)}")

    db.commit()
    return {"message": f"模版「{tpl.name}」已更新"}


def delete_template(db: Session, template_id: int, user_id: int) -> dict:
    """删除模版（同时从 DB 和 SES v2 删除）"""
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id, EmailTemplate.user_id == user_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模版不存在")

    try:
        sesv2_client.delete_email_template(TemplateName=tpl.ses_name)
    except Exception:
        pass

    db.delete(tpl)
    db.commit()
    return {"message": f"模版「{tpl.name}」已删除"}


def get_ses_template_name(db: Session, template_id: int, user_id: int) -> str:
    """获取模版对应的 SES 模版名称（用于发送邮件）"""
    tpl = db.query(EmailTemplate).filter(EmailTemplate.id == template_id, EmailTemplate.user_id == user_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模版不存在")
    return tpl.ses_name


def _parse_ai_json(text: str) -> dict:
    """Robustly extract JSON from AI response that may contain markdown fences or malformed output."""
    import json, re, logging

    logger = logging.getLogger("ses-sender.ai")
    text = text.strip()

    for prefix in ("```json", "```"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug(f"[_parse_ai_json] Direct parse failed: {e}")

    keys = ["suggestions", "optimized_subject", "optimized_html"]
    parsed = {}

    suggestions_match = re.search(r'"suggestions"\s*:\s*\[', text)
    if suggestions_match:
        bracket_start = text.index('[', suggestions_match.start())
        depth = 0
        end = bracket_start
        in_str = False
        esc = False
        for i in range(bracket_start, len(text)):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        try:
            parsed["suggestions"] = json.loads(text[bracket_start:end + 1])
        except json.JSONDecodeError:
            parsed["suggestions"] = []

    for key in ["optimized_subject", "optimized_html"]:
        pattern = f'"{key}"\\s*:\\s*"'
        match = re.search(pattern, text)
        if not match:
            continue
        value_start = match.end()
        esc = False
        value_end = value_start
        for i in range(value_start, len(text)):
            ch = text[i]
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                value_end = i
                break
        raw_val = text[value_start:value_end]
        parsed[key] = raw_val.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')

    if parsed.get("optimized_html") or parsed.get("optimized_subject"):
        return {
            "suggestions": parsed.get("suggestions", []),
            "optimized_subject": parsed.get("optimized_subject", ""),
            "optimized_html": parsed.get("optimized_html", ""),
        }

    raise HTTPException(status_code=500, detail="AI 返回格式异常，请重试")


def optimize_template_with_ai(subject: str, html_body: str, user_feedback: str = None, images: list = None, selected_model_id: str = None) -> dict:
    """调用 AI 优化邮件模板（支持多模型选择）"""
    import json
    import logging
    import boto3
    from core.config import BEDROCK_MODEL_ID, BEDROCK_REGION
    from core.database import SessionLocal

    logger = logging.getLogger("ses-sender.ai")

    model_cfg = {}
    try:
        from domain.settings.service import get_ai_model_by_id, get_ai_models, get_bedrock_config
        _db = SessionLocal()
        try:
            if selected_model_id:
                model_cfg = get_ai_model_by_id(_db, selected_model_id)
            else:
                models = get_ai_models(_db)
                model_cfg = models[0] if models else {}
            if not model_cfg:
                db_cfg = get_bedrock_config(_db)
                model_cfg = {"provider": "bedrock", "model_id": db_cfg.get("model_id") or BEDROCK_MODEL_ID,
                             "region": db_cfg.get("region") or BEDROCK_REGION, "auth_mode": db_cfg.get("auth_mode","iam_role"),
                             "access_key": db_cfg.get("access_key"), "secret_key": db_cfg.get("secret_key"),
                             "bedrock_api_key": db_cfg.get("api_key")}
        finally:
            _db.close()
    except Exception:
        pass

    provider = model_cfg.get("type") or model_cfg.get("provider") or "bedrock"
    model_id = model_cfg.get("model_id") or model_cfg.get("model") or BEDROCK_MODEL_ID
    region = model_cfg.get("region") or BEDROCK_REGION

    if not model_id:
        raise HTTPException(status_code=400, detail="未配置 AI 模型，请在系统设置中配置 Bedrock")

    base_instructions = """You are an expert email marketing consultant specializing in AWS SES best practices and email deliverability.

Analyze the following email template and provide optimization suggestions. Focus on:
1. **Deliverability** - Avoid spam trigger words, ensure proper HTML structure
2. **Open Rate** - Optimize subject line to be compelling and concise
3. **Click Rate** - Improve CTA (Call-to-Action) buttons and links
4. **Mobile Responsiveness** - Ensure the email renders well on mobile devices
5. **Compliance** - Check for unsubscribe link, proper sender identification
6. **HTML Quality** - Clean HTML, inline CSS, proper encoding"""

    feedback_section = ""
    if user_feedback and user_feedback.strip():
        feedback_section = f"""

**User's additional modification request:**
{user_feedback}

Please incorporate the user's feedback into your optimization. Prioritize the user's specific requests."""

    prompt = f"""{base_instructions}

Current email:
- Subject: {subject}
- HTML Body:
```html
{html_body}
```
{feedback_section}
Respond in Chinese. Return ONLY valid JSON (no markdown, no code fences) in this exact format:
{{
  "suggestions": ["建议1", "建议2", "建议3"],
  "optimized_subject": "优化后的邮件主题",
  "optimized_html": "优化后的完整HTML内容"
}}

Important:
- Keep all {{{{variable}}}} template variables (like {{{{name}}}}, {{{{email}}}}, {{{{unsubscribe_url}}}}) unchanged
- Keep the original language of the email content
- Make the HTML more professional and mobile-friendly
- Add inline CSS for better email client compatibility
- Your entire response must be a single valid JSON object, nothing else
- Do NOT wrap in markdown code fences
- Make sure all strings in JSON are properly escaped (especially quotes and newlines in HTML)"""

    image_data = _load_images(images, logger) if images else []

    if provider == "openai_compatible":
        openai_cfg = {"api_base": model_cfg.get("api_base",""), "api_key": model_cfg.get("api_key",""), "model": model_id}
        return _invoke_openai_compatible(openai_cfg, prompt, image_data, logger, subject, html_body)

    try:
        api_key = model_cfg.get("bedrock_api_key") or model_cfg.get("api_key")
        auth_mode = model_cfg.get("auth_mode", "iam_role")

        if auth_mode == "api_key" and api_key:
            ai_text = _invoke_bedrock_api_key(model_id, region, api_key, prompt, logger, image_data)
        else:
            client_kwargs = {"region_name": region}
            if auth_mode == "ak_sk":
                ak, sk = model_cfg.get("access_key"), model_cfg.get("secret_key")
                if ak and sk:
                    client_kwargs["aws_access_key_id"] = ak
                    client_kwargs["aws_secret_access_key"] = sk
            client = boto3.client("bedrock-runtime", **client_kwargs)

            content = []
            for img in image_data:
                import base64 as _b64
                content.append({
                    "image": {
                        "format": img["format"],
                        "source": {"bytes": _b64.b64decode(img["data"])},
                    }
                })
            content.append({"text": prompt})

            response = client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": content}],
                inferenceConfig={"maxTokens": 8192, "temperature": 0.3},
            )

            ai_text = ""
            for block in response.get("output", {}).get("message", {}).get("content", []):
                if "text" in block:
                    ai_text += block["text"]
            if not ai_text:
                ai_text = "{}"

        logger.debug(f"[AI Optimize] Raw response length: {len(ai_text)}")
        logger.debug(f"[AI Optimize] Raw response first 500 chars: {ai_text[:500]}")
        logger.debug(f"[AI Optimize] Raw response last 500 chars: {ai_text[-500:]}")

        ai_json = _parse_ai_json(ai_text)

        return {
            "suggestions": ai_json.get("suggestions", []),
            "optimized_subject": ai_json.get("optimized_subject", subject),
            "optimized_html": ai_json.get("optimized_html", html_body),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AI Optimize] Bedrock 调用失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 优化失败: {str(e)}")


def _invoke_openai_compatible(cfg: dict, prompt: str, image_data: list, logger, subject: str, html_body: str) -> dict:
    """通过 OpenAI 兼容 API 调用模型"""
    import json
    import urllib.request
    import urllib.error

    api_base = (cfg.get("api_base") or "").strip()
    if not api_base:
        raise HTTPException(status_code=400, detail="未配置 OpenAI Compatible API Base URL")

    url = api_base.rstrip("/") + "/chat/completions"

    content = []
    for img in (image_data or []):
        content.append({"type": "image_url", "image_url": {"url": f"data:{img['media_type']};base64,{img['data']}"}})
    content.append({"type": "text", "text": prompt})

    messages = [{"role": "user", "content": content if image_data else prompt}]
    payload = json.dumps({
        "model": cfg.get("model") or "gpt-4o",
        "messages": messages,
        "max_tokens": 8192,
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg.get("api_key"):
        req.add_header("Authorization", f"Bearer {cfg['api_key']}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            ai_text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error(f"[AI Optimize] OpenAI API error: HTTP {e.code} {body[:300]}")
        raise HTTPException(status_code=502, detail=f"AI API 调用失败: HTTP {e.code}")

    logger.debug(f"[AI Optimize] OpenAI response length: {len(ai_text)}")
    ai_json = _parse_ai_json(ai_text)

    return {
        "suggestions": ai_json.get("suggestions", []),
        "optimized_subject": ai_json.get("optimized_subject", subject),
        "optimized_html": ai_json.get("optimized_html", html_body),
    }


def _load_images(image_urls: list, logger) -> list:
    """将图片 URL（本地路径或 /uploads/...）加载为 base64"""
    import base64
    import os

    UPLOAD_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
    MIME_MAP = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    FORMAT_MAP = {"image/png": "png", "image/jpeg": "jpeg", "image/gif": "gif", "image/webp": "webp"}
    results = []

    for url in (image_urls or []):
        try:
            if url.startswith("/uploads/"):
                filepath = os.path.join(UPLOAD_BASE, url.replace("/uploads/", ""))
            elif url.startswith("http"):
                import urllib.request
                import tempfile
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".img")
                urllib.request.urlretrieve(url, tmp.name)
                filepath = tmp.name
            else:
                continue

            if not os.path.isfile(filepath):
                logger.warning(f"[AI] Image not found: {filepath}")
                continue

            ext = os.path.splitext(filepath)[1].lower()
            media_type = MIME_MAP.get(ext, "image/png")
            fmt = FORMAT_MAP.get(media_type, "png")

            with open(filepath, "rb") as fp:
                raw = fp.read()
            if len(raw) > 5 * 1024 * 1024:
                logger.warning(f"[AI] Image too large: {len(raw)} bytes, skipping")
                continue

            results.append({
                "data": base64.b64encode(raw).decode(),
                "media_type": media_type,
                "format": fmt,
            })
        except Exception as e:
            logger.warning(f"[AI] Failed to load image {url}: {e}")

    return results


def _invoke_bedrock_api_key(model_id: str, region: str, api_key: str, prompt: str, logger, image_data: list = None) -> str:
    """通过 Bedrock API Key (Bearer Token) + Converse API 调用模型"""
    import json
    import urllib.request
    import urllib.error

    url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{model_id}/converse"

    content = []
    for img in (image_data or []):
        import base64
        content.append({
            "image": {
                "format": img["format"],
                "source": {"bytes": img["data"]},
            }
        })
    content.append({"text": prompt})

    payload = json.dumps({
        "messages": [{"role": "user", "content": content}],
        "inferenceConfig": {"maxTokens": 8192, "temperature": 0.3},
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            text = ""
            for block in data.get("output", {}).get("message", {}).get("content", []):
                if "text" in block:
                    text += block["text"]
            return text or "{}"
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error(f"[AI Optimize] Bedrock API Key 调用失败: HTTP {e.code} {body[:300]}")
        raise HTTPException(status_code=502, detail=f"Bedrock API 调用失败: HTTP {e.code}")


def evaluate_template_with_ai(subject: str, html_body: str, model_ids: list = None) -> dict:
    """AI 评测邮件模板（多模型 × 多维度并发）"""
    import json
    import logging
    import boto3
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from core.config import BEDROCK_MODEL_ID, BEDROCK_REGION
    from core.database import SessionLocal

    logger = logging.getLogger("ses-sender.ai")

    all_models = []
    try:
        from domain.settings.service import get_ai_model_by_id, get_ai_models, get_bedrock_config
        _db = SessionLocal()
        try:
            available = get_ai_models(_db)
            if model_ids:
                for mid in model_ids:
                    cfg = get_ai_model_by_id(_db, mid)
                    if cfg:
                        all_models.append(cfg)
            if not all_models:
                if available:
                    p = available[0]
                    if p.get("models"):
                        m = p["models"][0]
                        cfg = {k: v for k, v in p.items() if k != "models"}
                        cfg.update(m)
                        all_models.append(cfg)
            if not all_models:
                db_cfg = get_bedrock_config(_db)
                all_models.append({"id": "default", "name": "Default", "type": "bedrock",
                                   "model_id": db_cfg.get("model_id") or BEDROCK_MODEL_ID,
                                   "region": db_cfg.get("region") or BEDROCK_REGION,
                                   "auth_mode": db_cfg.get("auth_mode", "iam_role")})
        finally:
            _db.close()
    except Exception:
        pass

    DIMENSIONS = [
        ("送达率", "Spam trigger words, authentication, sender reputation, SPF/DKIM/DMARC"),
        ("主题行质量", "Length 30-50 chars, personalization, urgency, emoji, A/B potential"),
        ("反垃圾邮件合规", "CAN-SPAM, GDPR, unsubscribe link, physical address, sender ID"),
        ("HTML 质量", "Inline CSS, table layout, encoding, no JS, alt tags, DOCTYPE"),
        ("移动端适配", "Responsive, font 14px+, buttons 44px+, single column, media queries"),
        ("ISP 兼容性", "Gmail 102KB clipping, Outlook VML, Yahoo, dark mode"),
        ("内容质量", "Text-image ratio 60:40, CTA clarity, structure, personalization"),
        ("合规性", "Unsubscribe link, List-Unsubscribe hint, privacy policy, opt-out"),
    ]

    email_ctx = f"Subject: {subject}\nHTML:\n{html_body}"

    def eval_one(model_cfg: dict, dim_name: str, criteria: str) -> dict:
        prompt = f"""Evaluate this email on "{dim_name}". Criteria: {criteria}

{email_ctx}

Chinese. ONLY JSON, no markdown: {{"score":85,"issues":["issue"],"suggestions":["suggestion"]}}
Score 0-100. Be strict."""
        try:
            ai_text = _call_ai_model(model_cfg, prompt, logger)
            try:
                r = json.loads(ai_text.strip().strip("`").strip())
            except json.JSONDecodeError:
                import re
                sm = re.search(r'"score"\s*:\s*(\d+)', ai_text)
                score = int(sm.group(1)) if sm else 50
                items = re.findall(r'"([^"]{5,80})"', ai_text)
                items = [i for i in items if i not in ("score","issues","suggestions") and not i.isdigit()][:5]
                r = {"score": score, "issues": items[:3], "suggestions": items[3:]}
            return {"model_id": model_cfg.get("id",""), "dim": dim_name,
                    "score": min(100, max(0, r.get("score", 50))),
                    "issues": r.get("issues", [])[:5], "suggestions": r.get("suggestions", [])[:5]}
        except Exception as e:
            logger.warning(f"[Eval] {model_cfg.get('name','')} / {dim_name}: {e}")
            return {"model_id": model_cfg.get("id",""), "dim": dim_name, "score": 0,
                    "issues": [f"评测失败"], "suggestions": []}

    tasks = []
    with ThreadPoolExecutor(max_workers=min(8, len(all_models) * len(DIMENSIONS))) as executor:
        for mcfg in all_models:
            for dname, dcriteria in DIMENSIONS:
                tasks.append(executor.submit(eval_one, mcfg, dname, dcriteria))
        results_raw = [t.result() for t in tasks]

    dim_order = [d[0] for d in DIMENSIONS]
    model_results = []
    for mcfg in all_models:
        mid = mcfg.get("id", "")
        dims = [r for r in results_raw if r["model_id"] == mid]
        dims.sort(key=lambda x: dim_order.index(x["dim"]) if x["dim"] in dim_order else 99)
        dimensions = [{"name": d["dim"], "score": d["score"], "max": 100, "issues": d["issues"], "suggestions": d["suggestions"]} for d in dims]
        scores = [d["score"] for d in dims if d["score"] > 0]
        overall = round(sum(scores) / len(scores)) if scores else 0
        model_results.append({
            "model_id": mid,
            "model_name": mcfg.get("name", mid),
            "overall_score": overall,
            "dimensions": dimensions,
        })

    return {"models": model_results}


def _call_ai_model(model_cfg: dict, prompt: str, logger) -> str:
    """统一的 AI 模型调用（供评测等功能复用）"""
    import json
    import boto3
    from core.config import BEDROCK_MODEL_ID, BEDROCK_REGION

    provider = model_cfg.get("type") or model_cfg.get("provider") or "bedrock"
    model_id = model_cfg.get("model_id") or model_cfg.get("model") or BEDROCK_MODEL_ID
    region = model_cfg.get("region") or BEDROCK_REGION

    if provider == "openai_compatible":
        import urllib.request
        api_base = (model_cfg.get("api_base") or "").strip()
        url = api_base.rstrip("/") + "/chat/completions"
        payload = json.dumps({"model": model_id, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024, "temperature": 0.2}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if model_cfg.get("api_key"):
            req.add_header("Authorization", f"Bearer {model_cfg['api_key']}")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    else:
        client_kwargs = {"region_name": region}
        auth_mode = model_cfg.get("auth_mode", "iam_role")
        if auth_mode == "ak_sk":
            ak, sk = model_cfg.get("access_key"), model_cfg.get("secret_key")
            if ak and sk:
                client_kwargs["aws_access_key_id"] = ak
                client_kwargs["aws_secret_access_key"] = sk
        api_key = model_cfg.get("bedrock_api_key") or model_cfg.get("api_key")
        if auth_mode == "api_key" and api_key:
            return _invoke_bedrock_api_key(model_id, region, api_key, prompt, logger)
        client = boto3.client("bedrock-runtime", **client_kwargs)
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
        )
        text = ""
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                text += block["text"]
        return text or "{}"


def get_dimension_fix(subject: str, html_body: str, dimension: str, issues: list, selected_model_id: str = None) -> dict:
    """获取单个维度的 AI 修复建议和代码示例"""
    import json
    import logging
    from core.config import BEDROCK_MODEL_ID, BEDROCK_REGION
    from core.database import SessionLocal

    logger = logging.getLogger("ses-sender.ai")

    model_cfg = {}
    try:
        from domain.settings.service import get_ai_model_by_id, get_ai_models, get_bedrock_config
        _db = SessionLocal()
        try:
            if selected_model_id:
                model_cfg = get_ai_model_by_id(_db, selected_model_id)
            else:
                models = get_ai_models(_db)
                model_cfg = models[0] if models else {}
            if not model_cfg:
                db_cfg = get_bedrock_config(_db)
                model_cfg = {"type": "bedrock", "model_id": db_cfg.get("model_id") or BEDROCK_MODEL_ID,
                             "region": db_cfg.get("region") or BEDROCK_REGION, "auth_mode": db_cfg.get("auth_mode", "iam_role")}
        finally:
            _db.close()
    except Exception:
        pass

    issues_text = "\n".join(f"- {i}" for i in issues) if issues else "(无具体问题)"

    prompt = f"""Fix the "{dimension}" issues in this email.

Issues:
{issues_text}

Subject: {subject}
HTML (first 5000 chars):
{html_body[:5000]}

Respond in Chinese. Return ONLY valid JSON, no markdown:
{{"fixes":[{{"issue":"问题","fix":"修复方法","code":"代码片段"}}],"key_changes":"总结"}}

Keep {{{{variable}}}} unchanged. Provide concrete code fixes."""

    try:
        ai_text = _call_ai_model(model_cfg, prompt, logger)
        try:
            return json.loads(ai_text.strip().strip("`").strip())
        except json.JSONDecodeError:
            import re
            fixes = []
            fix_pattern = re.findall(r'"issue"\s*:\s*"([^"]*)".*?"fix"\s*:\s*"([^"]*)"', ai_text, re.DOTALL)
            for issue, fix in fix_pattern[:5]:
                fixes.append({"issue": issue, "fix": fix, "code": ""})
            code_blocks = re.findall(r'"code"\s*:\s*"([^"]{10,})"', ai_text)
            for i, code in enumerate(code_blocks):
                if i < len(fixes):
                    fixes[i]["code"] = code.replace("\\n", "\n").replace('\\"', '"')
            key_changes = ""
            kc_match = re.search(r'"key_changes"\s*:\s*"([^"]*)"', ai_text)
            if kc_match:
                key_changes = kc_match.group(1)
            return {"fixes": fixes or [{"issue": "AI 返回格式异常", "fix": ai_text[:200], "code": ""}], "key_changes": key_changes}
    except Exception as e:
        logger.error(f"[AI Fix] {dimension} failed: {e}")
        raise HTTPException(status_code=500, detail=f"获取修复建议失败: {str(e)[:100]}")
