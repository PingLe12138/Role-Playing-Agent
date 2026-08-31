from typing import Any, Dict, List, Optional

from services.base import BaseService
from services.id_utils import generate_relationship_id, now


class RelationshipService(BaseService):
    def upsert(self, data: Dict[str, Any]) -> str:
        session_id = data.get("sessionID", "")
        cid1 = data.get("characterID_1", "")
        cid2 = data.get("characterID_2", "")
        if not cid1 or not cid2:
            raise ValueError("characterID_1 (source), characterID_2 (target) are required")
        existing = self.db.fetchone(
            "SELECT relationshipID, sessionID FROM character_relationship "
            "WHERE sessionID = ? AND characterID_1 = ? AND characterID_2 = ?",
            (session_id, cid1, cid2),
        )
        now_ts = now()
        if existing:
            data["recordUpdatedTime"] = now_ts
            if session_id and not existing["sessionID"]:
                data["sessionID"] = session_id
            self.db.update("character_relationship", data, {"relationshipID": existing["relationshipID"]})
            return existing["relationshipID"]
        data.setdefault("relationshipID", generate_relationship_id())
        data["characterID_1"] = cid1
        data["characterID_2"] = cid2
        data.setdefault("recordCreatedTime", now_ts)
        data.setdefault("recordUpdatedTime", now_ts)
        data["sessionID"] = session_id
        self.db.insert("character_relationship", data)
        return data["relationshipID"]

    def get_between(self, session_id: str, from_cid: str, to_cid: str) -> Optional[Dict[str, Any]]:
        return self.db.fetchone(
            "SELECT * FROM character_relationship WHERE sessionID = ? AND characterID_1 = ? AND characterID_2 = ?",
            (session_id, from_cid, to_cid),
        )


# ─── Shared seeding helper ────────────────────────────────────────────────
# Used by both `introduce_character_node` and `review_character_node` to avoid
# duplicating the bidirectional "create missing relationships" loop.
# / 被 introduce_character_node 与 review_character_node 共用，避免重复双向"补建缺失关系"的循环。

FIRST_MEETING = {"relationship_type": "初次见面", "strength": 0.3, "sentiment": 0.0, "power_dynamic": 0.0}


def _clamp_relationship_fields(d: Dict[str, Any]) -> Dict[str, Any]:
    d["strength"] = max(0.0, min(1.0, float(d.get("strength", 0.5))))
    d["sentiment"] = max(-1.0, min(1.0, float(d.get("sentiment", 0.0))))
    d["power_dynamic"] = max(-1.0, min(1.0, float(d.get("power_dynamic", 0.0))))
    return d


def _find_default(default_map: Dict[str, List[Dict[str, Any]]], from_cid: str, to_cid: str) -> Optional[Dict[str, Any]]:
    """Look up a preset relationship from a character's `defaultRelationships` card field.
    / 从角色卡的 `defaultRelationships` 字段查预设关系。"""
    rels = default_map.get(from_cid, [])
    for r in rels:
        if r.get("characterID", "") == to_cid:
            return _clamp_relationship_fields(
                {
                    "relationship_type": r.get("relationship_type", "neutral"),
                    "strength": r.get("strength", 0.5),
                    "sentiment": r.get("sentiment", 0.0),
                    "power_dynamic": r.get("power_dynamic", 0.0),
                }
            )
    return None


def seed_bidirectional_relationships(
    rel_service: "RelationshipService",
    session_id: str,
    new_ids: List[str],
    existing_ids: List[str],
    *,
    default_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    brand_new_ids: Optional[set] = None,
) -> None:
    """Create bidirectional relationships for newly arrived characters, skipping
    any direction that already exists.

    / 为新抵达的角色建立双向关系，跳过已存在的方向。

    For each ordered pair (new_id -> existing_id) and (existing_id -> new_id):
    / 对每个有序对 (new_id -> existing_id) 与 (existing_id -> new_id)：

      * if a relationship already exists for that direction → skip
        / 该方向已存在关系 → 跳过
      * else if a preset is found in `default_map[from][to]` → use it
        / 否则在 `default_map[from][to]` 中找到预设 → 使用预设
      * else if `new_id` is in `brand_new_ids` → use the "初次见面" first-meeting default
        / 否则 `new_id` 属于全新角色 → 使用"初次见面"默认
      * else → leave absent (matches introduce_character_node's behaviour for
        re-introduced pre-existing characters without a preset)
        / 否则 → 不创建（与 introduce_character_node 对无预设的复用老角色行为一致）

    Callers / 调用方:
      * `introduce_character_node`: passes a `default_map` loaded from the
        re-introduced characters' cards and `brand_new_ids` = the brand-new IDs.
      * `review_character_node`: passes no default_map and
        `brand_new_ids = set(new_ids)` so every new character gets "初次见面".
    """
    default_map = default_map or {}
    brand_new_ids = brand_new_ids or set()

    for new_id in new_ids:
        for existing_id in existing_ids:
            # direction: new -> existing
            if not rel_service.get_between(session_id, new_id, existing_id):
                defaults = _find_default(default_map, new_id, existing_id)
                if defaults:
                    rel_service.upsert(
                        {"sessionID": session_id, "characterID_1": new_id, "characterID_2": existing_id, **defaults}
                    )
                elif new_id in brand_new_ids:
                    rel_service.upsert(
                        {"sessionID": session_id, "characterID_1": new_id, "characterID_2": existing_id, **FIRST_MEETING}
                    )

            # direction: existing -> new
            if not rel_service.get_between(session_id, existing_id, new_id):
                defaults = _find_default(default_map, existing_id, new_id)
                if defaults:
                    rel_service.upsert(
                        {"sessionID": session_id, "characterID_1": existing_id, "characterID_2": new_id, **defaults}
                    )
                elif new_id in brand_new_ids:
                    rel_service.upsert(
                        {"sessionID": session_id, "characterID_1": existing_id, "characterID_2": new_id, **FIRST_MEETING}
                    )
