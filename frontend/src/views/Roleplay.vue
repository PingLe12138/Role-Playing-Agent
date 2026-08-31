<template>
    <div v-if="!store.currentSession" class="session-empty">
        <h3>会话未找到</h3>
        <el-button type="primary" @click="$router.push('/sessions')" style="margin-top: 16px">返回会话列表</el-button>
    </div>
    <div v-else class="roleplay-layout">
        <div class="rp-sidebar">
            <div class="rp-sidebar-header">
                <h4 class="rp-session-title">
                    <Comments theme="outline" size="15" class="rp-session-icon" />{{
                        store.currentSession.sessionTitle
                    }}
                </h4>
            </div>
            <div class="rp-divider"></div>
            <div class="rp-session-info">
                <div class="rp-info-title">
                    会话信息
                    <el-button
                        size="small"
                        text
                        class="rp-env-edit-btn"
                        :disabled="store.streaming || !!store.currentChoice"
                        @click="openEnvDialog"
                    >
                        <Edit theme="outline" size="14" />
                    </el-button>
                </div>
                <div class="rp-info-body">
                    <div v-if="sessionEnvInfo.location" class="rp-info-row">
                        <Local theme="outline" size="14" class="rp-info-icon" /> {{ sessionEnvInfo.location }}
                    </div>
                    <div v-if="sessionEnvInfo.time" class="rp-info-row">
                        <Time theme="outline" size="14" class="rp-info-icon" /> {{ sessionEnvInfo.time }}
                    </div>
                    <div v-if="sessionEnvInfo.atmosphere" class="rp-info-row">
                        <Magic theme="outline" size="14" class="rp-info-icon" /> {{ sessionEnvInfo.atmosphere }}
                    </div>
                </div>
                <div v-if="presentChars.length" class="rp-chars-section">
                    <div class="rp-info-title">在场角色</div>
                    <div class="rp-chars-tags">
                        <span
                            v-for="cid in presentChars"
                            :key="cid"
                            class="rp-char-pill"
                            :style="charPillStyle(cid)"
                        >
                            <i class="rp-char-dot"></i>{{ charNameMap[cid] || cid }}
                            <button
                                class="rp-char-close"
                                title="移出场景"
                                @click="handleRemoveCharacter(cid)"
                            >
                                <CloseSmall theme="outline" size="12" />
                            </button>
                        </span>
                    </div>
                </div>
            </div>
        </div>
        <div class="rp-main">
            <div class="rp-toolbar">
                <el-button size="small" text @click="$router.push('/sessions')"
                    ><Back theme="outline" size="16" /> 返回</el-button
                >
                <span class="rp-sse-badge" :class="connected ? 'is-on' : 'is-off'">
                    <i class="rp-sse-dot"></i>{{ connected ? "已连接" : "重连中..." }}
                </span>
                <el-button size="small" text class="rp-graph-btn" @click="graphVisible = true"
                    ><MindMapping theme="outline" size="16" /> 图结构</el-button
                >
                <el-button size="small" text type="danger" class="rp-clear-btn" @click="handleClear"
                    ><Delete theme="outline" size="14" /> 清空对话</el-button
                >
            </div>
            <div class="rp-messages" ref="msgContainer">
                <div class="rp-messages-inner">
                    <div v-if="!store.messages.length && !store.streaming" class="rp-empty">
                        <span class="rp-empty-icon"><Comments theme="outline" size="32" /></span>
                        <h4 class="rp-empty-title">故事即将开始</h4>
                        <p class="rp-empty-desc">
                            在下方输入你的行动或对话，AI 将驱动场景中的角色与你共同演绎剧情。
                        </p>
                    </div>
                    <template v-for="(msg, i) in store.messages" :key="i">
                        <div v-if="showDateDivider(i)" class="rp-date-divider">
                            {{ formatDay(msg.recordCreatedTime) }}
                        </div>
                        <RoleplayMessage
                            :msg="msg"
                            :compact="isCompact(i)"
                            @delete="handleDeleteMessage(msg)"
                        />
                    </template>
                    <div v-if="store.streaming" class="rp-streaming-bar">
                        <span class="rp-typing-dots"><i></i><i></i><i></i></span>
                        {{ store.statusText || "正在生成回复..." }}
                    </div>
                </div>
            </div>
            <div v-if="store.currentChoice" class="rp-choice-panel">
                <div class="rp-choice-head">
                    <Compass theme="outline" size="15" class="rp-choice-head-icon" />玩家抉择
                </div>
                <div class="rp-choice-context">{{ store.currentChoice.context }}</div>
                <div class="rp-choice-buttons">
                    <button
                        v-for="c in store.currentChoice.choices"
                        :key="c.id"
                        class="rp-choice-btn"
                        @click="handleSendChoice(c.text)"
                    >
                        {{ c.text }}
                    </button>
                    <button class="rp-choice-btn rp-choice-cancel" @click="handleCancelChoice">取消</button>
                </div>
            </div>
            <div class="rp-input-area">
                <RoleplayInput :disabled="store.streaming || !!store.currentChoice" @send="handleSend" />
            </div>
        </div>
        <el-dialog v-model="envDialogVisible" title="编辑场景环境" width="420px" @open="openEnvDialog">
            <el-form label-width="60px">
                <el-form-item label="地点">
                    <el-input v-model="editEnvForm.location" placeholder="场景所在地点" />
                </el-form-item>
                <el-form-item label="时间">
                    <el-input v-model="editEnvForm.time" placeholder="如：清晨、黄昏、深夜" />
                </el-form-item>
                <el-form-item label="氛围">
                    <el-input v-model="editEnvForm.atmosphere" placeholder="如：安静、紧张、欢快" />
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="envDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="saveEnv" :loading="savingEnv">保存</el-button>
            </template>
        </el-dialog>
        <GraphView :visible="graphVisible" :active-nodes="activeNodes" @close="graphVisible = false" />
    </div>
