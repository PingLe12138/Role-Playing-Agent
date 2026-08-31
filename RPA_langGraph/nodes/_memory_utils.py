"""Shared helper for generating and persisting a single character's memory.

Used by `memory_node` (periodic summarization for every present character) and
by `review_departure_node` (departure snapshot for a single character).  Keeping
the logic in one place avoids drift between the two implementations and fixes
a latent bug where the departure path used to omit the `{emotion_state}` field
of `MEMORY_PROMPT`, raising `KeyError` and silently aborting departure memories.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.prompts import MEMORY_PROMPT
from services.formatters import fmt_emotion_state
from SQLiteClient import SQLiteClient, db_lock

MAX_MEMORY_WORKERS = 4


def generate_character_memories_parallel(
    db: SQLiteClient,
    session_id: str,
    character_ids: List[str],
    history_text: str,
    *,
    params: Optional[dict] = None,
    log_label: str = "memory_node",
    prompt_template: Optional[str] = None,
    max_workers: int = MAX_MEMORY_WORKERS,
    context_state: Optional[dict] = None,
    llm_node: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Generate first-person memories for many characters with parallel LLM calls.

    / 并行 LLM 调用为多个角色生成第一人称记忆。

    Phase 1+2: per-character DB reads (serialized under `db_lock`) and LLM calls
    (fully parallel — they dominate latency).  Phase 3 (DB writes / Chroma adds)
    is intentionally NOT done here: callers persist the returned `{cid: content}`
    map themselves inside their own transaction under `db_lock`, preserving the
    existing atomicity semantics.
    / 阶段 1+2：按角色串行读 DB（db_lock 保护）+ 并行 LLM 调用（耗时主体）。
      阶段 3（DB 写 / Chroma 追加）不在此处执行：调用方在各自的事务内、
      db_lock 保护下自行持久化返回的 `{cid: content}` 映射，保持原有原子性语义。

    A failed LLM call yields `None` for that character without aborting the rest
    (matching the original per-character try/except semantics).
    / 单个角色 LLM 失败仅得 None，不影响其余角色（与原逐角色 try/except 语义一致）。

    `llm_node` picks which node's `node_llm` override supplies the client; it
    defaults to `log_label` (the departure path passes "review_departure_node"
    so it does not inherit the memory node's API settings).
    / llm_node 决定用哪个节点的 node_llm 覆盖来获取客户端，默认取 log_label
      （离场路径传 "review_departure_node"，避免继承记忆节点的 API 设置）。
    """
    if not character_ids:
        return {}

    if prompt_template:
        template = prompt_template
    elif log_label == "memory_node":
        template = MEMORY_PROMPT  # override lookup happens inside build_node_prompt
    else:
        template = MEMORY_PROMPT
    call_params = params if params is not None else get_node_params().get(log_label, {})
    llm = get_llm(llm_node or log_label)

    def _one(character_id: str):
        try:
            with db_lock:
                existing = db.fetchall(
                    "SELECT content FROM memory WHERE sessionID = ? AND characterID = ?",
                    (session_id, character_id),
                )
                card_row = db.fetchone("SELECT * FROM character_info_card WHERE characterID = ?", (character_id,))
                emotion_state = fmt_emotion_state(db, session_id, character_id)
            existing_text = "\n".join(r["content"] for r in existing)
            card_text = (
                f"名称: {card_row.get('characterName', '')}\n信息: {card_row.get('characterInfo', '无')}"
                if card_row
                else "无"
            )
            prompt = build_node_prompt(
                "memory_node",
                template,
                respect_override=(log_label == "memory_node"),
                context_state=context_state,
                context_extra={"character_id": character_id},
                character_card=card_text,
                existing_memories=existing_text or "(无)",
                history=history_text or "(空)",
                emotion_state=emotion_state,
            )
            messages = [
                {"role": "system", "content": "你是角色的记忆记录者，负责总结角色的经历和认知。"},
                {"role": "user", "content": prompt},
            ]
            content = llm.chat(
                messages,
                temperature=call_params.get("temperature"),
                max_tokens=call_params.get("max_tokens"),
                isEnableThinking=call_params.get("is_enable_thinking"),
                reasoning_effort=call_params.get("reasoning_effort"),
                max_context_tokens=call_params.get("max_context_tokens"),
            )
            logger.log_llm(log_label, content, call_params)
            return character_id, content
        except Exception:
            logger.log_llm_error(log_label)
            return character_id, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = dict(pool.map(_one, character_ids))
    return results
