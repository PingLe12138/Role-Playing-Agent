from typing import Annotated, TypedDict, Union

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

MAX_HISTORY = 50


class ToDoItem(TypedDict):
    targetNode: str
    isCompleted: bool
    extraData: str


class EnvData(TypedDict):
    location: str
    time: str
    atmosphere: str


def capped_messages(existing: list[BaseMessage], new: Union[list[BaseMessage], BaseMessage]) -> list[BaseMessage]:
    """Append messages to history, keeping at most MAX_HISTORY (50) most recent.
    / 将消息追加到历史记录，最多保留 MAX_HISTORY（50）条最近消息。

    Acts as a LangGraph reducer on sessionHistory — older messages are
    trimmed to bound token usage while preserving recent context.
    / 作为 sessionHistory 的 LangGraph 归约器使用——超过上限时自动裁剪旧消息以控制 token 消耗。
    """
    result = add_messages(existing, new)
    return result[-MAX_HISTORY:]


def overwrite_list(existing: list[str], new: list[str]) -> list[str]:
    """Replace an ID list with a deduplicated copy of *new* when non-empty.
    / 用新的去重后的 ID 列表替换现有列表（仅当新列表非空时）。

    A LangGraph reducer used for sessionPresentCharacter: empty input
    (e.g. during subgraph init) preserves the existing list to avoid wiping
    the character roster unintentionally.  Duplicates are removed via dict.
    / 用于 sessionPresentCharacter 的归约器：空输入（如子图初始化时）保留原列表，
      避免意外清空角色列表。重复项通过 dict 去重。
    """
    if not new:
        return existing
    return list(dict.fromkeys(new))


def append_strings(existing: list[str], new: list[str]) -> list[str]:
    existing.extend(new)
    return existing


def merge_todo_list(existing: list[ToDoItem], new: list[ToDoItem]) -> list[ToDoItem]:
    """Merge incoming TODO items into the existing list, keyed by (targetNode, extraData).
    / 以 (targetNode, extraData) 为键，将新的 TODO 项合并到现有列表中。

    A LangGraph reducer used for both supervisorToDoList and directorToDoList.
    - Passing an empty list → clears the entire list (used to reset TODOs).
    - Non-empty → upsert semantics: items with a matching key get replaced
      in-place; new keys are appended.  This allows nodes to "complete" a
      specific TODO by overwriting it with isCompleted=True.
    / 同时用于 supervisorToDoList 和 directorToDoList 的归约器。
    - 传入空列表 → 清空整个列表（用于重置 TODO）。
    - 非空 → 更新插入语义：匹配键的项原地替换；新键追加。
      这使得节点可以通过将 isCompleted=True 覆盖来"完成"特定的 TODO。
    """
    if not new:
        return []
    existing_map = {(item["targetNode"], item["extraData"]): i for i, item in enumerate(existing)}
    for item in new:
        key = (item["targetNode"], item["extraData"])
        if key in existing_map:
            existing[existing_map[key]] = item
        else:
            existing.append(item)
    return existing


def reset_on_empty(existing: list[dict], new: list[dict]) -> list[dict]:
    """Collect intermediate node outputs; pass an empty list to reset.
    / 收集节点的中间输出；传入空列表则重置。

    A LangGraph reducer used for directorGraphOutput.
    - Non-empty input appends to the existing list (review nodes read it).
    - Empty input clears the list — used after the review chain has consumed
      the accumulated outputs so the next round starts fresh.
    / 用于 directorGraphOutput 的归约器。
    - 非空输入追加到现有列表（审看节点读取此数据）。
    - 空输入清空列表——在审看链消费完累积输出后使用，使下一轮从零开始。
    """
    if not new:
        return []
    existing.extend(new)
    return existing


class AgentState(TypedDict):
    sessionID: str
    sessionHistory: Annotated[list[BaseMessage], capped_messages]
    sessionEnvData: EnvData
    sessionPresentCharacter: Annotated[list[str], overwrite_list]
    sessionDepartedCharacter: list[str]
    outline: list[str]
    supervisorToDoList: Annotated[list[ToDoItem], merge_todo_list]
    directorToDoList: Annotated[list[ToDoItem], merge_todo_list]
    supervisorCurrentTask: Union[ToDoItem, None]
    directorCurrentTask: Union[ToDoItem, None]
    sessionWorldviewCollectionID: str
    sessionUserCharacterID: str
    permanentWorldviewCollectionEntry: Annotated[list[str], append_strings]
    directorGraphOutput: Annotated[list[dict], reset_on_empty]
    memoryRoundCounter: int
    memorySummarizeInterval: int
    pendingDepartedIDs: list[str]
    pendingPlayerChoice: Union[dict, None]
