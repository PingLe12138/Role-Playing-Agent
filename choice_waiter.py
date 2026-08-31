"""Shared module for blocking/resuming the graph when a player choice is pending.

Usage:
  - player_choice_node calls `wait_for_choice(session_id)` which blocks
    until the player submits a choice via the API endpoint.
  - The API endpoint calls `submit_choice(session_id, text)` to wake
    the waiting thread.

The waiter is keyed by session_id. Cleanup happens automatically
after the choice is submitted (or after a timeout).
"""

import threading
import time

# Dict keyed by session_id
# Value: {"event": threading.Event, "response": str | None, "created": float}
_waiter_registry: dict[str, dict] = {}
_registry_lock = threading.Lock()

TIMEOUT_SECONDS = 86400  # 24 hours (effectively "no timeout" while still
# guaranteeing a stuck worker thread is eventually released; a player choice
# is meant to wait indefinitely until the player responds or cancels)

CANCEL_SENTINEL = "__CANCEL__"


def register_waiter(key: str) -> dict:
    """Register a new waiter for the given key.
    / 为给定的键注册一个新的等待器。

    The caller (player_choice_node) will later block on waiter["event"].wait().
    The API endpoint unblocks it by calling submit_choice() or cancel_choice()
    which set the event and store the response.
    / 调用者（player_choice_node）之后会阻塞在 waiter["event"].wait() 上。
      前端 API 端点通过 submit_choice() 或 cancel_choice() 设置事件并存储响应以解除阻塞。
    """
    with _registry_lock:
        waiter = {"event": threading.Event(), "response": None, "created": time.time()}
        _waiter_registry[key] = waiter
        return waiter


def unregister_waiter(key: str) -> None:
    """Remove a waiter from the registry after the wait completes (or times out).
    / 等待完成（或超时）后从注册表中移除等待器。

    Called automatically in the finally block of wait_for_choice().  The
    API endpoints (submit_choice / cancel_choice) use the absence of a
    waiter as a signal that the graph is no longer waiting (→ fallback path).
    / 由 wait_for_choice() 的 finally 块自动调用。API 端点（submit_choice /
      cancel_choice）通过等待器不存在来判断图已不再等待（→ 回退路径）。
    """
    with _registry_lock:
        _waiter_registry.pop(key, None)


def wait_for_choice(session_id: str) -> str | None:
    """Block until the player submits a choice, or timeout.

    Returns the choice text, or None on timeout.
    """
    key = session_id
    waiter = register_waiter(key)
    try:
        signaled = waiter["event"].wait(TIMEOUT_SECONDS)
        if signaled:
            return waiter.get("response")
        return None  # timeout
    finally:
        unregister_waiter(key)


def cancel_choice(session_id: str) -> bool:
    """Signal the waiting thread that the player cancelled the choice.

    Returns True if a waiter was found and signaled, False otherwise.
    """
    key = session_id
    with _registry_lock:
        waiter = _waiter_registry.get(key)
    if waiter is None:
        return False
    waiter["response"] = CANCEL_SENTINEL
    waiter["event"].set()
    return True


def submit_choice(session_id: str, choice_text: str) -> bool:
    """Signal the waiting thread with the player's choice.

    Returns True if a waiter was found and signaled, False otherwise.
    """
    key = session_id
    with _registry_lock:
        waiter = _waiter_registry.get(key)
    if waiter is None:
        return False
    waiter["response"] = choice_text
    waiter["event"].set()
    return True
