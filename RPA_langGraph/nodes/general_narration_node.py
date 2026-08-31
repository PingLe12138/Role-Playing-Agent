import json
import re
import traceback
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import (
    fmt_all_characters,
    fmt_all_emotion_states,
    fmt_all_memories,
    fmt_all_relationships,
    fmt_env_data,
    fmt_history,
    fmt_user_character,
    fmt_worldview_all,
)
from services.id_utils import generate_history_id
from SQLiteClient import get_db
from SSEPublisher import publisher

GENERAL_NARRATION_PROMPT = (
    """你是一个角色扮演系统中的一般叙述者 (General Narrator)。
根据对话历史和用户提供的指令，生成一段用户要求的故事情节。

要求：
1. 以第三人称叙述，语言生动自然
2. 直接按指令展开故事，不要询问确认或补充说明
3. 输出连贯的叙述文本，不要包含任何标记或格式说明
4. 【从历史结尾续写】你的叙述必须紧接"对话历史"最后一条消息之后的时间点自然延续，
   从最后一条内容停下的地方继续写，绝不要从头重讲已经发生过的情节
5. 【严禁重复】绝对禁止复述或改写历史中已经出现过的任何内容：
   - 不得重复已写过的情节、事件、场景、动作、对话或心理活动
   - 不得换一种说法重写同一事件，不得把角色说过的台词再编一遍
   - 不得再次详细描写已写过的环境细节（如光线、摆设、衣着等）
   - 宁可跳过旧内容直接推进，也不要重复
6. 【推进而非重讲】写作前先判断"历史停在哪里、指令要求写到哪"，
   只写两者之间尚未发生的部分；若指令描述的场景在历史中已写过，
   视为要求续写该场景的后续发展，而不是把该场景重新写一遍
7. 若指令与历史衔接不上，以历史最后一条消息为准向前推进，不推翻已有剧情

"""
    + """

=== 指令 ===
{instructions}

=== 当前环境 ===
{env_data}

=== 对话历史 ===
{history}

=== 在场角色信息卡 ===
{character_cards}

=== 用户角色信息 ===
{user_character}

=== 世界观设定 ===
{worldview_entries}

=== 角色记忆 ===
{memories}

=== 角色关系 ===
{relationships}

=== 在场角色情绪 ===
{emotion_states}

请以第三人称叙述，紧接对话历史的最后一条内容之后，生成符合指令要求的新情节。"""
)

# ---- 分块续写参数 ----
# 指令中出现字数要求（如"字数不少于8000字"）时，单次生成不足会追加续写轮次，
# 每轮续写重新附上完整节点提示词（全部上下文节 + 系统限制）与已生成的故事全文，
# 直到总字数达标或达到轮次上限，保证输出达到用户指定字数且不跑题。
#
# 续写合并策略（2026-08-17 事故修复）：LLM 在长上下文下常把【已生成的故事正文】
# 整段回抄到输出里再续写（graph_20260817_153255.log：第二轮输出前 1975 字符与
# 第一轮逐字相同），旧逻辑直接拼接导致成品中整段重复。现在：
#   - 提示词允许模型以"复述结尾 1-2 句作为锚点"的方式改写上一段结尾；
#   - _merge_chunk 检测输出开头与旧文结尾的重复：短重叠（<= MAX_REWRITE_ANCHOR_CHARS）
#     视为改写锚点 → 替换锚点之后的旧文段；长重叠（整段回抄）→ 仅去重并追加新内容。
MAX_CONTINUATION_ROUNDS = 8          # 总 LLM 调用轮次上限（含首次生成）
MIN_CONTINUATION_CHARS = 60          # 单轮产出低于该字符数视为模型已收尾
MAX_CONSECUTIVE_SHORT_ROUNDS = 2     # 连续收尾轮数达到该值则停止续写
CONTINUATION_STORY_CHARS = 30000     # 续写轮次携带的已生成正文上限（超出取结尾部分）
MIN_OVERLAP_CHARS = 12               # 续写输出与旧文结尾判为"重复/锚点"的最短长度
MAX_REWRITE_ANCHOR_CHARS = 200       # 超过该长度的重复视为"整段回抄"，只去重不替换
_OVERLAP_SEARCH_CHARS = 3000         # 只在旧文结尾附近查找重叠，控制开销

