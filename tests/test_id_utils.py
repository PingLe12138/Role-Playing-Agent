from services.id_utils import (
    generate_character_id,
    generate_history_id,
    generate_memory_id,
    generate_session_id,
    generate_user_character_id,
    generate_wvc_id,
    generate_wve_id,
    name_to_pinyin,
    new_id,
)


class TestNewId:
    def test_has_prefix(self):
        result = new_id("test")
        assert result.startswith("test_")

    def test_unique(self):
        ids = {new_id("x") for _ in range(100)}
        assert len(ids) == 100


class TestNameToPinyin:
    def test_chinese_name(self):
        result = name_to_pinyin("\u6c99\u7279")
        assert result  # e.g. "sha_te"

    def test_empty_name(self):
        assert name_to_pinyin("") == "unknown"

    def test_none_name(self):
        assert name_to_pinyin(None) == "unknown"


class TestGenerateCharacterId:
    def test_format(self):
        result = generate_character_id("\u6c99\u7279")
        assert result.startswith("char_")
        parts = result.split("_")
        assert len(parts) >= 3


class TestGenerateUserCharacterId:
    def test_format(self):
        result = generate_user_character_id("\u7528\u6237")
        assert result.startswith("uchr_")


class TestGenerateWvcId:
    def test_format(self):
        result = generate_wvc_id("\u4e2d\u4e16\u754c")
        assert result.startswith("wvc_")


class TestGenerateWveId:
    def test_format(self):
        result = generate_wve_id()
        assert result.startswith("wve_")


class TestGenerateSessionId:
    def test_format(self):
        assert generate_session_id().startswith("ses_")


class TestGenerateHistoryId:
    def test_format(self):
        assert generate_history_id().startswith("hst_")


class TestGenerateMemoryId:
    def test_format(self):
        assert generate_memory_id().startswith("mem_")
