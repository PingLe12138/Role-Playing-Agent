"""Regression tests for project-root path anchoring.

The default locations (config / data / chroma / logs / model) used to be
CWD-relative; these tests pin the anchored behavior so the app keeps working
when launched from any directory other than the project root.
/ 项目根路径锚定回归测试：默认位置（配置/数据/向量库/日志/模型）原先是
  CWD 相对路径，本测试固定锚定行为，保证从任意目录启动都可用。
"""

import json
import os
import tempfile

import pytest

import config_loader
import paths
from SQLiteClient import SQLiteClient


class TestPathsConstants:
    def test_project_root_is_absolute(self):
        assert os.path.isabs(str(paths.PROJECT_ROOT))

    def test_subpaths_located_under_project_root(self):
        for p in (paths.CONFIG_PATH, paths.DEFAULT_CONFIG_PATH, paths.DATA_DIR, paths.CHROMA_DIR, paths.LOGS_DIR):
            assert os.path.isabs(str(p))
            assert paths.PROJECT_ROOT in p.parents or p.parent == paths.PROJECT_ROOT


class TestEmbeddingModelPathAnchoring:
    @pytest.fixture(autouse=True)
    def _clear_embedding_cache(self):
        config_loader.clear_cache(embedding_model_path=True)
        yield
        config_loader.clear_cache(embedding_model_path=True)

    def test_relative_value_anchored_to_project_root(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"embedding": {"model_path": "models/MyModel"}})
        result = config_loader.get_embedding_model_path()
        assert os.path.isabs(result)
        assert result == str(paths.PROJECT_ROOT / "models/MyModel")

    def test_absolute_value_stays_as_is(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {"embedding": {"model_path": "/data/my-embedding"}})
        # 绝对路径必须保持绝对（Windows 下 pathlib 会补驱动器前缀，故不断言精确字符串）
        assert os.path.isabs(config_loader.get_embedding_model_path())

    def test_missing_value_falls_back_anchored_default(self, monkeypatch):
        monkeypatch.setattr(config_loader, "load_config", lambda: {})
        assert config_loader.get_embedding_model_path() == str(paths.PROJECT_ROOT / "models/Qwen3-Embedding-0.6B")


class TestResolveModelPath:
    def test_explicit_relative_anchored(self):
        import ChromaDBClient

        assert ChromaDBClient._resolve_model_path("models/Other") == str(paths.PROJECT_ROOT / "models/Other")

    def test_explicit_absolute_stays(self):
        import ChromaDBClient

        assert os.path.isabs(ChromaDBClient._resolve_model_path("/abs/model"))


class TestSqliteAnchoring:
    def test_default_db_dir_anchored(self):
        # 构造但不 connect，避免真实建库
        client = SQLiteClient("t.db")
        assert client.db_dir == str(paths.DATA_DIR)
        assert client.db_path == os.path.join(str(paths.DATA_DIR), "t.db")

    def test_explicit_db_dir_respected(self):
        client = SQLiteClient("t.db", db_dir="custom_data")
        assert client.db_dir == "custom_data"


class TestLoadConfigFromAnywhere:
    def test_load_config_without_cwd_dependency(self, monkeypatch):
        """load_config() must not depend on the CWD: point CONFIG_PATH at a
        temp file, chdir away from the project root, and it still loads.
        / load_config() 不得依赖 CWD：把 CONFIG_PATH 指向临时文件后 chdir 离开
          项目根目录，仍应正常加载。"""
        orig = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"llm": {"api_key": "sk-test"}}, f)
            monkeypatch.setattr(paths, "CONFIG_PATH", cfg_path)
            os.chdir(tmp)
            try:
                result = config_loader.load_config()
            finally:
                # 提前恢复 CWD，否则 Windows 无法删除当前工作目录
                os.chdir(orig)
            assert result["llm"]["api_key"] == "sk-test"

    def test_get_db_and_chroma_resolve_from_anywhere(self, monkeypatch):
        """Parsing must not raise when the CWD is not the project root, and the
        resolved paths must be absolute.
        / 当 CWD 不是项目根时，路径解析不得抛错，且解析结果必须为绝对路径。"""
        orig = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                client = SQLiteClient("t.db")
                import ChromaDBClient

                model_path = ChromaDBClient._resolve_model_path(None)
            finally:
                os.chdir(orig)
            assert os.path.isabs(client.db_dir)
            assert os.path.isabs(model_path)