_CONTINUATION_RULES = (
    "=== 续写要求 ===\n"
    "1. 严格遵循上方提示词中的【指令】推进情节：只写指令要求的内容，"
    "不得引入指令之外的新角色、新事件、新元素或新设定\n"
    "2. 情节必须持续推进，向【指令】要求的方向发展，最终收束到指令所指定的结果/结尾；"
    "紧接【已生成的故事正文】的结尾之后续写，不要从头复述正文中的任何情节；"
    "充分描写环境、动作、对话与心理活动，细节越丰富越好；"
    "不要总结，不要写“接着”“然后”之类的过渡说明\n"
    "3. 【允许改写上一段结尾】如果【已生成的故事正文】的结尾偏离了【指令】的方向、"
    "已经提前收尾、或内容重复拖沓，你可以改写它的结尾，让情节自然通向指令要求的结局。"
    "改写方式：先一字不差地复述你准备从何处改写的结尾句子（一两句即可，作为接续锚点），"
    "然后紧接着输出改写后的新叙述并继续推进；"
    "系统会识别该锚点，并用你的输出替换锚点之后的所有旧文段。"
    "若无需改写，直接输出新的续写正文即可\n"
    "4. 【严禁重复】除上述改写锚点外，绝对不要复述【已生成的故事正文】中已写过的任何内容："
    "不要整段回抄前文，不要换一种说法重写同一事件，不要重复已经写过的情节、场景、对话或动作；"
    "宁可跳过前文直接推进，也不要重复\n"
    "5. 直接输出续写的正文，不要包含任何标记、说明或格式\n"
    "目标：已生成 {done_chars} 字，目标不少于 {target_chars} 字，"
    "本次请继续写出至少 {wanted_chars} 字的正文。\n"
    "请直接以正文续写。"
)


def _char_len(text: str) -> int:
    """Count characters excluding whitespace (closer to '字数')."""
    return len(re.sub(r"\s", "", text))


def _extract_target_chars(text: str) -> int:
    """Extract the requested word count from instructions, e.g. '字数不少于8000字'."""
    if not text:
        return 0
    matches = [int(m) for m in re.findall(r"(\d+)\s*字", text)]
    return max(matches) if matches else 0


def _merge_chunk(story: str, chunk: str) -> str:
    """Merge a continuation chunk into the story so far, deduplicating echoes.

    The continuation prompt allows the model to rewrite the previous ending by
    restating a short tail anchor (1-2 sentences verbatim) before the revised
    text.  This merge implements the contract:

    - Short overlap (<= MAX_REWRITE_ANCHOR_CHARS and less than half the story):
      the chunk restates the anchor and then revises → replace everything after
      the anchor (story[:-L] + chunk[L:]).
    - Long overlap (echo of a large part / the whole story): never discard
      written content, just strip the repeated prefix and append the new part
      (story + chunk[L:]).
    - No overlap: plain append with a paragraph separator.

    / 把续写片段合并进已生成正文，并消除回抄重复：
      短重叠（<= MAX_REWRITE_ANCHOR_CHARS 且小于正文一半）= 模型复述改写锚点 →
      替换锚点之后的旧文段；长重叠 = 模型整段回抄前文 → 只去重、绝不丢内容，
      追加新部分；无重叠 = 直接以段落分隔追加。
    """
    if not story:
        return chunk
    tail = story[-_OVERLAP_SEARCH_CHARS:]
    max_l = min(len(tail), len(chunk))
    L = 0
    for l in range(max_l, MIN_OVERLAP_CHARS - 1, -1):
        if tail[-l:] == chunk[:l]:
            L = l
            break
    if L == 0:
        return story + "\n\n" + chunk
    if L <= MAX_REWRITE_ANCHOR_CHARS and L < len(story) // 2:
        # 改写锚点：从锚点起替换旧文段
        return story[:-L] + chunk[L:]
    # 整段回抄（含短正文整体回抄）：仅去重，追加新内容
    return story + chunk[L:]


def _build_continuation_prompt(first_prompt: str, story: str, total: int, target: int) -> str:
    """Build a continuation prompt: full original prompt + story written so far + continuation rules.

    The full original prompt carries every context section (instructions, env,
    history, character cards, worldview, memories, relationships, emotions) and
    the shared system rules, so continuation rounds keep following the original
    instruction instead of drifting off-topic.

    The appended continuation rules allow the model to rewrite the previous
    ending (restating a short anchor verbatim) and forbid re-echoing the story;
    _merge_chunk applies the matching merge.
    """
    if len(story) > CONTINUATION_STORY_CHARS:
        story = "……（前文过长，此处仅展示结尾部分）\n" + story[-CONTINUATION_STORY_CHARS:]
    rules = (
        _CONTINUATION_RULES.replace("{done_chars}", str(total))
        .replace("{target_chars}", str(target))
        .replace("{wanted_chars}", str(max(target - total, MIN_CONTINUATION_CHARS)))
    )
    return first_prompt + "\n\n=== 已生成的故事正文 ===\n" + story + "\n\n" + rules


def _chat_once(llm, params, messages: List[Dict[str, str]]) -> str:
    return llm.chat(
        messages,
        temperature=params.get("temperature"),
        max_tokens=params.get("max_tokens"),
        isEnableThinking=params.get("is_enable_thinking"),
        reasoning_effort=params.get("reasoning_effort"),
        max_context_tokens=params.get("max_context_tokens"),
    )


