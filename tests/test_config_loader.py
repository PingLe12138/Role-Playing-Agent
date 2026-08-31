import json
import os
import tempfile

import pytest

from AnthropicLLMClient import AnthropicLLMClient
import config_loader
from config_loader import get_memory_summarize_interval, load_config
from LLMStreamClient import LLMStreamClient
import paths


class TestLoadConfig:
    def test_load_valid_config(self):
        data = {"llm": {"api_key": "sk-test", "default_model": "gpt-4"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            result = load_config(path)
            assert result["llm"]["api_key"] == "sk-test"
            assert result["llm"]["default_model"] == "gpt-4"
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.json")

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("{invalid json}")
            path = f.name
        try:
            with pytest.raises(json.JSONDecodeError):
                load_config(path)
        finally:
            os.unlink(path)


class TestGetLlm:
    """get_llm() must forward the llm-level globals (temperature / max_tokens /
    thinking) into LLMStreamClient so config.json values actually take effect.
    / get_llm() 必须把 llm 全局参数（温度/最大 Token/思考模式）传入 LLMStreamClient，
      使 config.json 中的值真正生效。"""

    @pytest.fixture(autouse=True)
    def _clear_llm_cache(self):
        config_loader.clear_cache()
        yield
        config_loader.clear_cache()

    def test_forwards_llm_globals(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {
                "llm": {
                    "api_key": "sk-test",
                    "base_url": "https://example.com/v1",
                    "default_model": "deepseek-v4-flash",
                    "default_temperature": 0.3,
                    "default_max_tokens": 8192,
                    "is_enable_thinking": "enabled",
                }
            },
        )
        client = config_loader.get_llm()
        assert client.default_model == "deepseek-v4-flash"
        assert client.default_temperature == 0.3
        assert client.default_max_tokens == 8192
        assert client.isEnableThinking == "enabled"

    def test_missing_llm_globals_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"llm": {"api_key": "sk-test", "default_model": "gpt-4o-mini"}},
        )
        client = config_loader.get_llm()
        assert client.default_temperature == 0.9
        assert client.default_max_tokens == 2048
        assert client.isEnableThinking == "disabled"

    def test_null_llm_globals_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {
                "llm": {
                    "api_key": "sk-test",
                    "default_temperature": None,
                    "default_max_tokens": None,
                    "is_enable_thinking": None,
                }
            },
        )
        client = config_loader.get_llm()
        assert client.default_temperature == 0.9
        assert client.default_max_tokens == 2048
        assert client.isEnableThinking == "disabled"

    def test_forwards_new_llm_globals(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {
                "llm": {
                    "api_key": "sk-test",
                    "default_reasoning_effort": "high",
                    "max_context_tokens": 8000,
                }
            },
        )
        client = config_loader.get_llm()
        assert client.default_reasoning_effort == "high"
        assert client.default_max_context_tokens == 8000

    def test_missing_new_llm_globals_fall_back_to_none(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"llm": {"api_key": "sk-test"}},
        )
        client = config_loader.get_llm()
        assert client.default_reasoning_effort is None
        assert client.default_max_context_tokens is None