</template>

<script setup>
defineOptions({ name: "Roleplay" });
import { ref, reactive, computed, onMounted, onActivated, nextTick } from "vue";
import { useRoute, onBeforeRouteUpdate } from "vue-router";
import { Back, Local, Time, Magic, MindMapping, Edit, Comments, CloseSmall, Delete, Compass } from "@icon-park/vue-next";
import { ElMessage, ElMessageBox, ElNotification } from "element-plus";
import { useSessionStore } from "../stores/sessionStore.js";
import { useCharacterStore } from "../stores/characterStore.js";
import { useUserCharacterStore } from "../stores/userCharacterStore.js";
import { useSSE } from "../composables/useSSE.js";
import RoleplayMessage from "../components/RoleplayMessage.vue";
import RoleplayInput from "../components/RoleplayInput.vue";
import GraphView from "../components/GraphView.vue";
import { submitPlayerChoice, cancelPlayerChoice } from "../api/chat.js";

const route = useRoute();
const store = useSessionStore();
const characterStore = useCharacterStore();
const ucStore = useUserCharacterStore();
const msgContainer = ref(null);
const sessionEnvInfo = computed(() => {
    const raw = store.currentSession?.sessionEnvData;
    if (!raw) return {};
    if (typeof raw === "string") {
        try {
            return JSON.parse(raw);
        } catch {
            return {};
        }
    }
    return raw;
});

const presentChars = computed(() => {
    const raw = store.currentSession?.sessionPresentCharacter;
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === "string") {
        try {
            return JSON.parse(raw);
        } catch {
            return raw
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean);
        }
    }
    return [];
});

const charNameMap = computed(() => {
    const map = {};
    for (const c of characterStore.cards) map[c.characterID] = c.characterName;
    for (const c of ucStore.cards) map[c.userCharacterID] = c.userCharacterName;
    return map;
});

const activeNodes = reactive({});
const graphVisible = ref(false);

