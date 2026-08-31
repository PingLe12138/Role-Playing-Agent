"""Tests for RPA_langGraph/nodes/image_gen_node.py.

The node touches config, SQLite, SSE and ComfyUI — all mocked here so the
tests only exercise the node's decision flow and its failure policy (the node
must NEVER break the narrative).

/ RPA_langGraph/nodes/image_gen_node.py 的流程测试。节点依赖配置、SQLite、
  SSE 与 ComfyUI——此处全部 mock，仅测试节点的判定流程与失败策略
  （节点绝不能破坏剧情）。
"""

import json
from unittest import mock

from langchain_core.messages import AIMessage
import pytest

from RPA_langGraph.nodes import image_gen_node
from RPA_langGraph.nodes.image_gen_node import image_gen_node as node_entry

SCENE_ROW_SQL = (
    "INSERT INTO session_history "
    "(sessionHistoryID, parentID, role, createdBy, content, recordCreatedTime, recordUpdatedTime) "
    "VALUES (?, ?, 'scene_image', 'scene_image', ?, ?, ?)"
)

ACTOR_CONTENT = json.dumps(
    {
        "contentType": "actor_response",
        "content": json.dumps(
            {
                "action": "推开沉重的大门",
                "inner_thought": "这里有些不对劲",
                "speech": "我们到了。",
            },
            ensure_ascii=False,
        ),
    },
    ensure_ascii=False,
)


def make_state(**overrides):
    state = {
        "sessionID": "s1",
        "sessionEnvData": {"location": "城堡大厅", "time": "黄昏", "atmosphere": "烛光摇曳"},
        # directorGraphOutput is cleared by review_departure_node before this
        # node runs — mimic the real timeline: it is empty here, the turn
        # content lives in sessionHistory.
        # / directorGraphOutput 已被 review_departure_node 清空——模拟真实时序：
        #   此处为空，回合内容在 sessionHistory 中。
        "directorGraphOutput": [],
        "sessionHistory": [AIMessage(content=ACTOR_CONTENT)],
    }
    state.update(overrides)
    return state


def make_cfg(**overrides):
    cfg = {
        "enabled": True,
        "comfyui_base_url": "http://127.0.0.1:8188",
        "checkpoint": "animagine-xl-4.0.safetensors",
        "width": 896,
        "height": 1152,
        "steps": 30,
        "cfg": 6.0,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras",
        "negative_prompt": "lowres",
        "interval_seconds": 180,
        "max_per_session": 30,
        "llm_decision_enabled": True,
        "timeout_seconds": 300,
        "poll_interval_seconds": 1.0,
    }
    cfg.update(overrides)
    return cfg


class FakeComfyClient:
    """Stand-in for ComfyUIClient that returns a canned result.
    / ComfyUIClient 的替身，返回固定结果。"""

    def __init__(self, base_url="http://127.0.0.1:8188"):
        self.base_url = base_url

    def generate(self, prompt, negative, **kwargs):
        return {
            "url": "/static/scene_images/s1/scene.png",
            "filename": "scene.png",
            "prompt_id": "p1",
            "seed": 1,
        }


@pytest.fixture
def base_mocks(db):
    """Patch the node's DB + SSE publisher so no real services are touched.
    / 替换节点的 DB 与 SSE 发布器，避免触碰真实服务。"""
    with mock.patch.object(image_gen_node, "get_db", return_value=db), mock.patch.object(
        image_gen_node, "publisher"
    ) as pub:
        yield pub


class TestDisabled:
    def test_returns_empty_and_writes_nothing(self, db, base_mocks):
        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value={"enabled": False}
        ):
            result = node_entry(make_state())
        assert result == {}
        assert db.fetchall("SELECT * FROM session_history") == []


class TestLlmDecision:
    def test_llm_no_generate_skips(self, db, base_mocks):
        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value=make_cfg()
        ), mock.patch.object(
            image_gen_node, "_llm_decide", return_value={"generate": False, "reason": "纯对话过渡"}
        ):
            result = node_entry(make_state())
        assert result == {}
        assert db.fetchall("SELECT * FROM session_history") == []

    def test_llm_failure_skips_gracefully(self, db, base_mocks):
        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value=make_cfg()
        ), mock.patch.object(image_gen_node, "_llm_decide", return_value=None):
            result = node_entry(make_state())
        assert result == {}
        assert db.fetchall("SELECT * FROM session_history") == []

    def test_empty_history_skips_as_no_outputs(self, db, base_mocks):
        """Empty sessionHistory → node must skip without calling the LLM.
        / sessionHistory 为空 → 节点应跳过且不调用 LLM（对应真实时序中
          directorGraphOutput 已被清空、history 也没有 AI 消息的情形）。"""
        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value=make_cfg()
        ), mock.patch.object(image_gen_node, "_llm_decide") as decide:
            result = node_entry(make_state(sessionHistory=[]))
        assert result == {}
        decide.assert_not_called()
        assert db.fetchall("SELECT * FROM session_history") == []


