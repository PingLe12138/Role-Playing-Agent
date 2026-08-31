"""Unit tests for services/comfyui_client.py — the ComfyUI REST client.

All network calls are replaced by patching the module-level `_urlopen` hook,
so no real ComfyUI server is required.

/ services/comfyui_client.py（ComfyUI REST 客户端）单元测试。全部网络调用通过
  替换模块级 _urlopen 钩子模拟，无需真实 ComfyUI 服务。
"""

import json
from unittest import mock

import pytest

from services.comfyui_client import ComfyUIClient, ComfyUIError, _build_workflow


class FakeResp:
    """Context-manager response with a fixed payload.
    / 固定负载的上下文管理器响应。"""

    def __init__(self, payload, status=200):
        self._data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def make_router(responses):
    """Build an _urlopen replacement that dispatches on URL substrings.
    / 构造按 URL 子串分发的 _urlopen 替换函数。
    responses: list of (url_part, payload), checked in order."""

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for part, payload in responses:
            if part in url:
                return FakeResp(payload)
        raise AssertionError(f"unexpected URL: {url}")

    return fake_urlopen


def make_raise_urlerror(reason="connection refused"):
    """Build an _urlopen replacement that always raises a real URLError.
    / 构造总是抛出真实 URLError 的 _urlopen 替换函数。"""

    def fake_urlopen(req, timeout=None):
        import urllib.error

        raise urllib.error.URLError(reason)

    return fake_urlopen


class TestBuildWorkflow:
    def test_structure(self):
        wf = _build_workflow(
            checkpoint="animagine-xl-4.0.safetensors",
            prompt="masterpiece, a castle at dusk",
            negative="lowres",
            width=896,
            height=1152,
            steps=30,
            cfg=6.0,
            sampler_name="dpmpp_2m",
            scheduler="karras",
            seed=42,
            filename_prefix="rpa_scene",
        )
        assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
        assert wf["1"]["inputs"]["ckpt_name"] == "animagine-xl-4.0.safetensors"
        assert wf["2"]["inputs"]["text"] == "masterpiece, a castle at dusk"
        assert wf["3"]["inputs"]["text"] == "lowres"
        assert wf["4"]["inputs"] == {"width": 896, "height": 1152, "batch_size": 1}
        k = wf["5"]["inputs"]
        assert k["seed"] == 42
        assert k["steps"] == 30
        assert k["cfg"] == 6.0
        assert k["sampler_name"] == "dpmpp_2m"
        assert k["scheduler"] == "karras"
        assert k["denoise"] == 1.0
        assert wf["6"]["inputs"]["vae"] == ["1", 2]
        assert wf["7"]["inputs"]["filename_prefix"] == "rpa_scene"


class TestHealthCheck:
    def test_success(self):
        client = ComfyUIClient("http://comfy:8188")
        with mock.patch(
            "services.comfyui_client._urlopen",
            make_router([("/system_stats", {"system": {"comfyui_version": "x"}})]),
        ):
            assert client.health_check() is True

    def test_connection_error_raises(self):
        client = ComfyUIClient("http://comfy:8188")

        with mock.patch("services.comfyui_client._urlopen", make_raise_urlerror("connection refused")):
            with pytest.raises(ComfyUIError, match="无法连接"):
                client.health_check()


class TestGenerate:
    def _completed_history(self, prompt_id="abc123", filename="scene.png"):
        return {
            prompt_id: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "9": {"images": [{"filename": filename, "subfolder": "", "type": "output"}]}
                },
            }
        }

    def test_happy_path_saves_image(self, tmp_path):
        client = ComfyUIClient("http://comfy:8188", save_dir=str(tmp_path))
        router = make_router(
            [
                ("/prompt", {"prompt_id": "abc123"}),
                ("/history/abc123", self._completed_history()),
                ("/view", b"\x89PNG fake-image-bytes"),
            ]
        )
        with mock.patch("services.comfyui_client._urlopen", router):
            result = client.generate("a castle", "lowres", session_id="s1")

        assert result["url"] == "/static/scene_images/s1/scene.png"
        assert result["filename"] == "scene.png"
        assert result["prompt_id"] == "abc123"
        assert (tmp_path / "s1" / "scene.png").read_bytes() == b"\x89PNG fake-image-bytes"

    def test_comfyui_error_status_raises(self, tmp_path):
        client = ComfyUIClient("http://comfy:8188", save_dir=str(tmp_path))
        hist = {
            "err1": {
                "status": {
                    "status_str": "error",
                    "completed": True,
                    "messages": [["execution_error", {"exception_message": "CUDA OOM"}]],
                },
                "outputs": {},
            }
        }
        router = make_router([("/prompt", {"prompt_id": "err1"}), ("/history/err1", hist)])
        with mock.patch("services.comfyui_client._urlopen", router):
            with pytest.raises(ComfyUIError, match="生成失败"):
                client.generate("x", "y", session_id="s1")

    def test_timeout_raises(self, tmp_path):
        client = ComfyUIClient("http://comfy:8188", save_dir=str(tmp_path))
        router = make_router(
            [("/prompt", {"prompt_id": "t1"}), ("/history/t1", {})]  # never completes
        )
        with mock.patch("services.comfyui_client._urlopen", router):
            with pytest.raises(ComfyUIError, match="超时"):
                client.generate(
                    "x", "y", session_id="s1", timeout_seconds=0.3, poll_interval_seconds=0.05
                )

    def test_missing_prompt_id_raises(self, tmp_path):
        client = ComfyUIClient("http://comfy:8188", save_dir=str(tmp_path))
        router = make_router([("/prompt", {"error": "validation"})])
        with mock.patch("services.comfyui_client._urlopen", router):
            with pytest.raises(ComfyUIError, match="prompt_id"):
                client.generate("x", "y", session_id="s1")


class TestSaveImage:
    def test_filename_sanitized_never_escapes_subdir(self, tmp_path):
        client = ComfyUIClient("http://comfy:8188", save_dir=str(tmp_path))
        url = client._save_image("s1", "../../evil.png", b"data")
        # basename() strips traversal → the file stays inside s1/.
        # / basename() 去掉路径穿越 → 文件始终保存在 s1/ 内。
        assert url == "/static/scene_images/s1/evil.png"
        assert (tmp_path / "s1" / "evil.png").read_bytes() == b"data"
        assert not (tmp_path / "evil.png").exists()
