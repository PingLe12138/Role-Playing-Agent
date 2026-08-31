# -*- coding: utf-8 -*-
"""回归测试：general_narration_node 分块续写的 LLM 失败容错与去重合并。

历史事故：
- 2026-08-17 线上日志中，通用叙事指令带字数要求（"不少于8000字"）时，
  首轮 LLM 调用超时（openai.APITimeoutError），_generate_with_continuation 在
  except 分支 break 后 `return story` 抛 UnboundLocalError，异常逃出节点导致
  整个 LangGraph 调用失败（graph_error）。
- graph_20260817_153255.log（2026-08-17 16:16）：续写轮次把上一轮正文整段
  回抄进输出再续写，旧拼接逻辑导致成品中整段重复；现在由 _merge_chunk 去重，
  并支持"复述锚点改写上一段结尾"的合并语义。
"""
from RPA_langGraph.nodes.general_narration_node import _generate_with_continuation, _merge_chunk


class _RaisingLLM:
    """每次调用都抛异常，模拟 LLM 超时/网络故障。"""

    def chat(self, *args, **kwargs):
        raise RuntimeError("LLM API 请求失败: Request timed out.")


class _FailOnSecond:
    def __init__(self):
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return "第一段已经生成的内容。" * 20
        raise RuntimeError("boom")


class _EnoughLLM:
    def chat(self, *args, **kwargs):
        return "足够长的内容。" * 200


def test_first_round_failure_returns_empty_string():
    """首轮 LLM 调用即失败：应返回空串（由节点标记完成退出），不得抛 UnboundLocalError。"""
    result = _generate_with_continuation(_RaisingLLM(), {}, "prompt", 8000)
    assert result == ""


def test_midway_failure_keeps_generated_content():
    """首轮成功、后续轮失败：保留已生成内容，不丢正文。"""
    llm = _FailOnSecond()
    result = _generate_with_continuation(llm, {}, "prompt", 100000)
    assert result.startswith("第一段已经生成的内容")
    assert len(result) > 100


def test_normal_completion_reaches_target():
    """正常路径：达到目标字数后停止。"""
    result = _generate_with_continuation(_EnoughLLM(), {}, "prompt", 50)
    assert len(result) > 0


# ---- _merge_chunk：续写去重与改写合并 ----

def test_merge_chunk_empty_story_returns_chunk():
    """空正文：直接返回首轮片段。"""
    assert _merge_chunk("", "第一段正文。") == "第一段正文。"


def test_merge_chunk_no_overlap_appends():
    """无重叠：以段落分隔追加。"""
    story = "第一段已经写好的内容。"
    chunk = "完全不同的新内容。"
    assert _merge_chunk(story, chunk) == "第一段已经写好的内容。\n\n完全不同的新内容。"


def test_merge_chunk_whole_story_echo_is_deduplicated():
    """事故重演：续写输出把整段旧文回抄后再写新内容（graph_20260817_153255.log
    形态），应去掉回抄部分、仅追加新内容，正文不丢、不重复。"""
    story = "午后的阳光从仓库楼的窗户照进来。李欣站在台阶上，托着胸部看向王强。"
    new_part = "两人沿着走廊往教室走，李欣忽然停下来转过身。"
    chunk = story + "\n\n" + new_part  # 模型整段回抄 + 续写
    result = _merge_chunk(story, chunk)
    assert result == story + "\n\n" + new_part
    assert result.count(story) == 1


def test_merge_chunk_short_anchor_rewrite_replaces_tail():
    """改写锚点：模型复述结尾一两句作为锚点后改写，应替换锚点之后的旧文段。"""
    story = "阳光从窗外照进来，教室里很安静。李欣坐在座位上，低头翻着课本。王强走进来，脸红红的。李欣抬起头，冲他笑了一下。王强低下头，不敢看她。"
    anchor = "李欣抬起头，冲他笑了一下。王强低下头，不敢看她。"
    revised = "李欣抬起头，冲他笑了一下，随即又收回目光，翻了一页课本。"
    chunk = anchor + revised
    result = _merge_chunk(story, chunk)
    assert result == "阳光从窗外照进来，教室里很安静。李欣坐在座位上，低头翻着课本。王强走进来，脸红红的。" + revised
    # 旧锚点文段已被改写内容替换，不再重复出现
    assert anchor not in result
    assert result.count("李欣抬起头，冲他笑了一下") == 1


class _RepeatingLLM:
    """每轮都返回完全相同的内容，模拟模型回抄前文的病态行为。"""

    def chat(self, *args, **kwargs):
        return "这一段已经写过的内容绝不能重复。" * 10


def test_repeating_rounds_do_not_duplicate():
    """模型每轮回抄相同内容：最终正文只保留一份，不翻倍。"""
    llm = _RepeatingLLM()
    result = _generate_with_continuation(llm, {}, "prompt", 100000)
    chunk = "这一段已经写过的内容绝不能重复。" * 10
    assert result == chunk
    assert result.count(chunk) == 1
