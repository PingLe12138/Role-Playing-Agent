<template>
    <div v-if="parsed && !isPlayerChoice" :class="['msg-wrapper', cssClass, { compact }]">
        <!-- Player Choice Result — context + selected option + result narration -->
        <div v-if="choiceResult" class="msg-bubble msg-choice-result-card">
            <div class="msg-choice-result-label">玩家选择</div>
            <div v-if="choiceResult.choice_context" class="msg-choice-result-context">
                {{ choiceResult.choice_context }}
            </div>
            <div class="msg-choice-result-chose">{{ choiceResult.player_chose }}</div>
            <div v-if="choiceResult.result" class="msg-choice-result-text">{{ choiceResult.result }}</div>
        </div>
        <!-- Scene Image — ComfyUI-generated illustration -->
        <div v-else-if="sceneImage" class="msg-body msg-scene-body">
            <div class="msg-bubble msg-scene-card">
                <div class="msg-scene-label">场景插画</div>
                <el-image
                    :src="sceneImage.url"
                    :preview-src-list="[sceneImage.url]"
                    :preview-teleported="true"
                    fit="cover"
                    class="msg-scene-img"
                />
                <div v-if="sceneImage.description" class="msg-scene-desc">{{ sceneImage.description }}</div>
                <div v-if="sceneImage.prompt" class="msg-scene-prompt">{{ sceneImage.prompt }}</div>
                <div class="msg-meta">
                    <span v-if="msg.recordCreatedTime" class="msg-time">{{ formatTime(msg.recordCreatedTime) }}</span>
                </div>
            </div>
        </div>
        <!-- Normal messages -->
        <div v-else class="msg-body">
            <span v-if="showAvatar" class="msg-avatar" :style="avatarStyle">{{ avatarText }}</span>
            <div class="msg-bubble">
                <div class="msg-header-row">
                    <span v-if="charName" class="msg-header-name" :style="nameColorStyle">{{ charName }}</span>
                    <span v-else class="msg-header-spacer"></span>
                    <el-dropdown v-if="canDelete" trigger="click" @command="handleMoreCommand">
                        <span class="msg-more-btn"><More theme="outline" size="16" fill="currentColor" /></span>
                        <template #dropdown>
                            <el-dropdown-menu>
                                <el-dropdown-item command="delete">删除</el-dropdown-item>
                            </el-dropdown-menu>
                        </template>
                    </el-dropdown>
                </div>
                <div v-if="parsed.action" class="msg-seg msg-action">
                    <Clap theme="outline" size="13" class="msg-seg-icon" />{{ parsed.action }}
                </div>
                <div v-if="parsed.inner_thought" class="msg-seg msg-thought">
                    <ThinkingProblem theme="outline" size="13" class="msg-seg-icon" />{{ parsed.inner_thought }}
                </div>
                <div v-if="parsed.speech" class="msg-seg msg-speech">
                    <Quote theme="outline" size="13" class="msg-seg-icon" />{{ parsed.speech }}
                </div>
                <div v-if="!parsed.action && !parsed.inner_thought && !parsed.speech" class="msg-text">
                    {{ parsed.content }}
                </div>
                <div class="msg-meta">
                    <span v-if="msg.recordCreatedTime" class="msg-time">{{ formatTime(msg.recordCreatedTime) }}</span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed } from "vue";
import { useCharacterStore } from "../stores/characterStore.js";
import { useUserCharacterStore } from "../stores/userCharacterStore.js";
import { More, Clap, ThinkingProblem, Quote } from "@icon-park/vue-next";

const props = defineProps({
    msg: { type: Object, required: true },
    compact: { type: Boolean, default: false }
});
const emit = defineEmits(["delete"]);
const characterStore = useCharacterStore();
const ucStore = useUserCharacterStore();
const canDelete = computed(() => !!props.msg.sessionHistoryID || !!props.msg._tempId);

function handleMoreCommand(cmd) {
    if (cmd === "delete") emit("delete");
}