class TestNodeLlmOverride:
    """`node_llm[node]` must win over the global `llm` section, with unset
    (absent / null / empty) keys still inheriting the global value.
    / node_llm[node] 必须优先于全局 llm 段，未设置（缺省/null/空串）的键仍继承全局值。
    """

    BASE = {
        "llm": {
            "api_key": "sk-global",
            "base_url": "https://global.example.com/v1",
            "default_model": "global-model",
            "default_temperature": 0.9,
            "default_max_tokens": 2048,
            "is_enable_thinking": "disabled",
            "timeout_seconds": 600,
        }
    }

    @pytest.fixture(autouse=True)
    def _clear_llm_cache(self):
        config_loader.clear_cache()
        yield
        config_loader.clear_cache()

    def _patch(self, monkeypatch, node_llm):
        cfg = dict(self.BASE)
        cfg["node_llm"] = node_llm
        monkeypatch.setattr(config_loader, "load_config", lambda: cfg)

    def test_no_override_reuses_global_client(self, monkeypatch):
        self._patch(monkeypatch, {})
        assert config_loader.get_llm("actor_node") is config_loader.get_llm()

    def test_override_wins_over_global(self, monkeypatch):
        self._patch(
            monkeypatch,
            {"actor_node": {"api_key": "sk-node", "base_url": "https://node.example.com/v1", "default_model": "node-model"}},
        )
        client = config_loader.get_llm("actor_node")
        assert client.default_model == "node-model"
        assert client.client.api_key == "sk-node"
        assert str(client.client.base_url).startswith("https://node.example.com/v1")

    def test_unset_keys_inherit_global(self, monkeypatch):
        self._patch(monkeypatch, {"actor_node": {"default_model": "node-model"}})
        client = config_loader.get_llm("actor_node")
        assert client.default_model == "node-model"
        assert client.default_temperature == 0.9
        assert client.default_max_tokens == 2048
        assert client.client.api_key == "sk-global"

    def test_empty_string_and_null_inherit_global(self, monkeypatch):
        self._patch(
            monkeypatch,
            {"actor_node": {"base_url": "", "api_key": None, "default_model": "   "}},
        )
        assert config_loader.resolve_llm_config("actor_node") == self.BASE["llm"]

    def test_other_nodes_unaffected(self, monkeypatch):
        self._patch(monkeypatch, {"actor_node": {"default_model": "node-model"}})
        assert config_loader.get_llm("narration_node").default_model == "global-model"
        assert config_loader.get_llm("narration_node") is config_loader.get_llm()

    def test_clients_cached_per_node_and_rebuilt_on_change(self, monkeypatch):
        self._patch(monkeypatch, {"actor_node": {"default_model": "node-model"}})
        first = config_loader.get_llm("actor_node")
        assert config_loader.get_llm("actor_node") is first

        self._patch(monkeypatch, {"actor_node": {"default_model": "node-model-v2"}})
        second = config_loader.get_llm("actor_node")
        assert second is not first
        assert second.default_model == "node-model-v2"

    def test_clear_cache_drops_node_clients(self, monkeypatch):
        self._patch(monkeypatch, {"actor_node": {"default_model": "node-model"}})
        first = config_loader.get_llm("actor_node")
        config_loader.clear_cache()
        assert config_loader.get_llm("actor_node") is not first

    def test_unknown_node_falls_back_to_global(self, monkeypatch):
        self._patch(monkeypatch, {"nonexistent_node": {"default_model": "x"}})
        assert config_loader.resolve_llm_config("another_node") == self.BASE["llm"]

    def test_new_keys_override_global(self, monkeypatch):
        base = dict(self.BASE)
        base["llm"]["default_reasoning_effort"] = "high"
        base["llm"]["max_context_tokens"] = 8000
        cfg = dict(base)
        cfg["node_llm"] = {"actor_node": {"default_reasoning_effort": "max", "max_context_tokens": 4000}}
        monkeypatch.setattr(config_loader, "load_config", lambda: cfg)
        client = config_loader.get_llm("actor_node")
        assert client.default_reasoning_effort == "max"
        assert client.default_max_context_tokens == 4000
        global_client = config_loader.get_llm()
        assert global_client.default_reasoning_effort == "high"
        assert global_client.default_max_context_tokens == 8000

    def test_new_keys_missing_inherit_global(self, monkeypatch):
        base = dict(self.BASE)
        base["llm"]["default_reasoning_effort"] = "high"
        base["llm"]["max_context_tokens"] = 8000
        cfg = dict(base)
        cfg["node_llm"] = {"actor_node": {"default_model": "node-model"}}
        monkeypatch.setattr(config_loader, "load_config", lambda: cfg)
        client = config_loader.get_llm("actor_node")
        assert client.default_reasoning_effort == "high"
        assert client.default_max_context_tokens == 8000

    def test_new_keys_empty_inherit_global_zero_disables_trim(self, monkeypatch):
        """Empty reasoning_effort inherits the global; max_context_tokens=0 at
        the node_llm layer means "node disables trimming" (0 = no trim).
        / 空串思考强度继承全局；node_llm 层 max_context_tokens=0 表示该节点
          禁用上下文裁剪（0 = 不裁剪）。
        """
        base = dict(self.BASE)
        base["llm"]["default_reasoning_effort"] = "high"
        base["llm"]["max_context_tokens"] = 8000
        cfg = dict(base)
        cfg["node_llm"] = {"actor_node": {"default_reasoning_effort": "", "max_context_tokens": 0}}
        monkeypatch.setattr(config_loader, "load_config", lambda: cfg)
        client = config_loader.get_llm("actor_node")
        assert client.default_reasoning_effort == "high"
        assert client.default_max_context_tokens == 0


