from sqlalchemy.orm import Session
from domain.auth.models import SystemSetting
from core.config import BEDROCK_MODEL_ID, BEDROCK_REGION

SETTING_KEYS = [
    "ai_provider",           # bedrock / openai_compatible
    "bedrock_model_id",
    "bedrock_region",
    "bedrock_auth_mode",     # iam_role / ak_sk / api_key
    "bedrock_access_key",
    "bedrock_secret_key",
    "bedrock_api_key",
    # OpenAI Compatible (LiteLLM/OpenAI/Azure/Ollama/vLLM)
    "openai_api_base",       # API Base URL, e.g. https://api.openai.com/v1
    "openai_api_key",        # API Key
    "openai_model",          # Model name, e.g. gpt-4o, claude-3-sonnet
    # 图片存储
    "image_storage_mode",    # local / s3
    "image_s3_bucket",
    "image_s3_region",
    "image_s3_prefix",       # S3 key 前缀，如 "ses-sender/images/"
    "image_s3_access_key",   # 为空则用 IAM Role
    "image_s3_secret_key",
    "image_base_url",        # 回显域名，如 https://cdn.example.com
    # 退订页面自定义
    "unsub_page_title",      # 页面标题
    "unsub_page_subtitle",   # 副标题/描述
    "unsub_page_reasons",    # 退订原因选项 JSON 数组
    "unsub_page_success",    # 成功提示文案
    "unsub_page_logo",       # Logo 图片 URL
    "unsub_page_color",      # 品牌主色
    "unsub_page_button_text", # 确认退订按钮文字
    # SSO 配置
    "sso_github_enabled",
    "sso_github_client_id",
    "sso_github_client_secret",
    "sso_google_enabled",
    "sso_google_client_id",
    "sso_google_client_secret",
    "sso_saml_enabled",
    "sso_saml_idp_entity_id",
    "sso_saml_idp_sso_url",
    "sso_saml_idp_cert",
    "sso_saml_sp_entity_id",
]

_SECRET_KEYS = {"bedrock_secret_key", "bedrock_api_key", "openai_api_key", "image_s3_secret_key",
                "sso_github_client_secret", "sso_google_client_secret"}


def get_all_settings(db: Session) -> dict:
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(SETTING_KEYS)).all()
    result = {k: "" for k in SETTING_KEYS}
    for r in rows:
        result[r.key] = r.value or ""
    if not result.get("ai_provider"):
        result["ai_provider"] = "bedrock"
    if not result.get("bedrock_model_id"):
        result["bedrock_model_id"] = BEDROCK_MODEL_ID
    if not result.get("bedrock_region"):
        result["bedrock_region"] = BEDROCK_REGION
    if not result.get("bedrock_auth_mode"):
        result["bedrock_auth_mode"] = "iam_role"
    has_ak_sk = bool(result.get("bedrock_secret_key"))
    has_api_key = bool(result.get("bedrock_api_key"))
    has_openai_key = bool(result.get("openai_api_key"))
    has_s3_sk = bool(result.get("image_s3_secret_key"))
    for k in _SECRET_KEYS:
        result.pop(k, None)
    result["bedrock_has_ak_sk"] = has_ak_sk
    result["bedrock_has_api_key"] = has_api_key
    result["openai_has_key"] = has_openai_key
    result["sso_has_github_secret"] = bool(result.get("sso_github_client_secret"))
    result["sso_has_google_secret"] = bool(result.get("sso_google_client_secret"))
    result["image_has_s3_secret"] = has_s3_sk
    if not result.get("image_storage_mode"):
        result["image_storage_mode"] = "local"
    return result


def save_settings(db: Session, data: dict):
    for key in SETTING_KEYS:
        if key not in data:
            continue
        val = data[key]
        if key in _SECRET_KEYS and val == "":
            continue
        if val == "__CLEAR__":
            val = ""
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row:
            row.value = val
        else:
            db.add(SystemSetting(key=key, value=val))
    db.commit()