function tryParse(raw) {
    if (typeof raw !== "string") return { content: String(raw || "") };

    let text = raw.trim();
    if (text.startsWith("```")) {
        const idx = text.indexOf("\n");
        if (idx !== -1) {
            text = text.slice(idx + 1);
            if (text.endsWith("```")) text = text.slice(0, -3);
            text = text.trim();
        }
    }

    const actionTag = text.match(/<action>([\s\S]*?)<\/action>/);
    const innerTag = text.match(/<inner_thought>([\s\S]*?)<\/inner_thought>/);
    const speechTag = text.match(/<speech>([\s\S]*?)<\/speech>/);
    if (actionTag || innerTag || speechTag) {
        return {
            action: actionTag ? actionTag[1].trim() : "",
            inner_thought: innerTag ? innerTag[1].trim() : "",
            speech: speechTag ? speechTag[1].trim() : ""
        };
    }

    try {
        const obj = JSON.parse(text);
        // Detect player_choice content type
        if (obj.contentType === "player_choice") {
            return {
                content: text,
                _choiceType: "player_choice",
                _choiceData: { context: obj.context || "", choices: obj.choices || [] }
            };
        }
        if (obj.contentType === "player_choice_result") {
            return {
                content: text,
                _choiceType: "player_choice_result",
                _choiceResult: {
                    choice_context: obj.choice_context || "",
                    player_chose: obj.player_chose || "",
                    result: obj.result || ""
                }
            };
        }
        if (obj.contentType === "scene_image") {
            // Persisted payload: {"contentType":"scene_image","content":"{...json...}"}
            let scene = { url: "", description: "", prompt: "" };
            try {
                const inner = JSON.parse(obj.content);
                scene = {
                    url: inner.url || "",
                    description: inner.description || "",
                    prompt: inner.prompt || ""
                };
            } catch {
                scene.url = typeof obj.content === "string" ? obj.content : "";
            }
            return {
                content: text,
                _sceneType: "scene_image",
                _sceneData: scene
            };
        }
        if (obj.contentType && obj.content) {
            const inner = obj.content;
            try {
                const innerObj = JSON.parse(inner);
                if (innerObj.action !== undefined) {
                    return {
                        action: innerObj.action || "",
                        inner_thought: innerObj.inner_thought || "",
                        speech: innerObj.speech || ""
                    };
                }
                return { content: inner };
            } catch {
                return { content: inner };
            }
        }
        if (obj.action !== undefined)
            return { action: obj.action || "", inner_thought: obj.inner_thought || "", speech: obj.speech || "" };
        return { content: text };
    } catch {
        return { content: text };
    }
}

const parsed = computed(() => tryParse(props.msg.content));

const isPlayerChoice = computed(() => parsed.value?._choiceType === "player_choice");

const choiceResult = computed(() => {
    if (parsed.value?._choiceType === "player_choice_result") return parsed.value._choiceResult;
    return null;
});

const sceneImage = computed(() => {
    if (parsed.value?._sceneType === "scene_image") return parsed.value._sceneData;
    return null;
});

const cssClass = computed(() => {
    if (parsed.value?._choiceType === "player_choice") return "choice-card";
    if (parsed.value?._choiceType === "player_choice_result") return "choice-result";
    if (parsed.value?._sceneType === "scene_image") return "scene-image";
    if (props.msg.role === "user") return "user";
    if (props.msg.createdBy === "actor" || props.msg.role === "actor" || props.msg.contentType === "actor_response")
        return "actor";
    if (props.msg.role === "narration" || props.msg.createdBy === "narration" || props.msg.contentType === "narration")
        return "narration";
    if (
        props.msg.role === "general_narration" ||
        props.msg.createdBy === "general_narration" ||
        props.msg.contentType === "general_narration"
    )
        return "general-narration";
    return "system";
});

const charName = computed(() => {
    const role = props.msg.role;
    if (!role || role === "user") return "";

    if (role === "narration") return "旁白";
    if (role === "general_narration") return "一般叙述者";

    const npc = characterStore.cards.find((c) => c.characterID === role);
    if (npc) return npc.characterName;

    const uc = ucStore.cards.find((c) => c.userCharacterID === role);
    if (uc) return uc.userCharacterName;

    return role === "actor" ? "角色" : role;
});

const showAvatar = computed(() => !props.compact && (cssClass.value === "user" || cssClass.value === "actor"));

