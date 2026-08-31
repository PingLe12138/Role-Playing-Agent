import json
from typing import Any, Dict, List, Optional

from services.base import BaseService
from services.id_utils import generate_emotion_state_id, now


class EmotionStateService(BaseService):
    def insert(self, data: Dict[str, Any]) -> str:
        data.setdefault("emotionStateID", generate_emotion_state_id())
        now_ts = now()
        data.setdefault("recordCreatedTime", now_ts)
        self.db.insert("character_emotion_state", data)
        return data["emotionStateID"]

    def get_latest(self, session_id: str, character_id: str) -> Optional[Dict[str, Any]]:
        return self.db.fetchone(
            "SELECT * FROM character_emotion_state WHERE sessionID = ? AND characterID = ? "
            "ORDER BY recordCreatedTime DESC LIMIT 1",
            (session_id, character_id),
        )


# ─── Shared seeding helper ────────────────────────────────────────────────
# Used by `introduce_character_node` (角色登场) and `app.create_session`
# (会话开始) to seed a character's initial emotion from its card, de-duplicating
# the JSON-parse-and-fallback logic that previously lived in both call sites.
# / 被 introduce_character_node（角色登场）和 app.create_session（会话开始）共用，
#   从角色卡读取初始情绪并写入，消除两处重复的 JSON 解析与回退逻辑。


def seed_initial_emotion(
    emotion_svc: "EmotionStateService",
    db,
    session_id: str,
    character_id: str,
    *,
    trigger_summary: str = "角色登场",
) -> None:
    """Insert the character's initial emotion snapshot if none exists yet.

    / 若角色尚无情绪记录，则从其角色卡的 `initialEmotion` JSON 字段读取初始情绪并写入一条快照。
    Safe to call multiple times — only inserts when `get_latest` is empty.
    / 可重复调用——仅在 `get_latest` 为空时插入。
    """
    if emotion_svc.get_latest(session_id, character_id):
        return

    initial: Dict[str, Any] = {}
    card = db.fetchone("SELECT initialEmotion FROM character_info_card WHERE characterID = ?", (character_id,))
    if card and card.get("initialEmotion"):
        try:
            initial = json.loads(card["initialEmotion"])
        except Exception:
            initial = {}

    emotion_svc.insert(
        {
            "sessionID": session_id,
            "characterID": character_id,
            "emotionLabel": initial.get("emotionLabel") or "平静",
            "valence": initial.get("valence", 0.0),
            "arousal": initial.get("arousal", 0.5),
            "intensity": initial.get("intensity", 0.0),
            "energy": initial.get("energy", 1.0),
            "stress": initial.get("stress", 0.0),
            "triggerSummary": trigger_summary,
        }
    )


def seed_initial_emotions(
    emotion_svc: "EmotionStateService",
    db,
    session_id: str,
    character_ids: List[str],
    *,
    trigger_summary: str = "角色登场",
) -> None:
    """Seed initial emotions for a list of characters (skipping any that already have one).
    / 为多个角色批量写入初始情绪（已有记录的跳过）。"""
    for cid in character_ids:
        seed_initial_emotion(emotion_svc, db, session_id, cid, trigger_summary=trigger_summary)
