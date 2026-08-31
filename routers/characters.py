"""Character cards, user characters, relationships and emotion endpoints.

/ 角色卡、用户角色、角色关系与情绪相关端点。
"""

from datetime import datetime
import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ChromaDBClient import get_chroma
from models import (
    CharacterCardCreate,
    CharacterCardExportData,
    CharacterCardExportItem,
    CharacterCardUpdate,
    RelationshipsBatchCreate,
    UserCharacterCreate,
    UserCharacterExportData,
    UserCharacterExportItem,
    UserCharacterUpdate,
)
from routers.deps import character_svc, emotion_svc, ok, relationship_svc, user_character_svc
from services.id_utils import generate_character_id, generate_user_character_id
from SQLiteClient import get_db

router = APIRouter()


# ─── Character Cards ────────────────────────────────────────────────


@router.get("/api/character-cards")
def list_character_cards():
    return ok([dict(r) for r in character_svc.list_all()])


@router.post("/api/character-cards")
def create_character_card(data: CharacterCardCreate):
    cid = generate_character_id(data.characterName)
    defaults = [rel.model_dump() for rel in data.relationships if rel.characterID_1 == cid]
    initial_emotion = json.dumps(data.initialEmotion.model_dump()) if data.initialEmotion else "{}"
    card = character_svc.create(
        {
            "characterID": cid,
            "characterName": data.characterName,
            "characterInfo": data.characterInfo,
            "defaultRelationships": json.dumps(defaults),
            "initialEmotion": initial_emotion,
        }
    )
    return ok(dict(card))


@router.get("/api/character-cards/{cid}")
def get_character_card(cid: str):
    card = character_svc.get(cid)
    if not card:
        raise HTTPException(404, "角色卡不存在")
    return ok(dict(card))


@router.put("/api/character-cards/{cid}")
def update_character_card(cid: str, data: CharacterCardUpdate):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "没有需要更新的字段")
    if "defaultRelationships" in patch:
        patch["defaultRelationships"] = json.dumps(patch["defaultRelationships"])
    if "initialEmotion" in patch:
        patch["initialEmotion"] = json.dumps(patch["initialEmotion"])
    character_svc.update(cid, patch)
    return ok(msg="更新成功")


@router.delete("/api/character-cards/{cid}")
def delete_character_card(cid: str):
    character_svc.delete_cascade(cid)
    try:
        for col in get_chroma().list_collections():
            if col.name.endswith(f"_memory_{cid}"):
                get_chroma().delete_collection(col.name)
    except Exception:
        pass
    return ok(msg="删除成功")


# ─── Character Card Export / Import ──────────────────────────────────


@router.get("/api/character-cards/{cid}/export")
def export_character_card(cid: str):
    card = character_svc.get(cid)
    if not card:
        raise HTTPException(404, "角色卡不存在")
    export_data = CharacterCardExportData(
        exported_at=datetime.now().isoformat(),
        characters=[
            CharacterCardExportItem(
                characterName=card["characterName"],
                characterInfo=card.get("characterInfo", ""),
                defaultRelationships=card.get("defaultRelationships", "[]"),
                initialEmotion=card.get("initialEmotion", "{}"),
            )
        ],
    )
    safe_name = card["characterName"].replace(" ", "_")
    filename = f"{safe_name}_character.json"
    encoded_name = quote(filename, safe="")
    return Response(
        content=export_data.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.post("/api/character-cards/import")
def import_character_cards(data: CharacterCardExportData):
    created = []
    for item in data.characters:
        if not item.characterName:
            continue
        cid = generate_character_id(item.characterName)
        card = character_svc.create(
            {
                "characterID": cid,
                "characterName": item.characterName,
                "characterInfo": item.characterInfo,
                "defaultRelationships": item.defaultRelationships,
                "initialEmotion": item.initialEmotion,
            }
        )
        created.append(dict(card))
    return ok(created)


# ─── User Characters ──────────────────────────────────────────────


@router.get("/api/user-characters")
def list_user_characters():
    return ok([dict(r) for r in user_character_svc.list_all()])


@router.post("/api/user-characters")
def create_user_character(data: UserCharacterCreate):
    uid = generate_user_character_id(data.userCharacterName)
    defaults = [rel.model_dump() for rel in data.relationships if rel.characterID_1 == uid]
    card = user_character_svc.create(
        {
            "userCharacterID": uid,
            "userCharacterName": data.userCharacterName,
            "userCharacterInfo": data.userCharacterInfo,
            "defaultRelationships": json.dumps(defaults),
        }
    )
    return ok(dict(card))


@router.get("/api/user-characters/{uid}")
def get_user_character(uid: str):
    card = user_character_svc.get(uid)
    if not card:
        raise HTTPException(404, "用户角色不存在")
    return ok(dict(card))


@router.put("/api/user-characters/{uid}")
def update_user_character(uid: str, data: UserCharacterUpdate):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "没有需要更新的字段")
    if "defaultRelationships" in patch:
        patch["defaultRelationships"] = json.dumps(patch["defaultRelationships"])
    user_character_svc.update(uid, patch)
    return ok(msg="更新成功")


@router.delete("/api/user-characters/{uid}")
def delete_user_character(uid: str):
    user_character_svc.delete_cascade(uid)
    return ok(msg="删除成功")


# ─── User Character Export / Import ──────────────────────────────────


