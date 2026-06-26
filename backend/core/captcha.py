"""
后端图形验证码（SVG）+ Redis 存储。

流程：
1. GET /auth/captcha → generate() 生成 4 位验证码，画成 SVG，
   把答案存入 Redis（captcha:{id}，TTL 120s），返回 {captcha_id, image(SVG data URI)}。
2. POST /auth/login 校验 captcha_id + captcha_code，verify() 用 GETDEL 取出比对（一次性，防重放）。

降级策略：Redis 不可用时 verify() 返回 True（跳过校验，可用性优先）。
"""

import base64
import random
import uuid
import html

from core import redis_cache

_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
_CODE_LEN = 4
_TTL = 120
_KEY_PREFIX = "captcha:"


def _random_code() -> str:
    return "".join(random.choice(_CHARS) for _ in range(_CODE_LEN))


def _render_svg(code: str) -> str:
    """把验证码渲染成带干扰的 SVG 图片。"""
    w, h = 120, 40
    rnd = random.Random(code + str(random.random()))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" fill="#f0f0f0"/>',
    ]
    # 干扰线
    for _ in range(4):
        x1, y1, x2, y2 = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(0, w), rnd.randint(0, h)
        hue = rnd.randint(0, 360)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="hsl({hue},50%,70%)" stroke-width="1"/>'
        )
    # 干扰点
    for _ in range(30):
        cx, cy = rnd.randint(0, w), rnd.randint(0, h)
        hue = rnd.randint(0, 360)
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="1" fill="hsl({hue},40%,70%)"/>')
    # 字符
    for i, ch in enumerate(code):
        x = 16 + i * 26 + rnd.randint(-2, 2)
        y = 28 + rnd.randint(-3, 3)
        rot = rnd.randint(-18, 18)
        size = 20 + rnd.randint(0, 6)
        hue = rnd.randint(0, 360)
        safe = html.escape(ch)
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" '
            f'font-family="Courier New, monospace" font-weight="bold" '
            f'fill="hsl({hue},70%,35%)" '
            f'transform="rotate({rot} {x} {y})">{safe}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def generate() -> dict:
    """生成验证码，存入 Redis，返回 {captcha_id, image(data URI)}。"""
    code = _random_code()
    captcha_id = uuid.uuid4().hex
    redis_cache.setex(_KEY_PREFIX + captcha_id, code.lower(), _TTL)
    svg = _render_svg(code)
    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return {"captcha_id": captcha_id, "image": data_uri}


def verify(captcha_id: str, code: str) -> bool:
    """
    校验验证码（一次性，取出后即删）。
    - Redis 不可用：返回 True（跳过校验，可用性优先）。
    - id/code 为空、过期、不匹配：返回 False。
    """
    if not redis_cache.available():
        return True
    if not captcha_id or not code:
        return False
    stored = redis_cache.getdel(_KEY_PREFIX + captcha_id)
    if stored is None:
        return False
    return str(stored).strip().lower() == code.strip().lower()
