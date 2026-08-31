import traceback
from typing import Any, Dict, List

from config_loader import build_node_prompt, get_llm, get_node_params
from graph_logger import logger
from RPA_langGraph.AgentState import AgentState, ToDoItem
from RPA_langGraph.node_events import publish_node_complete, publish_node_start
from services.formatters import (
    chat_json,
    fmt_all_characters,
    fmt_all_memories,
    fmt_all_relationships,
    fmt_history,
    fmt_user_character,
    fmt_worldview_all,
    parse_llm_json,
)
from SQLiteClient import get_db

SYSTEM_PROMPT = (
    """你是一个角色扮演系统的导演节点 (Director)。
根据当前上下文，编排下一步需要执行的任务列表。

可用任务类型：
- actor — 让角色生成回应
- narration — 生成旁白
- outline — 更新剧情大纲

请根据以下信息，决定下一步需要执行哪些操作：

=== 对话历史 ===
{history}

=== 在场角色信息卡 ===
{characters}

=== 已离场角色（在当前场景之外，稍后可能被玩家召回） ===
{departed}

=== 用户角色信息 ===
{user_character}

=== 角色记忆 ===
{memories}

=== 世界观设定 ===
{worldview}

=== 已有剧情大纲 ===
{outline}

=== 角色关系 ===
{relationships}

请生成待办事项列表。每个待办事项包含：
- targetNode: 目标节点名称，只能是 "actor"、"narration" 或 "outline"
- isCompleted: 布尔值，请始终设为 false
- extraData: 字符串，如果是 actor 节点则传入要扮演的角色ID，其他节点传空字符串

请严格按以下 JSON 格式返回一个顶层 JSON 数组，不要用任何对象包裹（禁止使用 tasks/todo_list 等键），不要包含其他内容：
[
    {{"targetNode": "narration", "isCompleted": false, "extraData": ""}},
    {{"targetNode": "actor", "isCompleted": false, "extraData": "角色ID"}},
    {{"targetNode": "outline", "isCompleted": false, "extraData": ""}}
]

注意：
- 每一轮都应生成 narration，除非本轮没有任何角色需要出场；actor 在前，narration 紧随其后
- outline 不需要每轮都执行，仅在剧情有重大进展时才生成
- 只编排为响应用户输入所需的步骤，不要主动引入新剧情线、新冲突或新场景
- 生成 actor 类型的 TODO 时，extraData 必须填写当前在场角色中存在的角色 ID
- actor 类型的 TODO 的 extraData 绝对不能填入用户角色的角色ID，用户角色由玩家自己控制

"""
)


def director_node(state: AgentState) -> Dict[str, Any]:
    """Analyze the current story state and generate a TODO list for this turn.
    / 分析当前剧情状态，为本轮生成 TODO 列表。

    Calls the LLM (director prompt) to decide which NPC characters should
    speak/act, whether a narration / outline is needed, in what order.
    / 调用 LLM（导演提示词）来决定哪些 NPC 角色应发言/行动、是否需要旁白/大纲。

    **Filtering rules applied after the LLM response**:
    **LLM 响应后应用的过滤规则**：
        - Actor TODOs targeting the *user character* are silently removed
          (the engine never role-plays as the player — the player speaks
          for themselves).
          / 针对*用户角色*的 actor TODO 被静默移除（引擎从不扮演玩家——玩家为自己发言）。
        - Duplicate TODOs (same targetNode + extraData) are merged by the
          merge_todo_list reducer automatically.
          / 重复的 TODO（相同 targetNode + extraData）由 merge_todo_list 归约器自动合并。
    """
    publish_node_start(state, "director_node", "生成待办事项...")
    logger.node_start("director_node", state)

    db = get_db()

    history_text = fmt_history(state["sessionHistory"])
    character_ids = state.get("sessionPresentCharacter", [])
    characters_text = fmt_all_characters(db, character_ids)
    departed_ids = state.get("sessionDepartedCharacter", [])
    departed_text = fmt_all_characters(db, departed_ids) if departed_ids else "无"
    user_character_text = fmt_user_character(db, state.get("sessionUserCharacterID", ""))
    memories_text = fmt_all_memories(db, state.get("sessionID", ""), character_ids)
    worldview_text = fmt_worldview_all(db, state.get("sessionWorldviewCollectionID", ""))
    outline_text = "\n".join(state.get("outline", [])[-50:])
    relationships_text = fmt_all_relationships(db, state.get("sessionID", ""), character_ids)

    prompt = build_node_prompt(
        "director_node",
        SYSTEM_PROMPT,
        context_state=state,
        history=history_text or "(空)",
        characters=characters_text,
        departed=departed_text or "无",
        user_character=user_character_text,
        memories=memories_text,
        worldview=worldview_text,
        outline=outline_text or "(空)",
        relationships=relationships_text,
    )

    messages = [
        {"role": "system", "content": "你是一个专业的剧情导演，负责编排故事流程。"},
        {"role": "user", "content": prompt},
    ]

    llm = get_llm("director_node")
    params = get_node_params().get("director_node", {})
    try:
        _, response = chat_json(llm, messages, params)
        logger.log_llm("director_node", response, params)
    except Exception:
        logger.node_error("director_node")
        traceback.print_exc()
        logger.log_llm_error("director_node")
        logger.node_end("director_node", {"directorToDoList": []})
        return {"directorToDoList": []}

    todo_list = _parse_todo_response(response)

    user_char_id = state.get("sessionUserCharacterID", "")
    if user_char_id:
        todo_list = [
            todo for todo in todo_list if not (todo["targetNode"] == "actor" and todo["extraData"] == user_char_id)
        ]

    publish_node_complete(state, "director_node", "TODOs 生成完毕")
    result: Dict[str, Any] = {"directorToDoList": todo_list}
    logger.node_end("director_node", result)
    return result