def get_image_storage_config(db: Session) -> dict:
    """获取图片存储配置"""
    from core.config import AWS_REGION
    keys = [k for k in SETTING_KEYS if k.startswith("image_")]
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(keys)).all()
    cfg = {r.key: r.value for r in rows if r.value}
    return {
        "mode": cfg.get("image_storage_mode") or "local",
        "s3_bucket": cfg.get("image_s3_bucket") or "",
        "s3_region": cfg.get("image_s3_region") or AWS_REGION,
        "s3_prefix": cfg.get("image_s3_prefix") or "ses-sender/images/",
        "s3_access_key": cfg.get("image_s3_access_key") or None,
        "s3_secret_key": cfg.get("image_s3_secret_key") or None,
        "base_url": cfg.get("image_base_url") or "",
    }


def get_unsub_page_config(db: Session, source_email: str = None) -> dict:
    """获取退订页面自定义配置（优先用户级，fallback 系统级）"""
    import json as _json

    user_cfg = {}
    if source_email:
        from domain.auth.models import User as UserModel
        users = db.query(UserModel).filter(UserModel.email == source_email).all()
        for user in users:
            if user.unsub_config:
                try:
                    user_cfg = _json.loads(user.unsub_config)
                except Exception:
                    pass
                if user_cfg:
                    break

    keys = [k for k in SETTING_KEYS if k.startswith("unsub_page_")]
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(keys)).all()
    sys_cfg = {r.key: r.value for r in rows if r.value}

    def val(field, sys_key, default):
        return user_cfg.get(field) or sys_cfg.get(sys_key) or default

    reasons = [
        {"value": "too_frequent", "label": "收到邮件太频繁"},
        {"value": "not_relevant", "label": "内容与我无关"},
        {"value": "never_subscribed", "label": "我从未订阅过"},
        {"value": "prefer_other", "label": "我更喜欢其他渠道获取信息"},
        {"value": "other", "label": "其他原因"},
    ]
    if user_cfg.get("reasons"):
        reasons = user_cfg["reasons"] if isinstance(user_cfg["reasons"], list) else reasons
    elif sys_cfg.get("unsub_page_reasons"):
        try:
            reasons = _json.loads(sys_cfg["unsub_page_reasons"])
        except Exception:
            pass

    return {
        "title": val("title", "unsub_page_title", "退订确认"),
        "subtitle": val("subtitle", "unsub_page_subtitle", "我们很遗憾看到您离开。请告诉我们退订原因，帮助我们改进服务。"),
        "reasons": reasons,
        "success": val("success", "unsub_page_success", "退订成功"),
        "logo": val("logo", "unsub_page_logo", ""),
        "color": val("color", "unsub_page_color", "#667eea"),
        "buttonText": val("buttonText", "unsub_page_button_text", "确认退订"),
    }


def get_bedrock_config(db: Session) -> dict:
    """获取 Bedrock 调用配置"""
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(SETTING_KEYS)).all()
    cfg = {r.key: r.value for r in rows if r.value}
    return {
        "model_id": cfg.get("bedrock_model_id") or BEDROCK_MODEL_ID,
        "region": cfg.get("bedrock_region") or BEDROCK_REGION,
        "auth_mode": cfg.get("bedrock_auth_mode") or "iam_role",
        "access_key": cfg.get("bedrock_access_key") or None,
        "secret_key": cfg.get("bedrock_secret_key") or None,
        "api_key": cfg.get("bedrock_api_key") or None,
    }


def get_openai_config(db: Session) -> dict:
    """获取 OpenAI 兼容 API 配置"""
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(SETTING_KEYS)).all()
    cfg = {r.key: r.value for r in rows if r.value}
    return {
        "api_base": cfg.get("openai_api_base") or "",
        "api_key": cfg.get("openai_api_key") or "",
        "model": cfg.get("openai_model") or "gpt-4o",
    }


def get_ai_provider(db: Session) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == "ai_provider").first()
    return (row.value if row and row.value else "bedrock")