// ---- 本轮图运行通知状态 ----
// roundStarted：本轮图是否真正开始运行（node_start 置位，graph_complete 消费并复位）
// roundHadError：本轮是否出错（graph_error 置位，graph_complete 消费并复位）
const roundStarted = ref(false);
const roundHadError = ref(false);

function isCompact(i) {
    if (i === 0) return false;
    const prev = store.messages[i - 1];
    const cur = store.messages[i];
    return roleKey(prev) === roleKey(cur);
}

function formatDay(t) {
    if (!t) return "";
    try {
        return new Date(t).toLocaleDateString("zh-CN", {
            year: "numeric",
            month: "long",
            day: "numeric",
            weekday: "short"
        });
    } catch {
        return "";
    }
}

function showDateDivider(i) {
    if (i === 0) return true;
    const cur = store.messages[i];
    const prev = store.messages[i - 1];
    const a = cur?.recordCreatedTime;
    const b = prev?.recordCreatedTime;
    if (!a || !b) return false;
    try {
        return new Date(a).toDateString() !== new Date(b).toDateString();
    } catch {
        return false;
    }
}

function roleKey(m) {
    return m.role || m.createdBy || m.contentType || "";
}

function charPillStyle(cid) {
    const isUser = cid === store.currentSession?.userCharacterID;
    if (isUser) {
        return {
            background: "#e9f2ff",
            border: "1px solid #cfe1ff",
            color: "#2f5fb8",
            "--pill-dot": "#3a72d4",
            "--pill-close": "#3a72d4"
        };
    }
    return {
        background: "#eef4ff",
        border: "1px solid #d6e4ff",
        color: "#3a6fd8",
        "--pill-dot": "#5d9eff",
        "--pill-close": "#5d9eff"
    };
}

const envDialogVisible = ref(false);
const savingEnv = ref(false);
const editEnvForm = reactive({ location: "", time: "", atmosphere: "" });

function openEnvDialog() {
    const raw = store.currentSession?.sessionEnvData;
    let data = {};
    if (typeof raw === "string") {
        try { data = JSON.parse(raw); } catch { data = {}; }
    } else if (raw) {
        data = raw;
    }
    editEnvForm.location = data.location || "";
    editEnvForm.time = data.time || "";
    editEnvForm.atmosphere = data.atmosphere || "";
    envDialogVisible.value = true;
}

async function saveEnv() {
    savingEnv.value = true;
    try {
        await store.updateSessionEnvData({ ...editEnvForm });
        envDialogVisible.value = false;
        ElMessage.success("环境数据已更新");
    } catch (e) {
        ElMessage.error(e.message || "更新失败");
    } finally {
        savingEnv.value = false;
    }
}

async function loadSession() {
    const sid = route.params.id;
    await store.loadSession(sid);
}

onMounted(() => {
    loadSession();
    characterStore.load();
    ucStore.load();
    connect("/api/chat/stream");
});

onActivated(() => {
    nextTick(() => scrollToBottom());
});

onBeforeRouteUpdate(async (to, from) => {
    if (to.params.id !== from.params.id) {
        await loadSession();
    }
});

async function handleClear() {
    try {
        await ElMessageBox.confirm("确定清空当前会话的对话历史吗？此操作不可撤销。", "确认");
        await store.clearSessionHistoryAll();
        ElMessage.success("对话已清空");
    } catch {
        /* cancelled */
    }
}

async function handleRemoveCharacter(cid) {
    if (store.streaming) {
        ElMessage.warning("正在生成回复，请稍后再试");
        return;
    }
    const name = charNameMap.value[cid] || cid;
    try {
        await ElMessageBox.confirm(`确定将「${name}」移出当前场景？`, "确认");
        await store.removePresentCharacter(cid);
        ElMessage.success(`已将「${name}」移出场景`);
    } catch {
        /* cancelled */
    }
}

