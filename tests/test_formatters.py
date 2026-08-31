import json

from langchain_core.messages import HumanMessage

from services.formatters import fmt_env_data, fmt_history, fmt_node_outputs, parse_llm_json


class TestParseLlmJson:
    def test_plain_json_object(self):
        result = parse_llm_json('{"a": 1, "b": "hello"}')
        assert result == {"a": 1, "b": "hello"}

    def test_plain_json_array(self):
        result = parse_llm_json('[{"a": 1}, {"b": 2}]')
        assert result == [{"a": 1}, {"b": 2}]

    def test_triple_backtick_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_triple_backtick_no_lang(self):
        raw = '```\n{"key": "value"}\n```'
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_extra_text_before_after(self):
        raw = '这是一些文本\n{"actual": "json"}\n\u540e\u7eed\u6587\u672c'
        result = parse_llm_json(raw)
        assert result == {"actual": "json"}

    def test_extra_text_with_array(self):
        raw = "text before\n[1, 2, 3]\ntext after"
        result = parse_llm_json(raw)
        assert result == [1, 2, 3]

    def test_no_json_returns_none(self):
        result = parse_llm_json("\u5b8c\u5168\u6ca1\u6709 JSON \u5185\u5bb9")
        assert result is None

    def test_empty_string(self):
        result = parse_llm_json("")
        assert result is None

    def test_whitespace_only(self):
        result = parse_llm_json("   \n  \t  ")
        assert result is None

    def test_array_with_trailing_comma(self):
        raw = '[\n    {"a": 1},\n    {"b": 2},\n]'
        assert parse_llm_json(raw) == [{"a": 1}, {"b": 2}]

    def test_object_with_trailing_comma(self):
        raw = '{"a": 1, "b": 2,}'
        assert parse_llm_json(raw) == {"a": 1, "b": 2}

    def test_trailing_comma_inside_fences(self):
        raw = '```json\n[{"a": 1},]\n```'
        assert parse_llm_json(raw) == [{"a": 1}]

    def test_trailing_comma_with_wrapping_text(self):
        raw = "\u7ed3\u679c\u5982\u4e0b\uff1a\n[1, 2, 3,]\n\u4ee5\u4e0a\u3002"
        assert parse_llm_json(raw) == [1, 2, 3]

    def test_string_value_containing_close_bracket_comma_not_mangled(self):
        # 合法 JSON 直接按原样解析，字符串值里的 ", ]" 与 ", }" 不得被清洗逻辑改动
        raw = '{"a": "x, ] y", "b": "p, } q"}'
        assert parse_llm_json(raw) == {"a": "x, ] y", "b": "p, } q"}

    def test_bom_prefixed_json(self):
        raw = "\ufeff{\"a\": 1}"
        assert parse_llm_json(raw) == {"a": 1}


class TestFmtNodeOutputs:
    def test_empty_outputs(self):
        assert fmt_node_outputs([]) == ""
        assert fmt_node_outputs(None) == ""

    def test_actor_output(self):
        outputs = [
            {
                "node": "actor_node",
                "character": "\u6c99\u7279",
                "action": "\u62d4\u5251",
                "inner_thought": "\u4ed6\u5f88\u5f3a",
                "speech": "\u6765\u5427\uff01",
            }
        ]
        result = fmt_node_outputs(outputs)
        assert "[actor \u626e\u6f14 \u6c99\u7279]" in result
        assert "\u52a8\u4f5c: \u62d4\u5251" in result
        assert "\u5bf9\u8bdd: \u6765\u5427\uff01" in result

    def test_narration_output(self):
        outputs = [{"node": "narration_node", "result": "\u591c\u8272\u5f88\u6df1"}]
        result = fmt_node_outputs(outputs)
        assert "[narration \u65c1\u767d]" in result
        assert "\u591c\u8272\u5f88\u6df1" in result

    def test_outline_output(self):
        outputs = [{"node": "outline_node", "result": "\u4ed6\u4eec\u8fdb\u5165\u4e86\u53e4\u57ce"}]
        result = fmt_node_outputs(outputs)
        assert "[outline \u603b\u7ed3]" in result

    def test_unknown_node(self):
        outputs = [{"node": "custom", "foo": "bar"}]
        result = fmt_node_outputs(outputs)
        assert "[custom]" in result

    def test_multiple_outputs_separated(self):
        outputs = [{"node": "narration_node", "result": "A"}, {"node": "outline_node", "result": "B"}]
        result = fmt_node_outputs(outputs)
        assert "===" in result


class TestFmtHistory:
    def test_empty_history(self):
        assert fmt_history([]) == ""

    def test_basic_messages(self, sample_messages):
        result = fmt_history(sample_messages)
        assert "[human]" in result
        assert "[ai]" in result
        assert "\u4f60\u597d" in result

    def test_content_type_wrapper_unwrapped(self):
        wrapped = json.dumps(
            {"contentType": "generalNarration", "content": "\u5199\u4e00\u6bb5\u6545\u4e8b"}, ensure_ascii=False
        )
        msgs = [HumanMessage(content=wrapped)]
        result = fmt_history(msgs)
        assert "[human]" in result
        assert "\u5199\u4e00\u6bb5\u6545\u4e8b" in result
        assert "contentType" not in result


class TestFmtEnvData:
    def test_full_env(self):
        env = {"location": "\u53e4\u57ce", "time": "\u591c\u665a", "atmosphere": "\u5e84\u4e25"}
        result = fmt_env_data(env)
        assert "\u5730\u70b9: \u53e4\u57ce" in result
        assert "\u65f6\u95f4: \u591c\u665a" in result
        assert "\u6c1b\u56f4: \u5e84\u4e25" in result

    def test_partial_env(self):
        env = {"location": ""}
        result = fmt_env_data(env)
        assert "\u5730\u70b9: " in result
        assert "\u65f6\u95f4: \u672a\u77e5" in result

    def test_empty_env(self):
        result = fmt_env_data({})
        assert "\u672a\u77e5" in result
