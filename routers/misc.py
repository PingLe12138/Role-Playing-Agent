"""Utility endpoints: clear-all and log streaming/viewing.

/ 实用端点：清空数据、日志流与查看。
"""

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ChromaDBClient import get_chroma
from routers.deps import db, ok

router = APIRouter()

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
LOG_DIR = os.path.normpath(LOG_DIR)


def _delete_all_rows(db_client, tables: list[str]) -> None:
    """Wipe every row from `tables` with FK enforcement temporarily off, then
    restore the connection's PREVIOUS `foreign_keys` setting.

    `PRAGMA foreign_keys` is a per-connection switch and `db` is the process-wide
    shared connection, so hard-coding it back to ON leaks FK enforcement into every
    later request of the same process. That breaks normal usage: relationship and
    emotion rows are legitimately written for the *user* character (`create_session`,
    `update_relationship_node`), whose ID lives in `user_character_info_card` while
    those FKs point at `character_info_card` — with enforcement on, creating a
    session raises `FOREIGN KEY constraint failed`.
    / `PRAGMA foreign_keys` 是连接级开关，而 `db` 是进程内共享连接：清空后写死为 ON
      会把外键校验泄漏给本进程后续所有请求。用户角色的关系/情绪行（create_session、
      update_relationship_node 都会写）外键指向 character_info_card，一旦开启校验，
      建会话就会抛 FOREIGN KEY constraint failed。故此处恢复原值而非写死 ON。
    """
    prev = db_client.fetchone("PRAGMA foreign_keys") or {}
    fk_was_on = bool(prev.get("foreign_keys", 0))
    db_client.execute("PRAGMA foreign_keys = OFF")
    try:
        for t in tables:
            db_client.execute(f"DELETE FROM {t}")
    finally:
        db_client.execute("PRAGMA foreign_keys = ON" if fk_was_on else "PRAGMA foreign_keys = OFF")


@router.post("/api/clear-all")
def clear_all():
    tables = [
        "session_history",
        "session",
        "memory",
        "worldview_entry",
        "worldview_collection",
        "user_character_info_card",
        "character_info_card",
    ]
    _delete_all_rows(db, tables)
    try:
        for col in get_chroma().list_collections():
            get_chroma().delete_collection(col.name)
    except Exception:
        pass
    return ok(msg="所有数据已清除")


@router.get("/api/logs")
def list_logs():
    if not os.path.isdir(LOG_DIR):
        return ok([])
    files = []
    for f in os.listdir(LOG_DIR):
        if f.startswith("graph_") and f.endswith(".log"):
            path = os.path.join(LOG_DIR, f)
            stat = os.stat(path)
            files.append({"name": f, "size": stat.st_size, "mtime": stat.st_mtime})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return ok(files)


@router.get("/api/logs/stream")
async def stream_log(filename: str | None = Query(default=None)):
    async def event_generator():
        nonlocal filename
        if not filename:
            if not os.path.isdir(LOG_DIR):
                yield "event: no_file\ndata: {}\n\n"
                return
            files = sorted(
                [f for f in os.listdir(LOG_DIR) if f.startswith("graph_") and f.endswith(".log")], reverse=True
            )
            if not files:
                yield "event: no_file\ndata: {}\n\n"
                return
            filename = files[0]

        path = os.path.join(LOG_DIR, filename)
        last_size = os.path.getsize(path) if os.path.isfile(path) else 0

        try:
            while True:
                if os.path.isfile(path):
                    current_size = os.path.getsize(path)
                    if current_size > last_size:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_size)
                            new_content = f.read()
                            if new_content:
                                yield f"event: append\ndata: {json.dumps({'content': new_content})}\n\n"
                        last_size = current_size
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/logs/{filename}")
def get_log_content(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "非法的文件名")
    path = os.path.join(LOG_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, "日志文件不存在")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return ok({"name": filename, "content": content})