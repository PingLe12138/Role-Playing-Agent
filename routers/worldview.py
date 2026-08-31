"""Worldview collections and entries endpoints.

/ 世界观集合与条目相关端点。
"""

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ChromaDBClient import get_chroma
from models import (
    WorldviewCollectionCreate,
    WorldviewCollectionUpdate,
    WorldviewEntryCreate,
    WorldviewEntryUpdate,
    WorldviewExportCollection,
    WorldviewExportData,
    WorldviewExportEntry,
)
from routers.deps import ok, wvc_svc, wve_svc
from services.id_utils import generate_wvc_id, generate_wve_id

router = APIRouter()


# ─── Worldview Collections ──────────────────────────────────────


@router.get("/api/worldview-collections")
def list_worldview_collections():
    return ok([dict(r) for r in wvc_svc.list_all()])


@router.post("/api/worldview-collections")
def create_worldview_collection(data: WorldviewCollectionCreate):
    wid = generate_wvc_id(data.worldviewCollectionName)
    wvc = wvc_svc.create(
        {
            "worldviewCollectionID": wid,
            "worldviewCollectionName": data.worldviewCollectionName,
            "worldviewDescription": data.worldviewDescription,
        }
    )
    return ok(dict(wvc))


@router.get("/api/worldview-collections/{wid}")
def get_worldview_collection(wid: str):
    wvc = wvc_svc.get(wid)
    if not wvc:
        raise HTTPException(404, "世界观集合不存在")
    return ok(dict(wvc))


@router.put("/api/worldview-collections/{wid}")
def update_worldview_collection(wid: str, data: WorldviewCollectionUpdate):
    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "没有需要更新的字段")
    wvc_svc.update(wid, patch)
    return ok(msg="更新成功")


@router.delete("/api/worldview-collections/{wid}")
def delete_worldview_collection(wid: str):
    wvc_svc.delete_cascade(wid)
    try:
        for col in get_chroma().list_collections():
            if col.name.endswith(f"_worldviewentry_{wid}"):
                get_chroma().delete_collection(col.name)
    except Exception:
        pass
    return ok(msg="删除成功")


# ─── Export / Import ─────────────────────────────────────────────


@router.get("/api/worldview-collections/{wid}/export")
def export_worldview_collection(wid: str):
    wvc = wvc_svc.get(wid)
    if not wvc:
        raise HTTPException(404, "世界观集合不存在")
    entries = wve_svc.list_by_collection(wid)
    export_data = WorldviewExportData(
        exported_at=datetime.now().isoformat(),
        collection=WorldviewExportCollection(
            worldviewCollectionName=wvc["worldviewCollectionName"],
            worldviewDescription=wvc["worldviewDescription"],
        ),
        entries=[
            WorldviewExportEntry(
                worldviewCollectionEntryContent=e["worldviewCollectionEntryContent"],
                isPermanent=bool(e.get("isPermanent", False)),
            )
            for e in entries
        ],
    )
    safe_name = wvc["worldviewCollectionName"].replace(" ", "_")
    filename = f"{safe_name}_worldview.json"
    encoded_name = quote(filename, safe="")
    return Response(
        content=export_data.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.post("/api/worldview-collections/import")
def import_worldview_collection(data: WorldviewExportData):
    if not data.collection.worldviewCollectionName:
        raise HTTPException(400, "世界观名称不能为空")
    new_id = generate_wvc_id(data.collection.worldviewCollectionName)
    new_col = wvc_svc.create(
        {
            "worldviewCollectionID": new_id,
            "worldviewCollectionName": data.collection.worldviewCollectionName,
            "worldviewDescription": data.collection.worldviewDescription,
        }
    )
    for entry in data.entries:
        wve_svc.create(
            {
                "worldviewCollectionEntryID": generate_wve_id(),
                "parentID": new_id,
                "worldviewCollectionEntryContent": entry.worldviewCollectionEntryContent,
                "isPermanent": 1 if entry.isPermanent else 0,
            }
        )
    return ok(dict(new_col))


# ─── Worldview Entries ──────────────────────────────────────────


@router.get("/api/worldview-entries")
def list_worldview_entries(collection_id: str | None = Query(default=None)):
    if collection_id:
        return ok([dict(r) for r in wve_svc.list_by_collection(collection_id)])
    return ok([dict(r) for r in wve_svc.list_all()])


@router.post("/api/worldview-entries")
def create_worldview_entry(data: WorldviewEntryCreate):
    eid = generate_wve_id()
    entry = wve_svc.create(
        {
            "worldviewCollectionEntryID": eid,
            "parentID": data.parentID,
            "worldviewCollectionEntryContent": data.worldviewCollectionEntryContent,
            "isPermanent": 1 if data.isPermanent else 0,
        }
    )
    return ok(dict(entry))


@router.get("/api/worldview-entries/{eid}")
def get_worldview_entry(eid: str):
    entry = wve_svc.get(eid)
    if not entry:
        raise HTTPException(404, "世界观条目不存在")
    return ok(dict(entry))


@router.put("/api/worldview-entries/{eid}")
def update_worldview_entry(eid: str, data: WorldviewEntryUpdate):
    patch = {}
    if data.worldviewCollectionEntryContent is not None:
        patch["worldviewCollectionEntryContent"] = data.worldviewCollectionEntryContent
    if data.isPermanent is not None:
        patch["isPermanent"] = 1 if data.isPermanent else 0
    if not patch:
        raise HTTPException(400, "没有需要更新的字段")
    wve_svc.update(eid, patch)
    return ok(msg="更新成功")


@router.delete("/api/worldview-entries/{eid}")
def delete_worldview_entry(eid: str):
    wve_svc.delete_cascade(eid)
    return ok(msg="删除成功")


@router.get("/api/worldview-entries/by-collection/{parent_id}")
def list_worldview_entries_by_collection(parent_id: str):
    return ok([dict(r) for r in wve_svc.list_by_collection(parent_id)])