const avatarText = computed(() => {
    if (cssClass.value === "user") return "我";
    const name = charName.value || props.msg.role || "?";
    return name.charAt(0);
});

const avatarStyle = computed(() => {
    if (cssClass.value === "user") {
        return { background: "var(--brand-500, #5d9eff)" };
    }
    const name = charName.value || props.msg.role || "角色";
    let hue = 0;
    for (let i = 0; i < name.length; i++) hue = (hue * 31 + name.charCodeAt(i)) % 360;
    return {
        background: `linear-gradient(135deg, hsl(${hue}, 65%, 62%), hsl(${(hue + 40) % 360}, 70%, 50%))`
    };
});

// 角色名颜色跟随头像色相（更深一档），便于快速辨认说话人
const nameColorStyle = computed(() => {
    if (cssClass.value === "user") return {};
    const name = charName.value || props.msg.role || "角色";
    let hue = 0;
    for (let i = 0; i < name.length; i++) hue = (hue * 31 + name.charCodeAt(i)) % 360;
    return { color: `hsl(${hue}, 52%, 40%)` };
});

function formatTime(t) {
    if (!t) return "";
    try {
        return new Date(t).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    } catch {
        return "";
    }
}
</script>

<style scoped>
.msg-wrapper {
    margin-bottom: 16px;
    display: flex;
    animation: msg-in 0.25s ease-out;
    transition: transform 0.2s ease;
}
.msg-wrapper.compact {
    margin-bottom: 5px;
}
.msg-wrapper:not(.compact):hover {
    transform: translateY(-1px);
}
@keyframes msg-in {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: none;
    }
}
.msg-wrapper.user {
    justify-content: flex-end;
}
.msg-body {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    max-width: 85%;
    min-width: 0;
}
.msg-wrapper.narration .msg-body,
.msg-wrapper.system .msg-body,
.msg-wrapper.general-narration .msg-body {
    justify-content: center;
}
.msg-wrapper.user .msg-body {
    flex-direction: row-reverse;
}
.msg-avatar {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 1px 4px rgba(16, 24, 40, 0.18);
}
.msg-wrapper.user .msg-bubble {
    background: var(--brand-500, #5d9eff);
    color: #fff;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 8px rgba(93, 140, 255, 0.25);
}
.msg-wrapper.user .msg-time {
    color: rgba(255, 255, 255, 0.65);
}
.msg-wrapper.narration {
    justify-content: center;
}
.msg-wrapper.narration .msg-bubble {
    background: var(--el-fill-color, #f6f8fb);
    border: none;
    color: var(--text-secondary, #5b6779);
    font-style: italic;
    max-width: 80%;
    text-align: center;
    border-radius: 14px;
    padding: 9px 18px;
    font-size: 13px;
    box-shadow: none;
    letter-spacing: 0.2px;
}
.msg-wrapper.general-narration {
    justify-content: center;
}
.msg-wrapper.general-narration .msg-bubble {
    background: var(--brand-50, #f0f6ff);
    border: 1px solid var(--brand-100, #e2edff);
    color: var(--text-primary, #1e2a3a);
    max-width: 80%;
    border-radius: 14px;
    padding: 12px 18px;
    font-size: 15px;
}
.msg-wrapper.system {
    justify-content: center;
}
.msg-wrapper.system .msg-bubble {
    background: #fef3e2;
    color: #8a6d3b;
    max-width: 80%;
    border-radius: 12px;
    font-size: 13px;
}
.msg-wrapper.actor .msg-bubble {
    background: #fff;
    border: 1px solid var(--border-light, #e9edf3);
    border-top-left-radius: 4px;
}

.msg-bubble {
    max-width: 100%;
    min-width: 0;
    padding: 10px 14px;
    border-radius: var(--radius-md, 10px);
    box-shadow: var(--shadow-1, 0 1px 2px rgba(16, 24, 40, 0.05));
    line-height: 1.8;
    position: relative;
    transition: box-shadow 0.2s ease;
}
.msg-wrapper:not(.compact):hover .msg-bubble {
    box-shadow: var(--shadow-2, 0 4px 16px rgba(16, 24, 40, 0.06));
}
.msg-wrapper.narration:not(.compact):hover .msg-bubble {
    box-shadow: none;
}
.msg-header-row {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 4px;
}
.msg-header-name {
    flex: 1;
    font-size: 12px;
    font-weight: 600;
    color: var(--brand-600, #4a8af2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
}
.msg-header-spacer {
    flex: 1;
}
.msg-more-btn {
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    color: var(--text-muted, #909399);
    transition: background-color 0.15s;
    flex-shrink: 0;
}
.msg-more-btn:hover {
    background: rgba(0, 0, 0, 0.06);
    color: var(--brand-500, #5d9eff);
}
.msg-seg {
    display: flex;
    align-items: flex-start;
    gap: 6px;
}
.msg-seg-icon {
    flex-shrink: 0;
    margin-top: 3px;
}
.msg-action {
    color: #8a6d3b;
    font-size: 13px;
    background: #fdf8ee;
    border-radius: 6px;
    padding: 3px 8px;
    margin: 2px 0;
}
.msg-action .msg-seg-icon {
    color: #d9a441;
}
.msg-thought {
    color: #909399;
    font-style: italic;
    font-size: 13px;
    background: #f7f8fa;
    border-radius: 6px;
    padding: 3px 8px;
    margin: 2px 0;
}
.msg-thought .msg-seg-icon {
    color: #9aa5b1;
}
.msg-speech {
    font-size: 14px;
    margin-top: 2px;
}
.msg-speech .msg-seg-icon {
    color: #5d9eff;
}
.msg-text {
    font-size: 14px;
    white-space: pre-wrap;
}
.msg-meta {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 4px;
}
.msg-time {
    font-size: 11px;
    color: #c0c4cc;
}
/* Player Choice Result card */
.msg-wrapper.choice-result {
    justify-content: center;
}
.msg-choice-result-card {
    background: #fff;
    border: 1px solid var(--brand-100, #e2edff);
    box-shadow: var(--shadow-1, 0 1px 2px rgba(16, 24, 40, 0.05));
    max-width: 75%;
    border-radius: 14px;
    padding: 14px 18px;
}
.msg-choice-result-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--brand-600, #4a8af2);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 10px;
    text-align: center;
}
.msg-choice-result-context {
    font-size: 13px;
    color: var(--text-muted, #909399);
    margin-bottom: 10px;
    text-align: center;
    font-style: italic;
    line-height: 1.6;
}
.msg-choice-result-chose {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
    margin-bottom: 10px;
    padding: 6px 12px;
    background: var(--brand-50, #f0f6ff);
    border-radius: 8px;
    border-left: 3px solid var(--brand-500, #5d9eff);
}
.msg-choice-result-text {
    font-size: 14px;
    color: var(--text-primary, #1e2a3a);
    line-height: 1.8;
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--border-light, #e9edf3);
}
/* Scene Image card */
.msg-wrapper.scene-image {
    justify-content: center;
}
.msg-scene-body {
    max-width: 92%;
}
.msg-scene-card {
    background: #fff;
    border: 1px solid var(--border-light, #e9edf3);
    max-width: 430px;
    width: 100%;
    border-radius: 14px;
    padding: 14px;
    text-align: center;
}
.msg-scene-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--brand-500, #5d9eff);
    letter-spacing: 2px;
    margin-bottom: 10px;
}
.msg-scene-img {
    width: 100%;
    max-height: 480px;
    border-radius: 8px;
    cursor: zoom-in;
    box-shadow: 0 2px 12px rgba(16, 24, 40, 0.12);
    background: var(--el-fill-color-light, #f6f8fb);
}
.msg-scene-desc {
    font-size: 13px;
    color: var(--text-secondary, #5b6779);
    margin-top: 10px;
    line-height: 1.6;
}
.msg-scene-prompt {
    font-size: 11px;
    color: var(--text-muted, #909399);
    margin-top: 8px;
    padding: 6px 8px;
    background: var(--el-fill-color-light, #f6f8fb);
    border-radius: 6px;
    line-height: 1.5;
    word-break: break-all;
    white-space: pre-wrap;
    text-align: left;
    font-family: var(--font-mono, "JetBrains Mono", Consolas, monospace);
}
</style>
