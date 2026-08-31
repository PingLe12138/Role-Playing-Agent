"""Shared application singletons and helpers used by all routers.

/ 所有路由共用的应用级单例与辅助函数。

Holds the SQLite client, the 9 service singletons, the graph-execution thread
pool and the in-memory task-status registry. Defined once here so that every
router (and `app.py`'s lifespan) shares the exact same instances.
/ 在此统一定义 SQLite 客户端、9 个服务单例、图执行线程池与任务状态注册表，
  供所有路由及 app.py 的 lifespan 共享同一实例。
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from DatabaseManager import DatabaseManager
from models import ApiResponse
from services import (
    CharacterInfoCardService,
    EmotionStateService,
    RelationshipService,
    SessionHistoryService,
    SessionService,
    UserCharacterInfoCardService,
    WorldviewCollectionService,
    WorldviewEntryService,
)
from SQLiteClient import get_db

# ─── Persistence / executor singletons ────────────────────────────────────
db = get_db()
db_mgr = DatabaseManager()
executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix="graph")
graph_tasks: Dict[str, str] = {}

# ─── Service singletons ────────────────────────────────────────────────────
character_svc = CharacterInfoCardService(db)
user_character_svc = UserCharacterInfoCardService(db)
relationship_svc = RelationshipService(db)
emotion_svc = EmotionStateService(db)
wvc_svc = WorldviewCollectionService(db)
wve_svc = WorldviewEntryService(db)
session_svc = SessionService(db)
history_svc = SessionHistoryService(db)


def ok(data: Any = None, msg: str = "ok") -> ApiResponse:
    """Wrap a response payload in the standard `ApiResponse` envelope.
    / 用标准 `ApiResponse` 信封包装响应载荷。"""
    return ApiResponse(data=data, msg=msg)