class TestMemorySummarizeInterval:
    def test_default_10(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert get_memory_summarize_interval() == 10

    def test_reads_from_features(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"features": {"memory_summarize_interval": 5}},
        )
        assert get_memory_summarize_interval() == 5

    @pytest.mark.parametrize("bad", [0, -3, "abc", None])
    def test_invalid_falls_back_to_10(self, monkeypatch, bad):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"features": {"memory_summarize_interval": bad}},
        )
        assert get_memory_summarize_interval() == 10


class TestEmbeddingModelPath:
    @pytest.fixture(autouse=True)
    def _clear_embedding_cache(self):
        config_loader.clear_cache(embedding_model_path=True)
        yield
        config_loader.clear_cache(embedding_model_path=True)

    def test_default_when_missing(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert config_loader.get_embedding_model_path() == str(
            paths.PROJECT_ROOT / config_loader.EMBEDDING_MODEL_PATH_DEFAULT
        )

    def test_reads_from_embedding_section(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"embedding": {"model_path": "/data/my-embedding"}},
        )
        # 绝对路径保持绝对（Windows 下 pathlib 会补驱动器前缀，故断言 isabs）
        assert os.path.isabs(config_loader.get_embedding_model_path())

    @pytest.mark.parametrize("bad", [None, "", "   ", 123])
    def test_invalid_falls_back_to_default(self, monkeypatch, bad):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"embedding": {"model_path": bad}},
        )
        assert config_loader.get_embedding_model_path() == str(
            paths.PROJECT_ROOT / config_loader.EMBEDDING_MODEL_PATH_DEFAULT
        )

    def test_cached_until_cleared(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"embedding": {"model_path": "/a"}})
        first = config_loader.get_embedding_model_path()
        assert os.path.isabs(first)
        monkeypatch.setattr(config_loader, "load_config", lambda: {"embedding": {"model_path": "/b"}})
        assert config_loader.get_embedding_model_path() == first  # 仍走缓存
        config_loader.clear_cache(embedding_model_path=True)
        second = config_loader.get_embedding_model_path()
        assert os.path.isabs(second)
        assert second != first


