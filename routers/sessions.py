"""Sessions and session-history endpoints.

/ 会话与会话历史相关端点。
"""

from datetime import datetime
import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ChromaDBClient import get_chroma
from models import (
    CharacterExportItemInSession,
    EmotionExportItem,
    HistoryExportItem,
    MemoryExportItem,
    RelationshipExportItem,
    SessionCreate,
    SessionExportData,
    SessionExportItem,
    SessionHistoryCreate,
    SessionUpdate,
    UserCharacterExportItemInSession,
    WorldviewExportCollectionInSession,
    WorldviewExportEntry,
)
from routers.deps import (
    character_svc,
    emotion_svc,
    history_svc,
    ok,
    relationship_svc,
    session_svc,
    user_character_svc,
    wvc_svc,
    wve_svc,
)
from services.emotion import seed_initial_emotion, seed_initial_emotions
from services.id_utils import (
    generate_character_id,
    generate_history_id,
    generate_memory_id,
    generate_session_id,
    generate_user_character_id,
    generate_wvc_id,
    generate_wve_id,
    now,
)
from SQLiteClient import get_db

router = APIRouter()


# ─── Sessions ──────────────────────────────────────────────────


@router.get("/api/sessions")
def list_sessions(
    page: int | None = None,
    page_size: int = 10,
    keyword: str | None = None,
):
    if page is None:
        return ok([dict(r) for r in session_svc.list_all()])
    total, rows = session_svc.list_page(page, page_size, keyword or None)
    return ok(
        {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/api/sessions")
def create_session(data: SessionCreate):
    sid = generate_session_id()
    session = session_svc.create(
        {
            "sessionID": sid,
            "sessionTitle": data.sessionTitle,
            "worldviewCollectionID": data.worldviewCollectionID,
            "userCharacterID": data.userCharacterID,
            "sessionEnvData": data.sessionEnvData,
            "sessionPresentCharacter": data.sessionPresentCharacter,
        }
    )

    all_char_ids = list(set(data.sessionPresentCharacter))
    if data.userCharacterID:
        all_char_ids.append(data.userCharacterID)

    custom_rels = {}
    for rel in data.initialRelationships:
        custom_rels[(rel.characterID_1, rel.characterID_2)] = rel

    def _build_rel(from_cid, to_cid):
        custom = custom_rels.get((from_cid, to_cid))
        if custom:
            d = custom.model_dump()
            d.pop("sessionID", None)
        else:
            d = {"relationship_type": "neutral", "strength": 0.5, "sentiment": 0.0, "power_dynamic": 0.0}
        d["sessionID"] = sid
        d["characterID_1"] = from_cid
        d["characterID_2"] = to_cid
        return d

    for i in range(len(all_char_ids)):
        for j in range(i + 1, len(all_char_ids)):
            a, b = all_char_ids[i], all_char_ids[j]
            relationship_svc.upsert(_build_rel(a, b))
            relationship_svc.upsert(_build_rel(b, a))

    # Seed each character's initial emotion from its card (de-duplicated helper).
    # / 用去重后的辅助函数为每个角色写入初始情绪。
    seed_initial_emotions(emotion_svc, get_db(), sid, all_char_ids, trigger_summary="会话开始")

    return ok({"session": dict(session)})


@router.get("/api/sessions/{sid}")
def get_session(sid: str):
    session = session_svc.get(sid)
    if not session:
        raise HTTPException(404, "会话不存在")
    return ok(dict(session))


@router.put("/api/sessions/{sid}")
def update_session(sid: str, data: SessionUpdate):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "没有需要更新的字段")
    session_svc.update(sid, patch)
    return ok(msg="更新成功")


@router.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    session_svc.delete_cascade(sid)
    try:
        for col in get_chroma().list_collections():
            if col.name.startswith(f"session_{sid}_"):
                get_chroma().delete_collection(col.name)
    except Exception:
        pass
    return ok(msg="删除成功")


# ─── Session Export / Import ──────────────────────────────────────


def _default_rels_to_names(rels_json, char_id_to_name):
    try:
        rels = json.loads(rels_json) if isinstance(rels_json, str) else rels_json
        for rel in rels:
            if "characterID" in rel:
                oid = rel.pop("characterID")
                rel["characterName"] = char_id_to_name.get(oid, oid)
        return json.dumps(rels, ensure_ascii=False)
    except Exception:
        return rels_json if isinstance(rels_json, str) else json.dumps(rels_json, ensure_ascii=False)


def _char_id_to_name(db, cids):
    m = {}
    for cid in cids:
        row = db.fetchone("SELECT characterName FROM character_info_card WHERE characterID = ?", (cid,))
        if row:
            m[cid] = row["characterName"]
    return m


@router.get("/api/sessions/{sid}/export")
def export_session(sid: str):
    session = session_svc.get(sid)
    if not session:
        raise HTTPException(404, "会话不存在")

    db = get_db()
    wvc_export = None
    uc_export = None
    char_export_items = []
    history_export_items = []
    rel_export_items = []
    emotion_export_items = []
    memory_export_items = []

    # worldview
    wvc_id = session.get("worldviewCollectionID") or ""
    if wvc_id:
        wvc = wvc_svc.get(wvc_id)
        if wvc:
            entries = wve_svc.list_by_collection(wvc_id)
            wvc_export = WorldviewExportCollectionInSession(
                worldviewCollectionName=wvc["worldviewCollectionName"],
                worldviewDescription=wvc.get("worldviewDescription", ""),
                entries=[
                    WorldviewExportEntry(
                        worldviewCollectionEntryContent=e["worldviewCollectionEntryContent"],
                        isPermanent=bool(e.get("isPermanent", False)),
                    )
                    for e in entries
                ],
            )

    # user character
    uc_id = session.get("userCharacterID") or ""
    if uc_id:
        uc = user_character_svc.get(uc_id)
        if uc:
            uc_export = UserCharacterExportItemInSession(
                userCharacterName=uc["userCharacterName"],
                userCharacterInfo=uc.get("userCharacterInfo", ""),
                defaultRelationships=uc.get("defaultRelationships", "[]"),
            )

    # collect character IDs from the session roster
    all_char_ids = set()
    for cid in session.get("sessionPresentCharacter", []):
        if cid:
            all_char_ids.add(cid)
    for cid in session.get("sessionDepartedCharacter", []):
        if cid:
            all_char_ids.add(cid)

    # character cards
    char_id_to_name = _char_id_to_name(db, all_char_ids)
    for cid in all_char_ids:
        card = character_svc.get(cid)
        if not card:
            continue
        name = card["characterName"]
        char_id_to_name[cid] = name
        default_rels = card.get("defaultRelationships", "[]")
        char_export_items.append(
            CharacterExportItemInSession(
                characterName=name,
                characterInfo=card.get("characterInfo", ""),
                defaultRelationships=_default_rels_to_names(default_rels, char_id_to_name),
                initialEmotion=card.get("initialEmotion", "{}"),
            )
        )

    # session history (now with char_id_to_name ready)
    history_rows = history_svc.list_by_session(sid)
    for h in history_rows:
        role = h["role"]
        if h["createdBy"] == "actor":
            role = char_id_to_name.get(role, role)
        history_export_items.append(
            HistoryExportItem(
                role=role,
                createdBy=h["createdBy"],
                content=h["content"],
            )
        )

    # relationships
    rel_rows = db.fetchall("SELECT * FROM character_relationship WHERE sessionID = ?", (sid,))
    for r in rel_rows:
        from_name = char_id_to_name.get(r["characterID_1"], r["characterID_1"])
        to_name = char_id_to_name.get(r["characterID_2"], r["characterID_2"])
        rel_export_items.append(
            RelationshipExportItem(
                fromName=from_name,
                toName=to_name,
                relationship_type=r.get("relationship_type", "neutral"),
                strength=r.get("strength", 0.5),
                sentiment=r.get("sentiment", 0.0),
                power_dynamic=r.get("power_dynamic", 0.0),
            )
        )

    # emotion states
    emo_rows = db.fetchall("SELECT * FROM character_emotion_state WHERE sessionID = ?", (sid,))
    for e in emo_rows:
        cname = char_id_to_name.get(e["characterID"], e["characterID"])
        emotion_export_items.append(
            EmotionExportItem(
                characterName=cname,
                emotionLabel=e.get("emotionLabel", "平静"),
                valence=e.get("valence", 0.0),
                arousal=e.get("arousal", 0.5),
                intensity=e.get("intensity", 0.0),
                energy=e.get("energy", 1.0),
                stress=e.get("stress", 0.0),
                triggerSummary=e.get("triggerSummary", ""),
            )
        )

    # memories
    mem_rows = db.fetchall("SELECT * FROM memory WHERE sessionID = ?", (sid,))
    for m in mem_rows:
        cname = char_id_to_name.get(m["characterID"], m["characterID"])
        memory_export_items.append(
            MemoryExportItem(
                characterName=cname,
                content=m["content"],
            )
        )

    export_data = SessionExportData(
        exported_at=datetime.now().isoformat(),
        session=SessionExportItem(
            sessionTitle=session["sessionTitle"],
            status=session.get("status") or "active",
            sessionPresentCharacter=[
                char_id_to_name.get(cid, cid) for cid in session.get("sessionPresentCharacter", [])
            ],
            sessionDepartedCharacter=[
                char_id_to_name.get(cid, cid) for cid in session.get("sessionDepartedCharacter", [])
            ],
            sessionEnvData=session.get("sessionEnvData") or {},
            memoryRoundCounter=session.get("memoryRoundCounter") or 0,
            outline=session.get("outline") or [],
        ),
        worldviewCollection=wvc_export,
        userCharacter=uc_export,
        characters=char_export_items,
        history=history_export_items,
        relationships=rel_export_items,
        emotionStates=emotion_export_items,
        memories=memory_export_items,
    )

    safe_name = session["sessionTitle"].replace(" ", "_")
    filename = f"{safe_name}_session.json"
    encoded_name = quote(filename, safe="")
    return Response(
        content=export_data.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


def _default_rels_to_ids(rels_json, name_to_id):
    try:
        rels = json.loads(rels_json) if isinstance(rels_json, str) else rels_json
        for rel in rels:
            if "characterName" in rel:
                name = rel.pop("characterName")
                rel["characterID"] = name_to_id.get(name, name)
        return json.dumps(rels, ensure_ascii=False)
    except Exception:
        return rels_json if isinstance(rels_json, str) else json.dumps(rels_json, ensure_ascii=False)


@router.post("/api/sessions/import")
def import_session(data: SessionExportData):
    if not data.session.sessionTitle:
        raise HTTPException(400, "会话标题不能为空")

    db = get_db()
    new_session_id = generate_session_id()
    name_to_id = {}

    db.begin()
    try:
        # 1. worldview collection
        if data.worldviewCollection:
            wvc = data.worldviewCollection
            new_wvc_id = generate_wvc_id(wvc.worldviewCollectionName)
            wvc_svc.create(
                {
                    "worldviewCollectionID": new_wvc_id,
                    "worldviewCollectionName": wvc.worldviewCollectionName,
                    "worldviewDescription": wvc.worldviewDescription,
                }
            )
            for entry in wvc.entries:
                wve_svc.create(
                    {
                        "worldviewCollectionEntryID": generate_wve_id(),
                        "parentID": new_wvc_id,
                        "worldviewCollectionEntryContent": entry.worldviewCollectionEntryContent,
                        "isPermanent": 1 if entry.isPermanent else 0,
                    }
                )

        # 2. user character
        new_uc_id = ""
        if data.userCharacter:
            new_uc_id = generate_user_character_id(data.userCharacter.userCharacterName)
            name_to_id[data.userCharacter.userCharacterName] = new_uc_id
            user_character_svc.create(
                {
                    "userCharacterID": new_uc_id,
                    "userCharacterName": data.userCharacter.userCharacterName,
                    "userCharacterInfo": data.userCharacter.userCharacterInfo,
                    "defaultRelationships": data.userCharacter.defaultRelationships,
                }
            )

        # 3. NPC characters
        for c in data.characters:
            new_cid = generate_character_id(c.characterName)
            name_to_id[c.characterName] = new_cid
            character_svc.create(
                {
                    "characterID": new_cid,
                    "characterName": c.characterName,
                    "characterInfo": c.characterInfo,
                    "defaultRelationships": c.defaultRelationships,
                    "initialEmotion": c.initialEmotion,
                }
            )

        # 4. remap defaultRelationships on all characters (name → ID)
        if data.userCharacter:
            updated_uc = _default_rels_to_ids(data.userCharacter.defaultRelationships, name_to_id)
            user_character_svc.update(new_uc_id, {"defaultRelationships": updated_uc})
        for c in data.characters:
            new_cid = name_to_id[c.characterName]
            updated_rels = _default_rels_to_ids(c.defaultRelationships, name_to_id)
            character_svc.update(new_cid, {"defaultRelationships": updated_rels})

        # 5. session
        session_svc.create(
            {
                "sessionID": new_session_id,
                "sessionTitle": data.session.sessionTitle,
                "status": data.session.status,
                "sessionPresentCharacter": [
                    name_to_id.get(n, n) for n in data.session.sessionPresentCharacter
                ],
                "sessionDepartedCharacter": [
                    name_to_id.get(n, n) for n in data.session.sessionDepartedCharacter
                ],
                "sessionEnvData": data.session.sessionEnvData,
                "memoryRoundCounter": data.session.memoryRoundCounter,
                "outline": data.session.outline,
                "worldviewCollectionID": new_wvc_id if data.worldviewCollection else "",
                "userCharacterID": new_uc_id,
            }
        )

        # 6. session history
        for h in data.history:
            role = h.role
            if h.createdBy == "actor":
                role = name_to_id.get(role, role)
            history_svc.create(
                {
                    "sessionHistoryID": generate_history_id(),
                    "parentID": new_session_id,
                    "role": role,
                    "createdBy": h.createdBy,
                    "content": h.content,
                }
            )

        # 7. relationships
        for r in data.relationships:
            cid1 = name_to_id.get(r.fromName, r.fromName)
            cid2 = name_to_id.get(r.toName, r.toName)
            relationship_svc.upsert(
                {
                    "sessionID": new_session_id,
                    "characterID_1": cid1,
                    "characterID_2": cid2,
                    "relationship_type": r.relationship_type,
                    "strength": r.strength,
                    "sentiment": r.sentiment,
                    "power_dynamic": r.power_dynamic,
                }
            )

        # 8. emotion states
        for e in data.emotionStates:
            cid = name_to_id.get(e.characterName, e.characterName)
            seed_initial_emotion(
                emotion_svc,
                db,
                new_session_id,
                cid,
                trigger_summary="会话导入",
            )

        # 9. memories
        for m in data.memories:
            cid = name_to_id.get(m.characterName, m.characterName)
            now_ts = now()
            db.execute(
                "INSERT INTO memory (memoryID, sessionID, characterID, content, recordCreatedTime, recordUpdatedTime) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (generate_memory_id(), new_session_id, cid, m.content, now_ts, now_ts),
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return ok(
        {
            "sessionID": new_session_id,
        }
    )


# ─── Session History ──────────────────────────────────────


@router.get("/api/sessions/{sid}/history")
def list_session_history(sid: str):
    return ok([dict(r) for r in history_svc.list_by_session(sid)])


@router.delete("/api/sessions/{sid}/history")
def clear_session_history(sid: str):
    history_svc.delete_by_session(sid)
    return ok(msg="对话已清空")


@router.delete("/api/session-history/{history_id}")
def delete_session_history(history_id: str):
    history_svc.delete(history_id)
    return ok(msg="已删除")


@router.post("/api/session-history")
def create_session_history(data: SessionHistoryCreate):
    hid = generate_history_id()
    record = history_svc.create(
        {
            "sessionHistoryID": hid,
            "parentID": data.parentID,
            "role": data.role,
            "createdBy": data.createdBy,
            "content": data.content,
        }
    )
    return ok(dict(record))