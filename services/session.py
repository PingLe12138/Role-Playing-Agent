import json
from typing import Any, Dict, List, Optional

from RPA_langGraph.entities import Session, SessionHistory
from services.base import BaseService
from services.id_utils import generate_history_id, generate_session_id, now


def _json_dumps(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False)


def _json_loads(val: Optional[str], default: Any = None) -> Any:
    if val:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


_EMPTY_ENV = {"location": "", "time": "", "atmosphere": ""}


class SessionService(BaseService):
    def create(self, data: Dict) -> Session:
        data.setdefault("sessionID", generate_session_id())
        data.setdefault("sessionPresentCharacter", [])
        data.setdefault("sessionDepartedCharacter", [])
        data.setdefault("sessionEnvData", dict(_EMPTY_ENV))
        data.setdefault("sessionPendingChoice", None)
        data.setdefault("memoryRoundCounter", 0)
        data.setdefault("outline", [])
        data.setdefault("recordCreatedTime", now())
        data.setdefault("recordUpdatedTime", now())
        insert_data = dict(data)
        for key in (
            "sessionPresentCharacter",
            "sessionDepartedCharacter",
            "sessionEnvData",
            "outline",
        ):
            insert_data[key] = _json_dumps(data[key])
        if "sessionPendingChoice" in data:
            insert_data["sessionPendingChoice"] = (
                _json_dumps(data["sessionPendingChoice"]) if data["sessionPendingChoice"] else None
            )
        self._insert("session", insert_data)
        return Session(**data)

    def get(self, session_id: str) -> Optional[Session]:
        row = self._get("session", "sessionID", session_id)
        if row:
            return self._decode_row(row)
        return None

    def update(self, session_id: str, data: dict) -> int:
        if "sessionPresentCharacter" in data and isinstance(data["sessionPresentCharacter"], list):
            data["sessionPresentCharacter"] = _json_dumps(data["sessionPresentCharacter"])
        if "sessionDepartedCharacter" in data and isinstance(data["sessionDepartedCharacter"], list):
            data["sessionDepartedCharacter"] = _json_dumps(data["sessionDepartedCharacter"])
        if "sessionEnvData" in data and isinstance(data["sessionEnvData"], dict):
            data["sessionEnvData"] = _json_dumps(data["sessionEnvData"])
        if "sessionPendingChoice" in data:
            if data["sessionPendingChoice"] is None:
                data["sessionPendingChoice"] = None
            elif isinstance(data["sessionPendingChoice"], dict):
                data["sessionPendingChoice"] = _json_dumps(data["sessionPendingChoice"])
        if "outline" in data and isinstance(data["outline"], list):
            data["outline"] = _json_dumps(data["outline"])
        return self._update("session", "sessionID", session_id, data)

    def delete_cascade(self, session_id: str) -> int:
        self.db.execute("DELETE FROM session_history WHERE parentID = ?", (session_id,))
        self.db.execute("DELETE FROM memory WHERE sessionID = ?", (session_id,))
        return self._delete("session", "sessionID", session_id)

    def list_all(self) -> List[Session]:
        return [self._decode_row(r) for r in self._list("session")]

    def list_page(self, page: int = 1, page_size: int = 10, keyword: Optional[str] = None):
        """分页查询会话，按创建时间倒序；返回 (total, rows)。"""
        page = max(1, int(page))
        page_size = min(max(1, int(page_size)), 100)
        params: list = []
        where = ""
        if keyword:
            where = "WHERE sessionTitle LIKE ?"
            params.append(f"%{keyword}%")
        total = self.db.fetchone(
            f"SELECT COUNT(*) AS n FROM session {where}", tuple(params)
        )["n"]
        params.append(page_size)
        params.append((page - 1) * page_size)
        rows = self.db.fetchall(
            f"SELECT * FROM session {where} ORDER BY recordCreatedTime DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
        return total, [self._decode_row(r) for r in rows]

    def _decode_row(self, row: dict) -> Session:
        data = dict(row)
        data["sessionPresentCharacter"] = _json_loads(data.get("sessionPresentCharacter"), [])
        data["sessionDepartedCharacter"] = _json_loads(data.get("sessionDepartedCharacter"), [])
        data["sessionEnvData"] = _json_loads(data.get("sessionEnvData"), dict(_EMPTY_ENV))
        data["sessionPendingChoice"] = _json_loads(data.get("sessionPendingChoice"))
        data["outline"] = _json_loads(data.get("outline"), [])
        data.setdefault("sessionPresentCharacter", [])
        data.setdefault("sessionDepartedCharacter", [])
        data.setdefault("sessionEnvData", dict(_EMPTY_ENV))
        data.setdefault("sessionPendingChoice", None)
        data.setdefault("memoryRoundCounter", 0)
        return Session(**data)


class SessionHistoryService(BaseService):
    def create(self, data: Dict) -> SessionHistory:
        data.setdefault("sessionHistoryID", generate_history_id())
        data.setdefault("recordCreatedTime", now())
        data.setdefault("recordUpdatedTime", now())
        entity = SessionHistory(**data)
        self._insert("session_history", dict(entity))
        return entity

    def get(self, history_id: str) -> Optional[SessionHistory]:
        row = self._get("session_history", "sessionHistoryID", history_id)
        return SessionHistory(**row) if row else None

    def update(self, history_id: str, data: dict) -> int:
        return self._update("session_history", "sessionHistoryID", history_id, data)

    def delete_cascade(self, history_id: str) -> int:
        return self._delete("session_history", "sessionHistoryID", history_id)

    def delete(self, history_id: str) -> int:
        return self.delete_cascade(history_id)

    def delete_by_session(self, session_id: str) -> int:
        return self.db.delete("session_history", {"parentID": session_id})

    def list_by_session(self, session_id: str) -> List[SessionHistory]:
        rows = self._list("session_history", "parentID = ?", (session_id,))
        return [SessionHistory(**row) for row in rows]
