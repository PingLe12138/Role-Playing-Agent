# -*- coding: utf-8 -*-
"""回归测试：director_node 的 TODO 响应解析容错。

历史事故（2026-08-17 同日两次）：
- graph_20260817_142653.log：导演节点 LLM 返回单个 JSON 对象
  （{"targetNode": "actor", ...}）而非要求的数组，旧解析逻辑将非列表直接丢弃，
  导致 directorToDoList 为空、整轮无任何 actor/narration/outline 执行。
- graph_20260817_151928.log：LLM 返回 {"todo_list": [...]} 包裹数组。
- graph_20260817_152610.log：LLM 返回 {"tasks": [...]} 包裹数组。
  后两者在 json_object 模式下反复出现，包装键名不可预知 → 解析器必须泛化解包。
"""
from RPA_langGraph.nodes.director_node import _parse_todo_response


def test_array_response_parses_all_valid_items():
    """正常路径：合法的任务数组全部解析为 ToDoItem。"""
    raw = '''[
        {"targetNode": "narration", "isCompleted": false, "extraData": ""},
        {"targetNode": "actor", "isCompleted": false, "extraData": "char_a"},
        {"targetNode": "outline", "isCompleted": false, "extraData": ""}
    ]'''
    result = _parse_todo_response(raw)
    assert result == [
        {"targetNode": "narration", "isCompleted": False, "extraData": ""},
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_a"},
        {"targetNode": "outline", "isCompleted": False, "extraData": ""},
    ]


def test_single_object_response_is_wrapped():
    """事故场景：LLM 只返回单个任务对象而非数组，应视为单元素列表而非丢弃。"""
    raw = '''{
        "targetNode": "actor",
        "isCompleted": false,
        "extraData": "char_zheng_hu_b7bed01c"
    }'''
    result = _parse_todo_response(raw)
    assert result == [
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_zheng_hu_b7bed01c"}
    ]


def test_single_object_inside_markdown_fence_is_wrapped():
    """带 ```json 代码围栏的单对象响应同样应被接受。"""
    raw = '```json\n{"targetNode": "narration", "isCompleted": false, "extraData": ""}\n```'
    result = _parse_todo_response(raw)
    assert result == [{"targetNode": "narration", "isCompleted": False, "extraData": ""}]


def test_wrapped_array_response_is_unwrapped():
    """事故场景：LLM 把数组包在 {"todo_list": [...]} 对象里（json_object 模式
    偏好对象根），应解包而非当作单个任务对象丢弃。"""
    raw = '''{
        "todo_list": [
            {"targetNode": "actor", "isCompleted": false, "extraData": "char_zheng_hu_b7bed01c"},
            {"targetNode": "narration", "isCompleted": false, "extraData": ""},
            {"targetNode": "outline", "isCompleted": false, "extraData": ""}
        ]
    }'''
    result = _parse_todo_response(raw)
    assert result == [
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_zheng_hu_b7bed01c"},
        {"targetNode": "narration", "isCompleted": False, "extraData": ""},
        {"targetNode": "outline", "isCompleted": False, "extraData": ""},
    ]


def test_wrapped_array_with_todos_key_is_unwrapped():
    """使用 "todos" 键包裹数组同样应被解包。"""
    raw = '{"todos": [{"targetNode": "narration", "isCompleted": false, "extraData": ""}]}'
    assert _parse_todo_response(raw) == [
        {"targetNode": "narration", "isCompleted": False, "extraData": ""}
    ]


def test_wrapped_array_with_tasks_key_is_unwrapped():
    """事故重演：LLM 用 "tasks" 键包裹数组（graph_20260817_152610.log 的真实
    响应），包装键名未知时也必须泛化解包。"""
    raw = '''{
        "tasks": [
            {"targetNode": "narration", "isCompleted": false, "extraData": ""},
            {"targetNode": "actor", "isCompleted": false, "extraData": "char_zheng_hu_b7bed01c"},
            {"targetNode": "actor", "isCompleted": false, "extraData": "char_li_xin_fcdb88fc"}
        ]
    }'''
    result = _parse_todo_response(raw)
    assert result == [
        {"targetNode": "narration", "isCompleted": False, "extraData": ""},
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_zheng_hu_b7bed01c"},
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_li_xin_fcdb88fc"},
    ]


def test_wrapped_single_task_object_is_unwrapped():
    """包装键下是单个任务对象也应收纳。"""
    raw = '{"task": {"targetNode": "actor", "isCompleted": false, "extraData": "char_x"}}'
    assert _parse_todo_response(raw) == [
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_x"}
    ]


def test_wrapped_object_without_valid_wrapper_returns_empty():
    """包装对象既无 targetNode 也无可用列表键时返回空列表（而非崩溃）。"""
    assert _parse_todo_response('{"foo": "bar"}') == []


def test_single_object_with_invalid_target_returns_empty():
    """单对象但 targetNode 非法：仍按原规则静默丢弃，结果为空。"""
    raw = '{"targetNode": "unknown_node", "isCompleted": false, "extraData": ""}'
    assert _parse_todo_response(raw) == []


def test_non_object_non_list_response_returns_empty():
    """既非数组也非对象的响应（如纯文本/数字）仍返回空列表。"""
    assert _parse_todo_response("这不是 JSON") == []
    assert _parse_todo_response("42") == []


def test_invalid_items_are_silently_dropped():
    """数组中的非法项（非字典、缺 targetNode、非法 targetNode）被静默丢弃。"""
    raw = '''[
        {"targetNode": "actor", "isCompleted": false, "extraData": "char_ok"},
        "garbage",
        {"isCompleted": false},
        {"targetNode": "evil", "extraData": "x"},
        {"targetNode": "narration"}
    ]'''
    result = _parse_todo_response(raw)
    assert result == [
        {"targetNode": "actor", "isCompleted": False, "extraData": "char_ok"},
        {"targetNode": "narration", "isCompleted": False, "extraData": ""},
    ]