async function handleDeleteMessage(msg) {
    if (store.streaming) {
        ElMessage.warning("正在生成回复，请稍后再试");
        return;
    }
    const id = msg.sessionHistoryID;
    if (id) {
        try {
            await ElMessageBox.confirm("确定删除这条消息？", "确认");
            await store.deleteMessage(id);
        } catch {
            /* cancelled */
        }
    } else if (msg._tempId) {
        store.messages = store.messages.filter((m) => (m.sessionHistoryID || m._tempId) !== (id || msg._tempId));
    }
}

async function handleSend(text) {
    ensureConnected("/api/chat/stream");
    await store.sendMessage(text);
    nextTick(() => scrollToBottom());
}

async function handleSendChoice(text) {
    store.clearChoice();
    try {
        await submitPlayerChoice({
            sessionID: store.currentSessionId,
            choiceText: text
        });
    } catch (e) {
        ElMessage.error(e.message || "选择提交失败（可能已超时）");
    }
}

async function handleCancelChoice() {
    store.clearChoice();
    try {
        await cancelPlayerChoice({
            sessionID: store.currentSessionId
        });
    } catch (e) {
        ElMessage.error(e.message || "取消失败（可能已超时）");
    }
}

const sseHandlers = {
    message(data) {
        if (data.sessionID === store.currentSessionId) {
            store.appendStreamMessage(data);
            nextTick(() => scrollToBottom());
        }
    },
    node_start(data) {
        roundStarted.value = true;
        if (data.node) activeNodes[data.node] = "running";
        store.setStreaming(true);
        if (data.status) store.setStatusText(data.status);
    },
    node_complete(data) {
        if (data.node) activeNodes[data.node] = "completed";
    },
    history_update() {
        nextTick(() => scrollToBottom());
    },
    graph_complete(data) {
        if (data.sessionID === store.currentSessionId) {
            store.setStreaming(false);
            store.setStatusText("");
            // 本轮图运行结束：弹窗通知用户
            if (roundStarted.value) {
                if (!roundHadError.value) {
                    ElNotification({
                        title: "本轮生成完成",
                        message: "剧情已生成完毕，请查看最新内容。",
                        type: "success",
                        duration: 4000,
                        position: "bottom-right"
                    });
                }
                roundStarted.value = false;
                roundHadError.value = false;
            }
        }
        Object.keys(activeNodes).forEach((k) => {
            activeNodes[k] = "idle";
        });
        // NOTE: do NOT clear the choice panel here. A graph_complete may fire
        // before the player has answered (e.g. after the long choice-wait
        // timeout); the panel should stay visible until the player actually
        // responds or cancels. The panel is cleared by:
        //   - player_choice_result message arriving (appendStreamMessage), or
        //   - user clicking a choice / cancel (handleSendChoice / handleCancelChoice)
    },
    graph_error(data) {
        if (data.sessionID === store.currentSessionId) {
            roundHadError.value = true;
            const brief = (data.error || "")
                .split("\n")
                .map((l) => l.trim())
                .find((l) => l) || "图运行失败";
            ElNotification({
                title: "本轮生成失败",
                message: brief.length > 200 ? brief.slice(0, 200) + "…" : brief,
                type: "error",
                duration: 6000,
                position: "bottom-right"
            });
        }
    },
    session_update(data) {
        if (!store.currentSession) return;
        if (data.presentCharacter) {
            store.currentSession.sessionPresentCharacter = data.presentCharacter;
        }
        if (data.envData && !envDialogVisible.value) {
            store.currentSession.sessionEnvData = data.envData;
        }
        if (data.sessionDepartedCharacter) {
            store.currentSession.sessionDepartedCharacter = data.sessionDepartedCharacter;
        }
    },
    player_choice(data) {
        if (data.sessionID === store.currentSessionId) {
            store.setCurrentChoice(data);
            store.setStatusText("等待玩家选择...");
        }
    }
};

const { connect, ensureConnected, connected } = useSSE(sseHandlers);

function scrollToBottom() {
    const el = msgContainer.value;
    if (el) el.scrollTop = el.scrollHeight;
}
</script>

