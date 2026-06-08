"""SSO Authentication: GitHub OAuth2, Google OAuth2, SAML"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.database import get_db, SessionLocal
from core.config import SECRET_KEY
from domain.auth.models import User, SystemSetting
from domain.auth.service import create_access_token, hash_password

router = APIRouter(tags=["SSO"])
logger = logging.getLogger("ses-sender.sso")


def _get_sso_config(db: Session) -> dict:
    keys = [k for k in [
        "sso_github_enabled", "sso_github_client_id", "sso_github_client_secret",
        "sso_google_enabled", "sso_google_client_id", "sso_google_client_secret",
        "sso_saml_enabled", "sso_saml_idp_entity_id", "sso_saml_idp_sso_url",
        "sso_saml_idp_cert", "sso_saml_sp_entity_id",
    ]]
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(keys)).all()
    return {r.key: r.value for r in rows if r.value}


def _find_or_create_user(db: Session, email: str, display_name: str, provider: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = db.query(User).filter(User.username == email).first()
    if not user:
        username = email.split("@")[0]
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            username = email
        user = User(
            username=username,
            display_name=display_name or username,
            hashed_password=hash_password(f"sso_{provider}_{email}"),
            email=email,
            is_admin=False,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[SSO] Created user {username} via {provider}")
    return user


@router.get("/sso/providers")
def list_sso_providers(db: Session = Depends(get_db)):
    """获取启用的 SSO 提供商列表（登录页使用）"""
    cfg = _get_sso_config(db)
    providers = []
    if cfg.get("sso_github_enabled") == "true" and cfg.get("sso_github_client_id"):
        providers.append({"id": "github", "name": "GitHub", "icon": "github"})
    if cfg.get("sso_google_enabled") == "true" and cfg.get("sso_google_client_id"):
        providers.append({"id": "google", "name": "Google", "icon": "google"})
    if cfg.get("sso_saml_enabled") == "true" and cfg.get("sso_saml_idp_sso_url"):
        providers.append({"id": "saml", "name": "企业 SSO", "icon": "saml"})
    return providers


# ==================== GitHub OAuth2 ====================

@router.get("/sso/github/login")
def github_login(redirect_uri: str = Query(""), db: Session = Depends(get_db)):
    cfg = _get_sso_config(db)
    client_id = cfg.get("sso_github_client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="GitHub SSO 未配置")
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "scope": "user:email",
        "redirect_uri": redirect_uri or "",
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/sso/github/callback")
def github_callback(code: str = Query(""), db: Session = Depends(get_db)):
    cfg = _get_sso_config(db)
    client_id = cfg.get("sso_github_client_id")
    client_secret = cfg.get("sso_github_client_secret")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="GitHub SSO 未配置")

    data = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret, "code": code}).encode()
    req = urllib.request.Request("https://github.com/login/oauth/access_token", data=data)
    req.add_header("Accept", "application/json")
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub token exchange failed: {e}")

    access_token = resp.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"GitHub auth failed: {resp.get('error_description', 'unknown')}")

    req2 = urllib.request.Request("https://api.github.com/user")
    req2.add_header("Authorization", f"Bearer {access_token}")
    try:
        gh_user = json.loads(urllib.request.urlopen(req2, timeout=10).read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API failed: {e}")

    email = gh_user.get("email")
    if not email:
        req3 = urllib.request.Request("https://api.github.com/user/emails")
        req3.add_header("Authorization", f"Bearer {access_token}")
        try:
            emails = json.loads(urllib.request.urlopen(req3, timeout=10).read())
            for em in emails:
                if em.get("primary"):
                    email = em["email"]
                    break
            if not email and emails:
                email = emails[0]["email"]
        except Exception:
            pass

    if not email:
        raise HTTPException(status_code=400, detail="无法获取 GitHub 邮箱")

    user = _find_or_create_user(db, email, gh_user.get("name", ""), "github")
    token = create_access_token({"sub": user.username})

    return RedirectResponse(f"/?sso_token={token}&sso_user={urllib.parse.quote(json.dumps({'id':user.id,'username':user.username,'display_name':user.display_name,'email':user.email,'is_admin':user.is_admin}))}")


# ==================== Google OAuth2 ====================

@router.get("/sso/google/login")
def google_login(redirect_uri: str = Query(""), db: Session = Depends(get_db)):
    cfg = _get_sso_config(db)
    client_id = cfg.get("sso_google_client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Google SSO 未配置")
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/sso/google/callback")
def google_callback(code: str = Query(""), redirect_uri: str = Query(""), db: Session = Depends(get_db)):
    cfg = _get_sso_config(db)
    client_id = cfg.get("sso_google_client_id")
    client_secret = cfg.get("sso_google_client_secret")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Google SSO 未配置")

    data = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google token exchange failed: {e}")

    id_token = resp.get("id_token")
    access_token = resp.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Google auth failed")

    req2 = urllib.request.Request("https://www.googleapis.com/oauth2/v2/userinfo")
    req2.add_header("Authorization", f"Bearer {access_token}")
    try:
        g_user = json.loads(urllib.request.urlopen(req2, timeout=10).read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google API failed: {e}")

    email = g_user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="无法获取 Google 邮箱")

    user = _find_or_create_user(db, email, g_user.get("name", ""), "google")
    token = create_access_token({"sub": user.username})

    return RedirectResponse(f"/?sso_token={token}&sso_user={urllib.parse.quote(json.dumps({'id':user.id,'username':user.username,'display_name':user.display_name,'email':user.email,'is_admin':user.is_admin}))}")


# ==================== SAML ====================

@router.get("/sso/saml/login")
def saml_login(db: Session = Depends(get_db)):
    cfg = _get_sso_config(db)
    idp_sso_url = cfg.get("sso_saml_idp_sso_url")
    sp_entity_id = cfg.get("sso_saml_sp_entity_id", "ses-sender")
    if not idp_sso_url:
        raise HTTPException(status_code=400, detail="SAML SSO 未配置")

    import base64
    import time
    request_id = f"ses_{int(time.time())}"
    saml_request = f"""<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
        ID="{request_id}" Version="2.0" IssueInstant="{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        AssertionConsumerServiceURL="/sso/saml/callback"
        Issuer="{sp_entity_id}">
        <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">{sp_entity_id}</saml:Issuer>
    </samlp:AuthnRequest>"""

    encoded = base64.b64encode(saml_request.encode()).decode()
    params = urllib.parse.urlencode({"SAMLRequest": encoded})
    return RedirectResponse(f"{idp_sso_url}?{params}")


@router.post("/sso/saml/callback")
async def saml_callback(request, db: Session = Depends(get_db)):
    """SAML ACS (Assertion Consumer Service) endpoint"""
    import base64
    import xml.etree.ElementTree as ET
    from fastapi import Request

    form = await request.form()
    saml_response = form.get("SAMLResponse", "")
    if not saml_response:
        raise HTTPException(status_code=400, detail="Missing SAMLResponse")

    try:
        xml_str = base64.b64decode(saml_response).decode()
        root = ET.fromstring(xml_str)
        ns = {"saml": "urn:oasis:names:tc:SAML:2.0:assertion"}

        email = None
        name = None
        for attr in root.iter("{urn:oasis:names:tc:SAML:2.0:assertion}Attribute"):
            attr_name = attr.get("Name", "")
            val_el = attr.find("saml:AttributeValue", ns)
            val = val_el.text if val_el is not None else ""
            if "email" in attr_name.lower():
                email = val
            elif "name" in attr_name.lower() or "displayname" in attr_name.lower():
                name = val

        if not email:
            name_id = root.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}NameID")
            if name_id is not None and "@" in (name_id.text or ""):
                email = name_id.text

        if not email:
            raise HTTPException(status_code=400, detail="SAML response 中未找到邮箱")

        user = _find_or_create_user(db, email, name or "", "saml")
        token = create_access_token({"sub": user.username})

        return RedirectResponse(f"/?sso_token={token}&sso_user={urllib.parse.quote(json.dumps({'id':user.id,'username':user.username,'display_name':user.display_name,'email':user.email,'is_admin':user.is_admin}))}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SAML] Parse failed: {e}")
        raise HTTPException(status_code=400, detail=f"SAML 解析失败: {str(e)}")