def _parse_todo_response(response: str) -> List[ToDoItem]:
    """Parse the LLM's JSON response into a list of ToDoItem dicts.
    / 将 LLM 的 JSON 响应解析为 ToDoItem 字典列表。

    Valid targetNode values are "actor", "narration", "outline".
    Invalid items are silently dropped; an entirely invalid response
    returns an empty list (so the graph moves to the review chain
    with nothing to execute).

    Accepted shapes:
    - a bare JSON array of task objects (the requested format);
    - a single task object (treated as a one-element list);
    - an object wrapping the array under any list-valued key such as
      "todo_list" / "todos" / "tasks" / "directorToDoList" — unwrapped
      instead of dropped (2026-08-17 incidents: the LLM returned
      {"todo_list": [...]} then {"tasks": [...]} under json_object mode;
      each wrapper was treated as one task object and dropped, leaving the
      round with an empty TODO list).
    / 可接受的形态：
      - 裸的任务对象数组（要求的格式）；
      - 单个任务对象（视为单元素数组）；
      - 把数组包在 "todo_list" / "todos" / "tasks" / "directorToDoList"
        等**任意**列表键下的对象——泛化解包而非丢弃（2026-08-17 两次事故：
        json_object 模式下 LLM 先后返回 {"todo_list": [...]} 与
        {"tasks": [...]}，包装对象都被当作单个任务对象整体丢弃，本轮 TODO 为空）。
    """
    data = parse_llm_json(response)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "targetNode" in data:
            # 单个任务对象：视为单元素数组。
            items = [data]
        else:
            # 包装对象：LLM 在 json_object 模式下可能用任意键包裹数组
            # （todo_list / todos / tasks / directorToDoList 等）。
            # 无法预知键名 → 泛化解包：优先取对象值中第一个“任务形状”列表
            # （列表元素均为含 targetNode 的 dict）；否则取第一个列表；
            # 再否则取第一个含 targetNode 的 dict；都没有则空列表。
            items = next(
                (
                    v
                    for v in data.values()
                    if isinstance(v, list)
                    and v
                    and all(isinstance(e, dict) and "targetNode" in e for e in v)
                ),
                None,
            )
            if items is None:
                items = next((v for v in data.values() if isinstance(v, list)), [])
            if not items:
                items = next(
                    ([v] for v in data.values() if isinstance(v, dict) and "targetNode" in v),
                    [],
                )
    else:
        return []

    todo_list = []
    valid_nodes = {"actor", "narration", "outline"}
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("targetNode", "")
        if target not in valid_nodes:
            continue
        todo_list.append(ToDoItem(targetNode=target, isCompleted=False, extraData=str(item.get("extraData", ""))))
    return todo_list
