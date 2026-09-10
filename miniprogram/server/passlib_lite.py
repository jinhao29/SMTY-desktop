# -*- coding: utf-8 -*-
"""轻量认证工具：密码哈希（pbkdf2）+ HMAC token 签发/校验。零第三方依赖。"""
import hashlib
import hmac
import os
import time
import base64

# token 签名密钥：必须由环境变量提供。硬编码默认值等同于公开密钥——
# 源码可见即可伪造任意用户 token，故缺失时直接拒绝启动。
SECRET = os.environ.get('MP_SECRET', '')
if not SECRET or len(SECRET) < 16:
    raise RuntimeError(
        'MP_SECRET 未设置或过短（至少 16 字符）。\n'
        '请先生成并注入，例如：\n'
        '  export MP_SECRET="$(python -c \\"import secrets;print(secrets.token_urlsafe(32))\\")"\n'
        '缺失该变量时后端拒绝启动，以避免使用可预测的签名密钥。')

TOKEN_TTL = 7 * 24 * 3600  # 7 天


def hash_password(password: str, salt: str = '') -> str:
    salt = salt or os.urandom(8).hex()
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 60000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split('$', 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def _sign(payload: bytes) -> str:
    return hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()


def issue_token(user_id: int, phone: str) -> str:
    payload = f"{user_id}.{phone}.{int(time.time()) + TOKEN_TTL}".encode()
    b64 = base64.urlsafe_b64encode(payload).decode().rstrip('=')
    return f"{b64}.{_sign(payload)}"


def verify_token(token: str):
    """返回 (user_id, phone)；无效返回 None。"""
    try:
        b64, sig = token.rsplit('.', 1)
        payload = base64.urlsafe_b64decode(b64 + '=' * (-len(b64) % 4))
        if not hmac.compare_digest(_sign(payload), sig):
            return None
        uid, phone, exp = payload.decode().split('.')
        if int(exp) < time.time():
            return None
        return int(uid), phone
    except Exception:
        return None
