from datetime import datetime
import json
import os
import time
import traceback
from typing import Any, Dict, Optional

import paths

LINE = "\u2500" * 50
DOUBLE = "\u2550" * 50


def _size(val: Any) -> str:
    try:
        s = json.dumps(val, ensure_ascii=False, default=str)
    except Exception:
        s = str(val)
    lines = s.count("\n")
    if lines > 0:
        return f"{len(s)} chars, {lines + 1} lines"
    return f"{len(s)} chars"


def _safe(val: Any, max_len: int = 500) -> str:
    try:
        s = json.dumps(val, ensure_ascii=False, default=str)
        return s[:max_len] + ("..." if len(s) > max_len else "")
    except Exception:
        return str(val)[:max_len]


def _summarize_todos(todos: Any) -> str:
    if not todos:
        return "\u2014"
    items = []
    for t in todos if isinstance(todos, list) else [todos]:
        node = t.get("targetNode", "?")
        done = "\u2713" if t.get("isCompleted") else "\u25cb"
        extra = t.get("extraData", "")
        items.append(f"{done} {node}" + (f'="{extra[:30]}"' if extra else ""))
    return " | ".join(items)


class GraphLogger:
    _instance: Optional["GraphLogger"] = None

    def __init__(self, log_dir: Optional[str] = None):
        # 缺省锚定项目根 logs/（显式传入的相对/绝对路径原样生效）
        if log_dir is None:
            log_dir = str(paths.LOGS_DIR)
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"graph_{datetime.now():%Y%m%d_%H%M%S}.log")
        self._timings: Dict[str, float] = {}

    @classmethod
    def get(cls) -> "GraphLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _write(self, msg: str):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")

    def _write_state(self, state: Dict[str, Any], compact: bool = False):
        s = state.get("sessionID", "")[:16]
        h = len(state.get("sessionHistory", []))
        p = state.get("sessionPresentCharacter", [])
        self._write(f"  session: {s}  history: {h} msgs  chars: {len(p)}")

        if compact:
            return

        self._write(f"  presentChars: {p}")
        self._write(f"  departedChars: {state.get('sessionDepartedCharacter', [])}")
        self._write(f"  userChar: {state.get('sessionUserCharacterID', '')}")
        self._write(f"  wvcID: {state.get('sessionWorldviewCollectionID', '')}")
        env = state.get("sessionEnvData", {})
        if isinstance(env, dict):
            self._write(f"  env: {env.get('location', '')} / {env.get('time', '')} / {env.get('atmosphere', '')}")
        self._write(
            f"  outline: {len(state.get('outline', []))} entries  memCounter: {state.get('memoryRoundCounter', 0)}"
        )
        self._write(f"  directorTODO: {_summarize_todos(state.get('directorToDoList', []))}")
        self._write(f"  supervisorTODO: {_summarize_todos(state.get('supervisorToDoList', []))}")
        dt = state.get("directorCurrentTask") or state.get("supervisorCurrentTask")
        if dt:
            self._write(f"  currentTask: {_safe(dt)}")

    def log_input(self, state: Dict[str, Any]):
        self._write(f"\n{DOUBLE}")
        self._write("GRAPH INPUT")
        self._write(LINE)
        self._write_state(state)

    def log_output(self, state: Dict[str, Any]):
        self._write(LINE)
        self._write("GRAPH RESULT")
        dout = state.get("directorGraphOutput", [])
        if dout:
            self._write(f"  directorOutput: {len(dout)} entries  {_size(dout)}")
        self._write(f"  directorTODO:   {_summarize_todos(state.get('directorToDoList', []))}")
        self._write(f"  supervisorTODO: {_summarize_todos(state.get('supervisorToDoList', []))}")
        self._write(f"  memCounter:     {state.get('memoryRoundCounter', 0)}")
        self._write(DOUBLE + "\n")

    def node_start(self, name: str, state: Dict[str, Any]):
        self._timings[name] = time.time()
        self._write(f"\n{DOUBLE}")
        self._write(f"\u25b6 {name}  START")
        self._write(LINE)
        self._write_state(state, compact=True)
        self._write(LINE)

    def node_end(self, name: str, outputs: Dict[str, Any]):
        elapsed = time.time() - self._timings.pop(name, time.time())
        summary = {k: v for k, v in outputs.items() if k not in ("sessionHistory",)}
        self._write(f"  OUTPUT  {_safe(summary)}")
        self._write(LINE)
        self._write(f"\u25c0 {name}  END  (duration: {elapsed:.2f}s)")
        self._write(DOUBLE)

    def node_error(self, name: str):
        tb = traceback.format_exc().strip()
        lines = tb.split("\n")
        msg = lines[-1] if lines else "unknown error"
        self._write(f"  \u2717 ERROR: {msg}")
        for line in lines:
            self._write(f"    {line}")

    def log_llm(self, node_name: str, response: str, params: dict = None):
        body = response if isinstance(response, str) else str(response)
        self._write(f"\n  \u2500\u2500 PROMPT \u2500\u2500 [{node_name}]")
        if params:
            self._write(
                f"  \u2500\u2500 PARAMS temperature={params.get('temperature')}  max_tokens={params.get('max_tokens')}  thinking={params.get('is_enable_thinking')}"
            )
        self._write(f"  \u2500\u2500 RESPONSE ({_size(body)}) \u2500\u2500")
        try:
            parsed = json.loads(body)
            body = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            pass
        for line in body.splitlines():
            self._write(f"  {line}")

    def log_llm_error(self, node_name: str, detail: str = ""):
        self._write(f"  \u2717 LLM ERROR [{node_name}]")
        if detail:
            summary = " ".join(str(detail).split())
            if len(summary) > 500:
                summary = summary[:500] + "…"
            self._write(f"    {summary}")

    def log_sse(self, event: str, data: Any):
        self._write(f"  \u2192 SSE [{event}] {_size(data)}")


logger = GraphLogger.get()