def get_ai_models(db: Session) -> list:
    """获取 AI Provider+Model 列表"""
    import json as _json
    row = db.query(SystemSetting).filter(SystemSetting.key == "ai_models").first()
    if row and row.value:
        try:
            data = _json.loads(row.value)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_ai_models(db: Session, providers: list):
    import json as _json
    row = db.query(SystemSetting).filter(SystemSetting.key == "ai_models").first()
    val = _json.dumps(providers, ensure_ascii=False)
    if row:
        row.value = val
    else:
        db.add(SystemSetting(key="ai_models", value=val))
    db.commit()


def get_ai_model_by_id(db: Session, model_id: str) -> dict:
    """根据 model_id 找到 provider 配置 + model 配置，合并返回"""
    providers = get_ai_models(db)
    for p in providers:
        for m in p.get("models", []):
            if m.get("id") == model_id:
                result = {k: v for k, v in p.items() if k != "models"}
                result.update(m)
                return result
    if providers and providers[0].get("models"):
        p = providers[0]
        m = p["models"][0]
        result = {k: v for k, v in p.items() if k != "models"}
        result.update(m)
        return result
    return {}


def get_available_models(db: Session) -> list:
    """返回所有可用模型（供用户选择）"""
    providers = get_ai_models(db)
    result = []
    for p in providers:
        for m in p.get("models", []):
            result.append({
                "id": m.get("id"),
                "name": m.get("name", m.get("model_id") or m.get("model", "")),
                "provider_name": p.get("name", ""),
                "provider_type": p.get("type", ""),
            })
    return result


def test_ai_model(db: Session, data: dict) -> dict:
    """测试单个模型（传入 provider 配置 + model_id/model）"""
    ptype = data.get("type", "bedrock")
    if ptype == "openai_compatible":
        return _test_openai({"api_base": data.get("api_base",""), "api_key": data.get("api_key",""), "model": data.get("test_model","")})
    else:
        cfg = {
            "model_id": data.get("test_model",""), "region": data.get("region","") or BEDROCK_REGION,
            "auth_mode": data.get("auth_mode","iam_role"),
            "access_key": data.get("access_key"), "secret_key": data.get("secret_key"),
            "api_key": data.get("bedrock_api_key"),
        }
        mode = cfg["auth_mode"]
        if mode == "api_key" and cfg.get("api_key"):
            return _test_with_api_key(cfg)
        elif mode == "ak_sk" and cfg.get("access_key") and cfg.get("secret_key"):
            return _test_with_boto3(cfg, "AK/SK")
        else:
            return _test_with_boto3(cfg, "IAM Role")


def _test_openai(cfg: dict) -> dict:
    import json, urllib.request, urllib.error
    api_base = (cfg.get("api_base") or "").strip()
    if not api_base:
        return {"success": False, "auth_mode": "OpenAI Compatible", "error": "未配置 API Base URL"}
    url = api_base.rstrip("/") + "/chat/completions"
    payload = json.dumps({"model": cfg.get("model","gpt-4o"), "messages": [{"role":"user","content":"Say OK"}], "max_tokens": 32, "temperature": 0}).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg.get("api_key"):
        req.add_header("Authorization", f"Bearer {cfg['api_key']}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "auth_mode": "OpenAI Compatible", "model": cfg.get("model"), "reply": reply.strip()}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"success": False, "auth_mode": "OpenAI Compatible", "model": cfg.get("model"), "error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"success": False, "auth_mode": "OpenAI Compatible", "model": cfg.get("model"), "error": str(e)}


