"""SSE (Server-Sent Events) event dispatcher for real-time frontend updates.
/ SSE（服务器推送事件）分发器，用于向前端实时推送更新。

Published event types (see AGENTS.md for the full reference):
/ 发布的事件类型（完整参考见 AGENTS.md）：
  node_start / node_complete  — lifecycle events for graph nodes / 图节点的生命周期事件
  message                     — new AI / narration / system messages / 新的 AI、旁白、系统消息
  player_choice               — a player-choice panel needs to be shown / 需要显示玩家选择面板
  session_update              — env data / character list changes / 环境数据或角色列表变化
  graph_complete / graph_error — graph run finished / failed / 图执行完成 / 失败
  history_update               — full session history for refresh / 全量历史记录用于刷新
  ping                         — keepalive heartbeat every 5 seconds / 每 5 秒的心跳保活
"""

import asyncio
import json
import threading
from typing import Any, AsyncGenerator


class SSEPublisher:
    def __init__(self):
        self._subscribers: dict[int, asyncio.Queue] = {}
        self._lock = threading.Lock()
        self._counter = 0
        self._loop = None

    def publish(self, event: str, data: Any) -> None:
        from graph_logger import logger

        logger.log_sse(event, data)
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._dispatch, payload)
        else:
            self._dispatch(payload)

    def _dispatch(self, payload: str) -> None:
        dead = []
        with self._lock:
            for sid, q in list(self._subscribers.items()):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(sid)
            for sid in dead:
                self._subscribers.pop(sid, None)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._counter += 1
            sid = self._counter
            self._subscribers[sid] = q
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield payload
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            with self._lock:
                self._subscribers.pop(sid, None)


publisher = SSEPublisher()
