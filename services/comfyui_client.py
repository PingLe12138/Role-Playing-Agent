"""ComfyUI API client for scene-image generation.

/ ComfyUI 场景插画生成客户端。

Talks to a locally running ComfyUI server via its REST API (the same
`/prompt` / `/history` / `/view` endpoints the web UI uses) using only the
stdlib (`urllib`) — no extra dependency.  The workflow is a fixed
text-to-image graph in ComfyUI's API format:

    CheckpointLoaderSimple → 2× CLIPTextEncode (positive/negative)
                          → EmptyLatentImage → KSampler → VAEDecode → SaveImage

Generated images are downloaded into `static/scene_images/{session_id}/`
so they keep working even if ComfyUI later goes offline.  Every failure is
raised as `ComfyUIError` with a human-readable message — callers (graph
nodes) must treat it as non-fatal.

/ 通过 ComfyUI 的 REST API（与网页端相同的 /prompt / /history / /view 端点）
  与本机 ComfyUI 通信，仅用标准库 urllib，无额外依赖。工作流为固定文生图
  拓扑的 API 格式。生成的图片下载到 static/scene_images/{session_id}/，
  ComfyUI 后续离线也不影响已生成图片。所有失败以 ComfyUIError 抛出并带
  可读信息——调用方（图节点）必须将其视为非致命错误。
"""

import json
import os
import random
import time
from typing import Any, Dict, Optional
import urllib.error
import urllib.parse
import urllib.request

# Module-level hook for tests to patch without touching urllib directly.
# / 模块级钩子，测试可直接替换而无需打补丁 urllib。
_urlopen = urllib.request.urlopen

# Project static dir (resolved from this file: services/.. → project root).
# / 项目静态目录（由本文件位置解析：services/.. → 项目根）。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SAVE_DIR = os.path.join(_PROJECT_ROOT, "static", "scene_images")


class ComfyUIError(RuntimeError):
    """Raised for any ComfyUI failure (connection, HTTP, timeout, queue).
    / ComfyUI 任何失败（连接、HTTP、超时、队列）均抛出此异常。"""


def _build_workflow(
    *,
    checkpoint: str,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    sampler_name: str,
    scheduler: str,
    seed: int,
    filename_prefix: str,
) -> Dict[str, Any]:
    """Build a text-to-image workflow in ComfyUI's API format.

    / 以 ComfyUI API 格式构建文生图工作流。
    """
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": filename_prefix}},
    }


class ComfyUIClient:
    """Minimal ComfyUI client (submit → poll → download).
    / 极简 ComfyUI 客户端（提交 → 轮询 → 下载）。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8188", save_dir: str = DEFAULT_SAVE_DIR):
        self.base_url = base_url.rstrip("/")
        self.save_dir = save_dir

    # ── low-level HTTP ────────────────────────────────────────────────

    def _request_json(self, path: str, payload: Optional[dict] = None, timeout: float = 10.0) -> Any:
        """Send a JSON request and return the parsed JSON response.
        / 发送 JSON 请求并返回解析后的 JSON 响应。"""
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with _urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            raise ComfyUIError(f"ComfyUI HTTP {e.code}: {body}")
        except urllib.error.URLError as e:
            raise ComfyUIError(f"无法连接 ComfyUI（{self.base_url}）：{e.reason}")
        except (TimeoutError, OSError) as e:
            raise ComfyUIError(f"连接 ComfyUI 超时（{self.base_url}）：{e}")

    def _download(self, path: str, timeout: float = 60.0) -> bytes:
        """Download binary content (used for /view images).
        / 下载二进制内容（用于 /view 图片）。"""
        url = self.base_url + path
        try:
            with _urlopen(url, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise ComfyUIError(f"下载图片失败 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        except urllib.error.URLError as e:
            raise ComfyUIError(f"下载图片失败：{e.reason}")
        except (TimeoutError, OSError) as e:
            raise ComfyUIError(f"下载图片超时：{e}")

    # ── public API ────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Probe the server; raise ComfyUIError if unreachable.
        / 探测服务器连通性；不可达时抛 ComfyUIError。"""
        self._request_json("/system_stats", timeout=5)
        return True

    def generate(
        self,
        prompt: str,
        negative: str,
        *,
        session_id: str = "",
        checkpoint: str = "animagine-xl-4.0.safetensors",
        width: int = 896,
        height: int = 1152,
        steps: int = 30,
        cfg: float = 6.0,
        sampler_name: str = "dpmpp_2m",
        scheduler: str = "karras",
        filename_prefix: str = "rpa_scene",
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate one image and save it under static/scene_images/{session_id}/.

        Returns {"url", "filename", "prompt_id"}.  Raises ComfyUIError on any
        failure (submission, queue error, generation error, timeout).

        / 生成一张图片并保存到 static/scene_images/{session_id}/。
          返回 {"url", "filename", "prompt_id"}；任何失败抛 ComfyUIError。
        """
        seed = seed if seed is not None else random.randrange(0, 2**32)
        workflow = _build_workflow(
            checkpoint=checkpoint,
            prompt=prompt,
            negative=negative,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            sampler_name=sampler_name,
            scheduler=scheduler,
            seed=seed,
            filename_prefix=filename_prefix,
        )

        resp = self._request_json("/prompt", {"prompt": workflow, "client_id": "rpa-agent"}, timeout=15)
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"ComfyUI 未返回 prompt_id：{resp}")

        deadline = time.time() + float(timeout_seconds)
        while True:
            hist = self._request_json(f"/history/{urllib.parse.quote(str(prompt_id))}", timeout=10)
            entry = hist.get(prompt_id) if isinstance(hist, dict) else None
            if entry:
                status = entry.get("status", {}) or {}
                status_str = status.get("status_str", "")
                if status_str == "error" or status.get("completed") is True and status_str == "error":
                    msgs = status.get("messages", [])
                    raise ComfyUIError(f"ComfyUI 生成失败：{json.dumps(msgs[:2], ensure_ascii=False)[:500]}")
                outputs = entry.get("outputs", {}) or {}
                for _nid, out in outputs.items():
                    images = out.get("images", []) or []
                    if images:
                        img = images[0]
                        filename = img.get("filename", "")
                        subfolder = img.get("subfolder", "")
                        img_type = img.get("type", "output")
                        if filename:
                            data = self._download(
                                "/view?"
                                + urllib.parse.urlencode(
                                    {"filename": filename, "subfolder": subfolder, "type": img_type}
                                ),
                                timeout=60,
                            )
                            url = self._save_image(session_id, filename, data)
                            return {"url": url, "filename": filename, "prompt_id": prompt_id, "seed": seed}
                if status.get("completed"):
                    break  # completed without images
            if time.time() >= deadline:
                raise ComfyUIError("ComfyUI 生成超时")
            time.sleep(max(0.1, float(poll_interval_seconds)))

        raise ComfyUIError("ComfyUI 任务完成但未产出图片")

    def _save_image(self, session_id: str, filename: str, data: bytes) -> str:
        """Persist image bytes under static/scene_images/{session_id}/ and
        return the web URL.  / 将图片字节保存到 static/scene_images/{session_id}/ 并返回 URL。"""
        subdir = os.path.join(self.save_dir, session_id)
        os.makedirs(subdir, exist_ok=True)
        # Sanitize the filename so it can never escape the session subdir.
        # / 清洗文件名，确保不会越出会话子目录。
        safe_name = os.path.basename(filename or "scene.png")
        path = os.path.join(subdir, safe_name)
        with open(path, "wb") as f:
            f.write(data)
        return f"/static/scene_images/{session_id}/{safe_name}"
