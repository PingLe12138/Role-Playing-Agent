from langchain_core.messages import AIMessage, HumanMessage

from RPA_langGraph.AgentState import (
    MAX_HISTORY,
    ToDoItem,
    append_strings,
    capped_messages,
    merge_todo_list,
    overwrite_list,
    reset_on_empty,
)


class TestCappedMessages:
    def test_basic_add(self):
        existing = [HumanMessage(content="hi")]
        new = AIMessage(content="hello")
        result = capped_messages(existing, new)
        assert len(result) == 2
        assert result[-1].content == "hello"

    def test_capped_at_max(self):
        existing = [HumanMessage(content=str(i)) for i in range(MAX_HISTORY)]
        new = HumanMessage(content="new")
        result = capped_messages(existing, new)
        assert len(result) == MAX_HISTORY
        assert result[-1].content == "new"


class TestOverwriteList:
    def test_empty_new_keeps_existing(self):
        assert overwrite_list(["a", "b"], []) == ["a", "b"]

    def test_non_empty_overwrites(self):
        assert overwrite_list(["a", "b"], ["c", "d"]) == ["c", "d"]

    def test_deduplicates(self):
        assert overwrite_list(["a"], ["b", "b", "a"]) == ["b", "a"]

    def test_empty_existing_with_new(self):
        assert overwrite_list([], ["x"]) == ["x"]

    def test_both_empty(self):
        assert overwrite_list([], []) == []


class TestAppendStrings:
    def test_append_new(self):
        existing = ["a"]
        result = append_strings(existing, ["b", "c"])
        assert result == ["a", "b", "c"]

    def test_empty_existing(self):
        assert append_strings([], ["x"]) == ["x"]

    def test_empty_new(self):
        existing = ["a"]
        assert append_strings(existing, []) == ["a"]


class TestMergeTodoList:
    def test_empty_new_returns_empty(self):
        existing = [ToDoItem(targetNode="actor", isCompleted=False, extraData="")]
        result = merge_todo_list(existing, [])
        assert result == []

    def test_updates_existing_by_key(self):
        existing = [ToDoItem(targetNode="actor", isCompleted=False, extraData="")]
        new = [ToDoItem(targetNode="actor", isCompleted=True, extraData="")]
        result = merge_todo_list(existing, new)
        assert len(result) == 1
        assert result[0]["isCompleted"] is True

    def test_appends_new_key(self):
        existing = [ToDoItem(targetNode="actor", isCompleted=False, extraData="")]
        new = [ToDoItem(targetNode="narration", isCompleted=False, extraData="")]
        result = merge_todo_list(existing, new)
        assert len(result) == 2


class TestResetOnEmpty:
    def test_empty_new_resets(self):
        assert reset_on_empty([{"a": 1}], []) == []

    def test_non_empty_appends(self):
        result = reset_on_empty([{"a": 1}], [{"b": 2}])
        assert result == [{"a": 1}, {"b": 2}]

    def test_both_empty(self):
        assert reset_on_empty([], []) == []
