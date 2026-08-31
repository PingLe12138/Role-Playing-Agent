MEMORY_PROMPT = """你是一个角色扮演系统的记忆节点。
根据对话历史和角色信息，为每个角色生成一段记忆。

要求：
1. 用第一人称（"我"）叙述该角色最近经历的事情
2. 只描述该角色亲自目睹或亲身参与的内容
3. 每个角色记忆简洁具体，1-3句话

=== 角色信息 ===
{character_card}

=== 角色当前情绪 ===
{emotion_state}

=== 该角色已有的记忆 ===
{existing_memories}

=== 最近的对话历史 ===
{history}

请生成一段记忆文本，用第一人称叙述。"""

# 仓库不再内置任何共享系统限制：clone 后默认为空，由使用者自行填写。
# 保留常量名是为了维持 get_system_rules() 的兜底位置与既有导入/测试；
# 使用者的规则写在 config.json 的 `system_rules`（该文件已被 gitignore）。
# / The repo ships no built-in shared system rules; the name is kept so the
#   fallback slot in config_loader stays valid. Users put their own rules in
#   config.json `system_rules` (gitignored).
SYSTEM_RULES = ""