class TestHappyPath:
    def test_persists_and_publishes(self, db, base_mocks):
        cfg = make_cfg()
        with mock.patch.object(image_gen_node, "get_image_generation_config", return_value=cfg), mock.patch.object(
            image_gen_node,
            "_llm_decide",
            return_value={
                "generate": True,
                "prompt": "masterpiece, best quality, a castle at dusk, anime style",
                "negative": "",
                "caption": "黄昏下矗立的城堡",
            },
        ) as decide, mock.patch.object(image_gen_node, "ComfyUIClient", return_value=FakeComfyClient()):
            result = node_entry(make_state())

        assert result == {}
        # The scene snapshot fed to the LLM judge must contain the turn text
        # extracted from sessionHistory (not the cleared directorGraphOutput).
        # / 传给 LLM 判定的场景快照必须含从 sessionHistory 提取的回合文本
        #   （而非已被清空的 directorGraphOutput）。
        scene_arg = decide.call_args[0][1]
        assert "推开沉重的大门" in scene_arg
        rows = db.fetchall("SELECT * FROM session_history")
        assert len(rows) == 1
        payload = json.loads(rows[0]["content"])
        assert payload["contentType"] == "scene_image"
        inner = json.loads(payload["content"])
        assert inner["url"] == "/static/scene_images/s1/scene.png"
        assert inner["description"] == "黄昏下矗立的城堡"
        assert inner["prompt"] == "masterpiece, best quality, a castle at dusk, anime style"

        # SSE message event carries the same wrapped payload as the DB row.
        # / SSE message 事件携带与 DB 行相同的包裹格式。
        msg_calls = [c for c in base_mocks.publish.call_args_list if c.args[0] == "message"]
        assert msg_calls
        assert msg_calls[0].args[1]["contentType"] == "scene_image"
        assert json.loads(msg_calls[0].args[1]["content"])["contentType"] == "scene_image"


class TestCooldownAndCap:
    def test_cooldown_skips(self, db, base_mocks):
        db.execute(
            SCENE_ROW_SQL,
            (
                "h0",
                "s1",
                '{"contentType": "scene_image", "content": "{\\"url\\": \\"/static/old.png\\"}"}',
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value=make_cfg(interval_seconds=3600)
        ):
            result = node_entry(make_state())
        assert result == {}
        assert len(db.fetchall("SELECT * FROM session_history")) == 1

    def test_max_per_session_skips(self, db, base_mocks):
        db.execute(
            SCENE_ROW_SQL,
            (
                "h0",
                "s1",
                '{"contentType": "scene_image", "content": "{\\"url\\": \\"/static/old.png\\"}"}',
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value=make_cfg(max_per_session=1)
        ):
            result = node_entry(make_state())
        assert result == {}
        assert len(db.fetchall("SELECT * FROM session_history")) == 1


class TestComfyFailure:
    def test_comfy_error_returns_empty(self, db, base_mocks):
        class BoomClient:
            def __init__(self, base_url="http://127.0.0.1:8188"):
                pass

            def generate(self, prompt, negative, **kwargs):
                from services.comfyui_client import ComfyUIError

                raise ComfyUIError("无法连接 ComfyUI（http://127.0.0.1:8188）")

        with mock.patch.object(
            image_gen_node, "get_image_generation_config", return_value=make_cfg()
        ), mock.patch.object(
            image_gen_node,
            "_llm_decide",
            return_value={"generate": True, "prompt": "x", "negative": "", "caption": "y"},
        ), mock.patch.object(image_gen_node, "ComfyUIClient", return_value=BoomClient()):
            result = node_entry(make_state())

        assert result == {}
        # Failure must not write a scene_image row. / 失败时不写入 scene_image 行。
        assert db.fetchall("SELECT * FROM session_history") == []