@router.get("/api/user-characters/{uid}/export")
def export_user_character(uid: str):
    card = user_character_svc.get(uid)
    if not card:
        raise HTTPException(404, "用户角色不存在")
    export_data = UserCharacterExportData(
        exported_at=datetime.now().isoformat(),
        characters=[
            UserCharacterExportItem(
                userCharacterName=card["userCharacterName"],
                userCharacterInfo=card.get("userCharacterInfo", ""),
                defaultRelationships=card.get("defaultRelationships", "[]"),
            )
        ],
    )
    safe_name = card["userCharacterName"].replace(" ", "_")
    filename = f"{safe_name}_user_character.json"
    encoded_name = quote(filename, safe="")
    return Response(
        content=export_data.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.post("/api/user-characters/import")
def import_user_characters(data: UserCharacterExportData):
    created = []
    for item in data.characters:
        if not item.userCharacterName:
            continue
        uid = generate_user_character_id(item.userCharacterName)
        card = user_character_svc.create(
            {
                "userCharacterID": uid,
                "userCharacterName": item.userCharacterName,
                "userCharacterInfo": item.userCharacterInfo,
                "defaultRelationships": item.defaultRelationships,
            }
        )
        created.append(dict(card))
    return ok(created)


# ─── Character Relationships ─────────────────────────────────────


@router.post("/api/character-relationships")
def batch_upsert_relationships(data: RelationshipsBatchCreate):
    results = []
    for rel in data.relationships:
        rid = relationship_svc.upsert(rel.model_dump())
        results.append(rid)
    return ok({"created": len(results)})


@router.get("/api/character-relationships/{cid}")
def get_character_relationships(cid: str):
    db = get_db()
    rels = db.fetchall(
        "SELECT cr.*, s.sessionTitle, "
        "COALESCE(c1.characterName, u1.userCharacterName) AS sourceName, "
        "COALESCE(c2.characterName, u2.userCharacterName) AS targetName "
        "FROM character_relationship cr "
        "LEFT JOIN session s ON cr.sessionID = s.sessionID "
        "LEFT JOIN character_info_card c1 ON cr.characterID_1 = c1.characterID "
        "LEFT JOIN user_character_info_card u1 ON cr.characterID_1 = u1.userCharacterID "
        "LEFT JOIN character_info_card c2 ON cr.characterID_2 = c2.characterID "
        "LEFT JOIN user_character_info_card u2 ON cr.characterID_2 = u2.userCharacterID "
        "WHERE cr.characterID_1 = ? OR cr.characterID_2 = ? "
        "ORDER BY cr.sessionID, cr.strength DESC",
        (cid, cid),
    )
    results = [dict(r) for r in rels]

    card = db.fetchone("SELECT defaultRelationships FROM character_info_card WHERE characterID = ?", (cid,))
    if card and card["defaultRelationships"]:
        try:
            defaults = json.loads(card["defaultRelationships"])
        except Exception:
            defaults = []
        for d in defaults:
            other = d["characterID"]
            row = db.fetchone("SELECT characterName FROM character_info_card WHERE characterID = ?", (other,))
            if row:
                other_name = row["characterName"]
            else:
                urow = db.fetchone(
                    "SELECT userCharacterName FROM user_character_info_card WHERE userCharacterID = ?", (other,)
                )
                other_name = urow["userCharacterName"] if urow else other
            results.append(
                {
                    "relationshipID": "",
                    "sessionID": "",
                    "sessionTitle": "默认（全局）",
                    "characterID_1": cid,
                    "characterID_2": other,
                    "sourceName": None,
                    "targetName": other_name,
                    "relationship_type": d.get("relationship_type", "neutral"),
                    "strength": d.get("strength", 0.5),
                    "sentiment": d.get("sentiment", 0.0),
                    "power_dynamic": d.get("power_dynamic", 0.0),
                    "isDefault": True,
                }
            )
    return ok(results)


@router.delete("/api/character-relationships/{cid}")
def delete_character_relationships(cid: str, session_id: str = Query(None)):
    db = get_db()
    if session_id:
        db.execute(
            "DELETE FROM character_relationship WHERE characterID_1 = ? AND sessionID = ?", (cid, session_id)
        )
    else:
        db.execute("DELETE FROM character_relationship WHERE characterID_1 = ? OR characterID_2 = ?", (cid, cid))
        db.execute("UPDATE character_info_card SET defaultRelationships = '[]' WHERE characterID = ?", (cid,))
    return ok(msg="关系已清除")


# ─── Character Emotions ──────────────────────────────────────────


@router.get("/api/characters/{cid}/emotions")
def get_character_emotions(cid: str):
    db = get_db()
    rows = db.fetchall(
        "SELECT DISTINCT ces.sessionID, s.sessionTitle "
        "FROM character_emotion_state ces "
        "JOIN session s ON s.sessionID = ces.sessionID "
        "WHERE ces.characterID = ?",
        (cid,),
    )
    sessions = []
    for row in rows:
        latest = emotion_svc.get_latest(row["sessionID"], cid)
        if latest:
            latest["sessionTitle"] = row["sessionTitle"]
            sessions.append(dict(latest))

    card = character_svc.get(cid)
    initial_emotion = {}
    if card and card.get("initialEmotion"):
        try:
            initial_emotion = json.loads(card["initialEmotion"])
        except Exception:
            pass

    return ok({"initialEmotion": initial_emotion, "sessions": sessions})


@router.put("/api/characters/{cid}/emotions")
def update_character_emotions(cid: str, data: dict):
    session_id = data.get("sessionID", "")
    if not session_id:
        raise HTTPException(400, "sessionID 是必需的")
    emotion_svc.insert(
        {
            "sessionID": session_id,
            "characterID": cid,
            "emotionLabel": data.get("emotionLabel", "平静"),
            "valence": data.get("valence", 0.0),
            "arousal": data.get("arousal", 0.5),
            "intensity": data.get("intensity", 0.0),
            "energy": data.get("energy", 1.0),
            "stress": data.get("stress", 0.0),
            "triggerSummary": data.get("triggerSummary", "手动编辑"),
        }
    )
    return ok(msg="情绪已更新")