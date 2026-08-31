import json
from typing import Optional
import uuid

import paths

_AUTH_PASSWORD: Optional[str] = None
_AUTH_TOKEN: Optional[str] = None


def load_auth_config():
    global _AUTH_PASSWORD
    try:
        with open(paths.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        _AUTH_PASSWORD = cfg.get("auth_password", "") or ""
    except Exception:
        _AUTH_PASSWORD = ""
    global _AUTH_TOKEN
    _AUTH_TOKEN = None


def is_enabled() -> bool:
    return bool(_AUTH_PASSWORD)


def login(password: str) -> Optional[str]:
    if not _AUTH_PASSWORD or password != _AUTH_PASSWORD:
        return None
    global _AUTH_TOKEN
    _AUTH_TOKEN = uuid.uuid4().hex
    return _AUTH_TOKEN


def check_token(token: Optional[str]) -> bool:
    if not _AUTH_PASSWORD:
        return True
    if not _AUTH_TOKEN or not token:
        return False
    return token == _AUTH_TOKEN


def change_password(old: str, new: str) -> bool:
    global _AUTH_PASSWORD, _AUTH_TOKEN
    if old != _AUTH_PASSWORD:
        return False
    if not new:
        return False
    _AUTH_PASSWORD = new
    _AUTH_TOKEN = None
    try:
        with open(paths.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["auth_password"] = new
        with open(paths.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False
