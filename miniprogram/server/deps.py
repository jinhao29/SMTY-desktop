# -*- coding: utf-8 -*-
"""FastAPI 依赖：token 校验。"""
from fastapi import Header, HTTPException

from passlib_lite import verify_token


def get_current_user(authorization: str = Header(default='')):
    token = authorization.replace('Bearer ', '').strip()
    identity = verify_token(token)
    if not identity:
        raise HTTPException(status_code=401, detail='未登录或登录已过期')
    return {'user_id': identity[0], 'phone': identity[1]}
