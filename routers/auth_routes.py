"""Authentication endpoints (login / status / change-password).

/ 认证相关端点（登录 / 状态 / 修改密码）。
"""

from fastapi import APIRouter

import auth as auth_module
from models import ChangePasswordRequest, LoginRequest
from routers.deps import ok

router = APIRouter()


@router.get("/api/auth/status")
def auth_status():
    return ok({"enabled": auth_module.is_enabled()})


@router.post("/api/auth/login")
def auth_login(data: LoginRequest):
    token = auth_module.login(data.password)
    if token:
        return ok({"token": token, "enabled": True})
    return ok({"token": None, "enabled": auth_module.is_enabled()})


@router.post("/api/auth/change-password")
def auth_change_password(data: ChangePasswordRequest):
    success = auth_module.change_password(data.old_password, data.new_password)
    if success:
        return ok(msg="密码已修改")
    return ok(msg="原密码错误")