class TestSystemRules:
    @pytest.fixture(autouse=True)
    def _clear_system_rules_cache(self):
        config_loader.clear_cache()
        yield
        config_loader.clear_cache()

    def test_falls_back_to_default_constant(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        monkeypatch.setattr(config_loader, "_load_default_config", lambda: {})
        assert config_loader.get_system_rules() == config_loader.SYSTEM_RULES

    def test_reads_defaultconfig(self, monkeypatch):
        default_rules = "默认规则"
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        monkeypatch.setattr(config_loader, "_load_default_config", lambda: {"system_rules": default_rules})
        assert config_loader.get_system_rules() == default_rules

    def test_config_override_wins(self, monkeypatch):
        default_rules = "默认规则"
        custom_rules = "自定义规则"
        monkeypatch.setattr(
            config_loader, "load_config", lambda: {"system_rules": custom_rules}
        )
        monkeypatch.setattr(config_loader, "_load_default_config", lambda: {"system_rules": default_rules})
        assert config_loader.get_system_rules() == custom_rules

    def test_repo_ships_no_builtin_rules(self, monkeypatch):
        """The repo must not ship any shared system rules: when all three
        sources are empty, get_system_rules() returns "" and build_node_prompt
        appends nothing (empty string is falsy).

        Regression guard against re-introducing rule text into the repo.
        / 仓库不得内置共享限制：三处来源皆空时返回空串，build_node_prompt
          不追加任何内容（空串为假值）。防止规则文本被重新塞回仓库。
        """
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        monkeypatch.setattr(config_loader, "_load_default_config", lambda: {})
        assert config_loader.SYSTEM_RULES == ""
        assert config_loader.get_system_rules() == ""
        prompt = config_loader.build_node_prompt("nonexistent_node", "主体：{a}", a="A")
        assert prompt == "主体：A"

    def test_defaultconfig_carries_no_rule_text(self):
        """Check the real file (no monkeypatch): defaultconfig.json must not
        embed any rule text, otherwise every clone would inherit it.

        / 直接检查仓库文件（不走 monkeypatch）：defaultconfig.json 不得内嵌
          任何规则文本，否则每个 clone 都会继承。
        """
        cfg = config_loader._load_default_config()
        assert cfg.get("system_rules", "") == ""
        assert "【系统限制】" not in json.dumps(cfg, ensure_ascii=False)


class TestBuildNodePrompt:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        config_loader.clear_cache()
        yield
        config_loader.clear_cache()

    def _setup(self, monkeypatch, *, rules="【系统限制】测试规则", prompts=None):
        monkeypatch.setattr(
            config_loader, "load_config", lambda: {"system_rules": rules, "node_prompts": prompts or {}}
        )
        monkeypatch.setattr(config_loader, "_load_default_config", lambda: {"system_rules": rules})

    def test_appends_rules(self, monkeypatch):
        self._setup(monkeypatch)
        prompt = config_loader.build_node_prompt("nonexistent_node", "主体：{a}", a="A")
        assert prompt == "主体：A\n\n【系统限制】测试规则"

    def test_no_double_append_when_embedded(self, monkeypatch):
        self._setup(monkeypatch)
        rules = config_loader.get_system_rules()
        template = f"主体：{{a}}\n\n{rules}"
        prompt = config_loader.build_node_prompt("nonexistent_node", template, a="A")
        assert prompt.count("【系统限制】") == 1

    def test_config_prompt_override_used(self, monkeypatch):
        self._setup(monkeypatch, prompts={"actor_node": "自定义提示词 {a}"})
        prompt = config_loader.build_node_prompt("actor_node", "默认模板 {a}", a="A")
        assert prompt.startswith("自定义提示词 A")

    def test_respect_override_false_ignores_config_prompt(self, monkeypatch):
        self._setup(monkeypatch, prompts={"actor_node": "自定义提示词 {a}"})
        prompt = config_loader.build_node_prompt(
            "actor_node", "默认模板 {a}", respect_override=False, a="A"
        )
        assert prompt.startswith("默认模板 A")


class TestSetupConfig:
    """First-run wizard state: `setup` section of config.json plus the
    "is the LLM actually configured" probe.
    / 首次引导状态：config.json 的 setup 段，以及「模型是否真的配置过」探测。
    """

    @pytest.fixture(autouse=True)
    def _clear_setup_cache(self):
        config_loader.clear_cache(setup=True)
        yield
        config_loader.clear_cache(setup=True)

    def test_missing_section_means_not_completed(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert config_loader.get_setup_config() == {}
        assert config_loader.is_setup_completed() is False

    def test_malformed_section_means_not_completed(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"setup": "yes"})
        assert config_loader.get_setup_config() == {}
        assert config_loader.is_setup_completed() is False

    def test_completed_flag(self, monkeypatch):
        monkeypatch.setattr(
            config_loader, "load_config", lambda: {"setup": {"completed": True, "completed_at": "2026-08-30T10:00:00"}}
        )
        assert config_loader.is_setup_completed() is True

    def test_cached_until_cleared(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"setup": {"completed": True}})
        assert config_loader.is_setup_completed() is True
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert config_loader.is_setup_completed() is True  # 仍走缓存
        config_loader.clear_cache(setup=True)
        assert config_loader.is_setup_completed() is False

    def test_clear_cache_does_not_clear_setup_by_default(self, monkeypatch):
        """clear_cache() must not invalidate the setup flag unless asked to —
        otherwise an unrelated config write could re-show the wizard.
        / 默认 clear_cache() 不得清掉 setup 标记，否则任何一次配置写入都会让
          引导重新弹出。"""
        monkeypatch.setattr(config_loader, "load_config", lambda: {"setup": {"completed": True}})
        assert config_loader.is_setup_completed() is True
        config_loader.clear_cache()
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert config_loader.is_setup_completed() is True

    @pytest.mark.parametrize("api_key", ["", "   ", None])
    def test_empty_api_key_is_unconfigured(self, monkeypatch, api_key):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"llm": {"api_key": api_key}})
        assert config_loader.is_llm_configured() is False

    @pytest.mark.parametrize("placeholder", ["your-api-key-here", "YOUR_API_KEY", "sk-xxx"])
    def test_placeholder_api_key_is_unconfigured(self, monkeypatch, placeholder):
        """A fresh copy of config.template.json must report "not configured".
        / 直接复制 config.template.json 得到的配置必须判定为「未配置」。"""
        monkeypatch.setattr(config_loader, "load_config", lambda: {"llm": {"api_key": placeholder}})
        assert config_loader.is_llm_configured() is False

    def test_real_api_key_is_configured(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"llm": {"api_key": "sk-real-key"}})
        assert config_loader.is_llm_configured() is True

    def test_missing_llm_section_is_unconfigured(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert config_loader.is_llm_configured() is False


class TestProtocolSelection:
    """build_llm_client must pick the client class by `protocol`, defaulting to
    the OpenAI-compatible client when absent / empty / unknown.
    / build_llm_client 必须按 protocol 选择客户端类；缺省/空串/未知值时回退 OpenAI 客户端。
    """

    @pytest.fixture(autouse=True)
    def _clear_llm_cache(self):
        config_loader.clear_cache()
        yield
        config_loader.clear_cache()

    def test_anthropic_protocol_returns_anthropic_client(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"llm": {"protocol": "anthropic", "api_key": "sk-ant", "default_model": "claude-sonnet"}},
        )
        client = config_loader.get_llm()
        assert isinstance(client, AnthropicLLMClient)
        assert client.default_model == "claude-sonnet"

    def test_missing_protocol_falls_back_to_openai(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"llm": {"api_key": "sk-test", "default_model": "gpt-4o-mini"}},
        )
        assert isinstance(config_loader.get_llm(), LLMStreamClient)

    def test_empty_protocol_falls_back_to_openai(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"llm": {"protocol": "", "api_key": "sk-test"}},
        )
        assert isinstance(config_loader.get_llm(), LLMStreamClient)

    def test_unknown_protocol_falls_back_to_openai(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {"llm": {"protocol": "gemini", "api_key": "sk-test"}},
        )
        assert isinstance(config_loader.get_llm(), LLMStreamClient)

    def test_node_llm_protocol_override_wins(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {
                "llm": {"protocol": "openai", "api_key": "sk-global"},
                "node_llm": {"actor_node": {"protocol": "anthropic", "api_key": "sk-ant"}},
            },
        )
        assert isinstance(config_loader.get_llm("actor_node"), AnthropicLLMClient)
        assert isinstance(config_loader.get_llm(), LLMStreamClient)

    def test_node_llm_empty_protocol_inherits_global(self, monkeypatch):
        monkeypatch.setattr(
            config_loader,
            "load_config",
            lambda: {
                "llm": {"protocol": "anthropic", "api_key": "sk-ant"},
                "node_llm": {"actor_node": {"protocol": "", "api_key": "sk-ant"}},
            },
        )
        assert isinstance(config_loader.get_llm("actor_node"), AnthropicLLMClient)

    def test_protocol_change_rebuilds_client(self, monkeypatch):
        configs = iter(
            [
                {"llm": {"protocol": "openai", "api_key": "sk-test"}},
                {"llm": {"protocol": "anthropic", "api_key": "sk-ant"}},
            ]
        )
        monkeypatch.setattr(config_loader, "load_config", lambda: next(configs))
        first = config_loader.get_llm()
        assert isinstance(first, LLMStreamClient)
        second = config_loader.get_llm()
        assert isinstance(second, AnthropicLLMClient)
        assert second is not first
