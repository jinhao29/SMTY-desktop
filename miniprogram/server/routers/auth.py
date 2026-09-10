# -*- coding: utf-8 -*-
"""认证接口：POST /auth/login、POST /auth/logout、GET /auth/me。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import execute, query_one, now_str
from deps import get_current_user
from passlib_lite import verify_password, issue_token

router = APIRouter(prefix='/api/v1/auth', tags=['auth'])


class LoginBody(BaseModel):
    phone: str
    password: str


@router.post('/login')
def login(body: LoginBody):
    user = query_one("SELECT * FROM users WHERE phone=?", (body.phone,))
    if not user or not verify_password(body.password, user['password_hash']):
        raise HTTPException(status_code=400, detail='手机号或密码错误')
    token = issue_token(user['id'], user['phone'])
    return {'token': token, 'user': {'id': user['id'], 'phone': user['phone'],
                                     'name': user['name'], 'role': user['role']}}


@router.post('/logout')
def logout(user=Depends(get_current_user)):
    # 无状态 token，客户端删除本地缓存即可
    return {'ok': True}


@router.get('/me')
def me(user=Depends(get_current_user)):
    row = query_one("SELECT id, phone, name, role, created_at FROM users WHERE id=?",
                    (user['user_id'],))
    if not row:
        raise HTTPException(status_code=404, detail='用户不存在')
    return row