def _generate_with_continuation(llm, params, first_prompt: str, target_chars: int) -> str:
    """Generate the story in chunks until the requested length is reached.

    Every continuation round re-sends the FULL original node prompt (all context
    sections + system rules) together with the complete story written so far,
    so the model keeps following the original instruction instead of drifting.

    Chunks are merged via _merge_chunk, which strips any repetition of the
    story written so far (the model tends to echo it back under long-context
    generation) and applies tail rewrites when the model restates a short
    anchor.  Individual round errors are tolerated: whatever has been generated
    so far is kept, so a mid-way failure does not lose the whole story.
    """
    system_msg = {"role": "system", "content": "你是一个故事叙述者，负责生成指定的情节发展。"}
    messages: List[Dict[str, str]] = [system_msg, {"role": "user", "content": first_prompt}]

    short_streak = 0
    story = ""
    for _ in range(MAX_CONTINUATION_ROUNDS):
        try:
            chunk = _chat_once(llm, params, messages)
        except Exception as e:
            logger.log_llm_error("general_narration_node", str(e))
            traceback.print_exc()
            break
        logger.log_llm("general_narration_node", chunk, params)

        chunk = (chunk or "").strip()
        story = _merge_chunk(story, chunk)
        total = _char_len(story)

        if _char_len(chunk) < MIN_CONTINUATION_CHARS:
            short_streak += 1
        else:
            short_streak = 0
        if total >= target_chars or short_streak >= MAX_CONSECUTIVE_SHORT_ROUNDS:
            break

        messages = [
            system_msg,
            {"role": "user", "content": _build_continuation_prompt(first_prompt, story, total, target_chars)},
        ]

    return story


def general_narration_node(state: AgentState) -> Dict[str, Any]:
    task = state.get("supervisorCurrentTask")
    if task is None:
        return {}

    logger.node_start("general_narration_node", state)

    publish_node_start(state, "general_narration_node", "生成指定情节...")
    db = get_db()

    history = state.get("sessionHistory", [])
    history_text = fmt_history(history)

    character_ids = state.get("sessionPresentCharacter", [])
    character_cards = fmt_all_characters(db, character_ids)
    user_character = fmt_user_character(db, state.get("sessionUserCharacterID", ""))
    env_data = fmt_env_data(state.get("sessionEnvData", {}))
    worldview_entries = fmt_worldview_all(db, state.get("sessionWorldviewCollectionID", ""))
    memories = fmt_all_memories(db, state.get("sessionID", ""), character_ids)
    relationships = fmt_all_relationships(db, state.get("sessionID", ""), character_ids)
    emotion_states = fmt_all_emotion_states(db, state.get("sessionID", ""), character_ids)

    instructions = task.get("extraData", "")
    prompt = build_node_prompt(
        "general_narration_node",
        GENERAL_NARRATION_PROMPT,
        context_state=state,
        instructions=instructions,
        env_data=env_data,
        history=history_text or "(空)",
        character_cards=character_cards,
        user_character=user_character,
        worldview_entries=worldview_entries,
        memories=memories,
        relationships=relationships,
        emotion_states=emotion_states,
    )

    llm = get_llm("general_narration_node")
    params = get_node_params().get("general_narration_node", {})

    target_chars = _extract_target_chars(instructions)
    if target_chars > 0:
        # 指令带字数要求：分块续写，直到总字数达到目标
        response = _generate_with_continuation(llm, params, prompt, target_chars)
    else:
        try:
            response = _chat_once(
                llm,
                params,
                [
                    {"role": "system", "content": "你是一个故事叙述者，负责生成指定的情节发展。"},
                    {"role": "user", "content": prompt},
                ],
            )
            logger.log_llm("general_narration_node", response, params)
        except Exception as e:
            logger.node_error("general_narration_node")
            traceback.print_exc()
            logger.log_llm_error("general_narration_node", str(e))
            task["isCompleted"] = True
            return {"supervisorToDoList": [task], "supervisorCurrentTask": None}

    if not response or not response.strip():
        # 全部轮次均失败时，与旧逻辑一致：标记完成并退出，不写空内容
        task["isCompleted"] = True
        return {"supervisorToDoList": [task], "supervisorCurrentTask": None}

    formatted = json.dumps({"contentType": "general_narration", "content": response}, ensure_ascii=False)

    try:
        session_id = state.get("sessionID", "")
        history_id = generate_history_id()
        db.execute(
            "INSERT INTO session_history "
            "(sessionHistoryID, parentID, role, createdBy, content, "
            "recordCreatedTime, recordUpdatedTime) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (history_id, session_id, "general_narration", "general_narration", formatted),
        )
    except Exception:
        traceback.print_exc()

    publisher.publish(
        "message",
        {
            "sessionID": state.get("sessionID", ""),
            "contentType": "general_narration",
            "content": response,
            "role": "general_narration",
            "sessionHistoryID": history_id,
        },
    )

    task["isCompleted"] = True

    publish_node_complete(state, "general_narration_node", "情节生成完毕")
    result = {
        "sessionHistory": [AIMessage(content=formatted)],
        "supervisorToDoList": [task],
        "supervisorCurrentTask": None,
    }
    logger.node_end("general_narration_node", result)
    return result