<style scoped>
.session-empty {
    text-align: center;
    margin-top: 80px;
    color: var(--text-muted, #909399);
}
.roleplay-layout {
    display: flex;
    height: calc(100vh - 56px - 40px);
    gap: 0;
    background: #fff;
    border-radius: var(--card-radius, 12px);
    box-shadow: var(--card-shadow, 0 1px 3px rgba(0, 0, 0, 0.06));
    overflow: hidden;
}
.rp-sidebar {
    width: 240px;
    flex-shrink: 0;
    border-right: 1px solid var(--border-light, #e9edf3);
    display: flex;
    flex-direction: column;
    background: #fafbfc;
}
.rp-sidebar-header {
    padding: 16px 12px 12px;
    flex-shrink: 0;
}
.rp-session-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 6px;
}
.rp-session-icon {
    flex-shrink: 0;
    color: var(--brand-500, #5d9eff);
    background: var(--brand-50, #f0f6ff);
    border-radius: 7px;
    padding: 4px;
}
.rp-divider {
    height: 1px;
    background: var(--border-light, #e9edf3);
    margin: 0 12px;
    flex-shrink: 0;
}
.rp-session-info {
    margin: 8px 12px 12px;
    padding: 12px;
    background: #fff;
    border-radius: 12px;
    border: 1px solid var(--border-light, #e9edf3);
    font-size: 12px;
    box-shadow: var(--shadow-1, 0 1px 2px rgba(16, 24, 40, 0.05));
}
.rp-info-title {
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--text-primary, #1e2a3a);
    font-size: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.rp-env-edit-btn {
    padding: 0 2px;
    color: var(--text-muted, #909399);
    font-size: 12px;
}
.rp-env-edit-btn:hover {
    color: var(--brand-500, #5d9eff);
}
.rp-info-body {
    color: var(--text-secondary, #5b6779);
    line-height: 1.8;
}
.rp-info-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    margin-bottom: 4px;
    border-radius: 8px;
    background: #f7f9fc;
}
.rp-info-icon {
    flex-shrink: 0;
    color: var(--brand-500, #5d9eff);
    background: var(--brand-50, #f0f6ff);
    border-radius: 6px;
    padding: 2px;
}
.rp-chars-section {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border-light, #e9edf3);
}
.rp-chars-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.rp-char-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    max-width: 100%;
    padding: 3px 8px 3px 10px;
    border-radius: 16px;
    font-size: 12px;
    line-height: 1.5;
    overflow: hidden;
}
.rp-char-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--pill-dot, #5d9eff);
    flex-shrink: 0;
}
.rp-char-close {
    border: none;
    background: transparent;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    padding: 0;
    color: var(--pill-close, #5d9eff);
    opacity: 0.55;
    transition: opacity 0.15s;
    flex-shrink: 0;
}
.rp-char-close:hover {
    opacity: 1;
}
.rp-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
}
.rp-toolbar {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border-light, #e9edf3);
    flex-shrink: 0;
}
.rp-clear-btn,
.rp-graph-btn {
    font-size: 12px;
}
.rp-clear-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.rp-graph-btn {
    margin-right: 4px;
    color: var(--brand-500, #5d9eff);
}
.rp-sse-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-right: auto;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 20px;
    line-height: 1.5;
}
.rp-sse-badge.is-on {
    color: #18a058;
    background: rgba(24, 160, 88, 0.08);
    border: 1px solid rgba(24, 160, 88, 0.3);
}
.rp-sse-badge.is-off {
    color: #f56c6c;
    background: rgba(245, 108, 108, 0.08);
    border: 1px solid rgba(245, 108, 108, 0.3);
}
.rp-sse-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    transition: background 0.3s;
    background: currentColor;
}
.rp-sse-badge.is-on .rp-sse-dot {
    box-shadow: 0 0 4px currentColor;
}
.rp-sse-badge.is-off .rp-sse-dot {
    animation: sse-pulse 1.2s ease-in-out infinite;
}
@keyframes sse-pulse {
    0%,
    100% {
        opacity: 0.4;
    }
    50% {
        opacity: 1;
    }
}
.rp-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px 0;
    background:
        radial-gradient(720px 260px at 50% -60px, rgba(93, 158, 255, 0.06), transparent 70%),
        #f8f9fb;
}
/* 聊天空状态 */
.rp-empty {
    text-align: center;
    padding: 72px 20px 40px;
    color: var(--text-muted, #909399);
    user-select: none;
}
.rp-empty-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    border-radius: 18px;
    background: #fff;
    color: var(--brand-500, #5d9eff);
    border: 1px solid var(--brand-100, #e2edff);
    box-shadow: var(--shadow-2, 0 1px 2px rgba(16, 24, 40, 0.04), 0 4px 16px rgba(16, 24, 40, 0.06));
}
.rp-empty-title {
    margin: 16px 0 6px;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-secondary, #5b6779);
}
.rp-empty-desc {
    margin: 0;
    font-size: 13px;
    line-height: 1.7;
    max-width: 320px;
    display: inline-block;
}
/* 消息内容限宽居中，滚动条保持全宽 */
.rp-messages-inner {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 16px;
    display: flex;
    flex-direction: column;
}
/* 日期分隔条 */
.rp-date-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--text-muted, #909399);
    font-size: 12px;
    margin: 14px 0 10px;
    user-select: none;
    flex-shrink: 0;
}
.rp-date-divider::before,
.rp-date-divider::after {
    content: "";
    flex: 1;
    height: 1px;
    background: var(--border-light, #e9edf3);
}
.rp-streaming-bar {
    text-align: center;
    color: var(--text-muted, #909399);
    font-size: 13px;
    padding: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
}
/* 三点点阵打字动画 */
.rp-typing-dots {
    display: inline-flex;
    gap: 4px;
}
.rp-typing-dots i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--brand-500, #5d9eff);
    animation: typing-bounce 1.2s infinite ease-in-out;
}
.rp-typing-dots i:nth-child(2) {
    animation-delay: 0.15s;
}
.rp-typing-dots i:nth-child(3) {
    animation-delay: 0.3s;
}
@keyframes typing-bounce {
    0%,
    60%,
    100% {
        transform: translateY(0);
        opacity: 0.4;
    }
    30% {
        transform: translateY(-4px);
        opacity: 1;
    }
}
.rp-input-area {
    padding: 12px 16px;
    border-top: 1px solid var(--border-light, #e9edf3);
    background: #fff;
    box-shadow: 0 -6px 14px rgba(16, 24, 40, 0.03);
}
.rp-choice-panel {
    padding: 14px 20px 16px;
    background: var(--brand-50, #f0f6ff);
    border-top: 2px solid var(--brand-500, #5d9eff);
    border-bottom: 1px solid var(--brand-100, #e2edff);
    flex-shrink: 0;
}
.rp-choice-head {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1px;
    color: var(--brand-600, #4a8af2);
    margin-bottom: 8px;
    text-transform: uppercase;
}
.rp-choice-head-icon {
    flex-shrink: 0;
}
.rp-choice-context {
    font-size: 14px;
    color: var(--text-primary, #1e2a3a);
    margin-bottom: 12px;
    font-weight: 500;
    line-height: 1.6;
}
.rp-choice-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.rp-choice-btn {
    padding: 8px 20px;
    font-size: 14px;
    border: 1px solid var(--brand-500, #5d9eff);
    background: #fff;
    color: var(--brand-600, #4a8af2);
    border-radius: 20px;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
}
.rp-choice-btn:hover:not(:disabled) {
    background: var(--brand-500, #5d9eff);
    color: #fff;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(93, 158, 255, 0.3);
}
.rp-choice-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
.rp-choice-cancel {
    border-color: var(--border-light, #e9edf3);
    color: var(--text-muted, #909399);
}
.rp-choice-cancel:hover:not(:disabled) {
    background: var(--el-fill-color, #f6f8fb);
    color: var(--text-secondary, #5b6779);
    border-color: var(--border-light, #e9edf3);
    box-shadow: none;
    transform: none;
}
</style>
