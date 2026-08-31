from datetime import datetime
import time
import uuid

from pypinyin import lazy_pinyin


def _ts_suffix() -> str:
    return hex(int(time.time() * 1000))[2:]


def _rand_suffix(length: int = 12) -> str:
    return uuid.uuid4().hex[:length]


def new_id(prefix: str) -> str:
    return f"{prefix}_{_ts_suffix()}_{_rand_suffix(12)}"


def name_to_pinyin(name: str) -> str:
    if not name:
        return "unknown"
    try:
        parts = lazy_pinyin(name)
        return "_".join(parts)
    except Exception:
        return name


def generate_character_id(name: str) -> str:
    return f"char_{name_to_pinyin(name)}_{_rand_suffix(8)}"


def generate_user_character_id(name: str) -> str:
    return f"uchr_{name_to_pinyin(name)}_{_rand_suffix(8)}"


def generate_wvc_id(name: str) -> str:
    return f"wvc_{name_to_pinyin(name)}_{_rand_suffix(8)}"


def generate_wve_id() -> str:
    return new_id("wve")


def generate_session_id() -> str:
    return new_id("ses")


def generate_history_id() -> str:
    return new_id("hst")


def generate_memory_id() -> str:
    return new_id("mem")


def generate_relationship_id() -> str:
    return new_id("rel")


def generate_emotion_state_id() -> str:
    return new_id("emo")


def now() -> str:
    return datetime.now().isoformat()