def test_bedrock_connection(db: Session, override: dict = None) -> dict:
    """测试 Bedrock 连通性"""
    cfg = get_bedrock_config(db)
    if override:
        for k in ["bedrock_auth_mode","bedrock_model_id","bedrock_region","bedrock_access_key","bedrock_secret_key","bedrock_api_key"]:
            if override.get(k): cfg[k.replace("bedrock_","")] = override[k]
    mode = cfg["auth_mode"]

    if mode == "api_key":
        if not cfg["api_key"]:
            return {"success": False, "auth_mode": "Bedrock API Key", "error": "未配置 Bedrock API Key"}
        return _test_with_api_key(cfg)
    elif mode == "ak_sk":
        if not cfg["access_key"] or not cfg["secret_key"]:
            return {"success": False, "auth_mode": "AK/SK", "error": "未配置 Access Key 或 Secret Key"}
        return _test_with_boto3(cfg, "AK/SK")
    else:
        return _test_with_boto3(cfg, "IAM Role")


def _test_with_api_key(cfg: dict) -> dict:
    """使用 Bedrock API Key (Bearer Token) 测试"""
    import json
    import urllib.request
    import urllib.error

    url = f"https://bedrock-runtime.{cfg['region']}.amazonaws.com/model/{cfg['model_id']}/converse"
    payload = json.dumps({
        "messages": [{"role": "user", "content": [{"text": "Say OK"}]}],
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {cfg['api_key']}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            reply = ""
            for block in data.get("output", {}).get("message", {}).get("content", []):
                if "text" in block:
                    reply += block["text"]
            return {"success": True, "auth_mode": "Bedrock API Key", "model_id": cfg["model_id"], "region": cfg["region"], "reply": reply.strip()}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"success": False, "auth_mode": "Bedrock API Key", "model_id": cfg["model_id"], "region": cfg["region"], "error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"success": False, "auth_mode": "Bedrock API Key", "model_id": cfg["model_id"], "region": cfg["region"], "error": str(e)}


def _test_with_boto3(cfg: dict, auth_label: str) -> dict:
    """使用 boto3 (IAM Role 或 AK/SK) 测试"""
    import boto3
    import json

    kwargs = {"region_name": cfg["region"]}
    if auth_label == "AK/SK" and cfg["access_key"] and cfg["secret_key"]:
        kwargs["aws_access_key_id"] = cfg["access_key"]
        kwargs["aws_secret_access_key"] = cfg["secret_key"]

    try:
        client = boto3.client("bedrock-runtime", **kwargs)
        response = client.converse(
            modelId=cfg["model_id"],
            messages=[{"role": "user", "content": [{"text": "Say OK"}]}],
            inferenceConfig={"maxTokens": 32, "temperature": 0},
        )
        reply = ""
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                reply += block["text"]
        return {"success": True, "auth_mode": auth_label, "model_id": cfg["model_id"], "region": cfg["region"], "reply": reply.strip()}
    except Exception as e:
        return {"success": False, "auth_mode": auth_label, "model_id": cfg["model_id"], "region": cfg["region"], "error": str(e)}


def test_openai_connection(db: Session, override: dict = None) -> dict:
    """测试 OpenAI 兼容 API 连通性"""
    import json
    import urllib.request
    import urllib.error

    cfg = get_openai_config(db)
    if override:
        if override.get("openai_api_base"): cfg["api_base"] = override["openai_api_base"]
        if override.get("openai_api_key"): cfg["api_key"] = override["openai_api_key"]
        if override.get("openai_model"): cfg["model"] = override["openai_model"]

    if not cfg["api_base"]:
        return {"success": False, "auth_mode": "OpenAI Compatible", "model": cfg["model"], "error": "未配置 API Base URL"}

    url = cfg["api_base"].rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 32,
        "temperature": 0,
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg["api_key"]:
        req.add_header("Authorization", f"Bearer {cfg['api_key']}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "auth_mode": "OpenAI Compatible", "model": cfg["model"], "api_base": cfg["api_base"], "reply": reply.strip()}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"success": False, "auth_mode": "OpenAI Compatible", "model": cfg["model"], "api_base": cfg["api_base"], "error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"success": False, "auth_mode": "OpenAI Compatible", "model": cfg["model"], "api_base": cfg["api_base"], "error": str(e)}
