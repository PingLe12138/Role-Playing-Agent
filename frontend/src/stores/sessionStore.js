import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { listSessions, createSession, deleteSession, updateSession, getSession } from "../api/session.js";
import { listSessionHistory, clearSessionHistory, deleteSessionHistory } from "../api/sessionHistory.js";
import { sendChatMessage } from "../api/chat.js";

export const useSessionStore = defineStore("session", () => {
    const sessions = ref([]);
    const currentSession = ref(null);
    const messages = ref([]);
    const loading = ref(false);
    const streaming = ref(false);
    const statusText = ref("");
    const currentChoice = ref(null); // { context, choices } — pending player choice awaiting response
    const sessionTotal = ref(0);
    const sessionPage = ref(1);
    const sessionPageSize = ref(10);
    const sessionKeyword = ref("");

    const currentSessionId = computed(() => currentSession.value?.sessionID || "");

    async function loadSessions(opts = {}) {
        loading.value = true;
        try {
            if (opts.reset) sessionPage.value = 1;
            if (opts.page != null) sessionPage.value = opts.page;
            if (opts.pageSize != null) {
                sessionPage.value = 1;
                sessionPageSize.value = opts.pageSize;
            }
            if (opts.keyword != null) sessionKeyword.value = opts.keyword;
            const data = await listSessions({
                page: sessionPage.value,
                page_size: sessionPageSize.value,
                keyword: sessionKeyword.value || undefined
            });
            sessions.value = data?.items || [];
            sessionTotal.value = data?.total || 0;
        } finally {
            loading.value = false;
        }
    }

    async function create(data) {
        const result = await createSession(data);
        sessions.value.push(result.session);
        return result;
    }

    async function removeSession(id) {
        await deleteSession(id);
        sessions.value = sessions.value.filter((s) => s.sessionID !== id);
        if (currentSession.value?.sessionID === id) {
            currentSession.value = null;
            messages.value = [];
        }
    }

    async function loadSession(sessionId) {
        currentSession.value = await getSession(sessionId);
        if (!currentSession.value) return;
        messages.value = (await listSessionHistory(sessionId)) || [];
        // 恢复挂起的玩家选择（页面刷新后）
        restoreChoiceFromSession(currentSession.value);
    }

    async function removePresentCharacter(characterId) {
        if (!currentSession.value) return;
        const ids = currentSession.value.sessionPresentCharacter || [];
        const updated = Array.isArray(ids) ? ids.filter((id) => id !== characterId) : [];
        await updateSession(currentSession.value.sessionID, {
            sessionPresentCharacter: updated
        });
        currentSession.value.sessionPresentCharacter = updated;
    }

    async function updateSessionEnvData(envData) {
        if (!currentSession.value) return;
        await updateSession(currentSession.value.sessionID, {
            sessionEnvData: envData
        });
        currentSession.value.sessionEnvData = { ...envData };
    }

    async function sendMessage(text) {
        if (!currentSessionId.value) return;
        streaming.value = true;
        try {
            await sendChatMessage({
                sessionID: currentSessionId.value,
                message: text
            });
        } catch (e) {
            streaming.value = false;
        }
    }

    function appendStreamMessage(msg) {
        if (!msg.sessionHistoryID && !msg._tempId) {
            msg._tempId = "msg_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6);
        }
        messages.value.push(msg);
        // 当选择结果消息到达时，清除当前挂起的选择面板
        if (msg.contentType === "player_choice_result") {
            currentChoice.value = null;
        }
    }

    function setStreaming(val) {
        streaming.value = val;
    }

    function setStatusText(val) {
        statusText.value = val;
    }

    function setCurrentChoice(data) {
        if (!data || !data.choices || !data.choices.length) {
            currentChoice.value = null;
            return;
        }
        currentChoice.value = {
            context: data.context || "",
            choices: data.choices || []
        };
    }

    function clearChoice() {
        currentChoice.value = null;
    }

    function restoreChoiceFromSession(session) {
        const raw = session?.sessionPendingChoice;
        if (!raw) {
            currentChoice.value = null;
            return;
        }
        let data = raw;
        if (typeof data === "string") {
            try {
                data = JSON.parse(data);
            } catch {
                currentChoice.value = null;
                return;
            }
        }
        if (data && data.phase === "awaiting_player" && data.choices && data.choices.length) {
            // Check if any player_choice_result exists after the last player_choice;
            // if so, the choice is already resolved — don't show interactive panel.
            const msgs = messages.value;
            let hasResult = false;
            for (let i = msgs.length - 1; i >= 0; i--) {
                try {
                    const c = JSON.parse(msgs[i].content || "{}");
                    if (c.contentType === "player_choice_result") {
                        hasResult = true;
                        break;
                    }
                    if (c.contentType === "player_choice") break;
                } catch {}
            }
            if (hasResult) {
                currentChoice.value = null;
                return;
            }
            currentChoice.value = {
                context: data.context || "",
                choices: data.choices || []
            };
        } else {
            currentChoice.value = null;
        }
    }

    async function clearSessionHistoryAll() {
        if (!currentSessionId.value) return;
        await clearSessionHistory(currentSessionId.value);
        messages.value = [];
    }

    async function deleteMessage(id) {
        if (!id) return;
        await deleteSessionHistory(id);
        messages.value = messages.value.filter((m) => m.sessionHistoryID !== id);
    }

    return {
        sessions,
        currentSession,
        messages,
        loading,
        streaming,
        statusText,
        currentChoice,
        currentSessionId,
        sessionTotal,
        sessionPage,
        sessionPageSize,
        sessionKeyword,
        loadSessions,
        create,
        removeSession,
        loadSession,
        removePresentCharacter,
        updateSessionEnvData,
        sendMessage,
        appendStreamMessage,
        setStreaming,
        setStatusText,
        setCurrentChoice,
        clearChoice,
        clearSessionHistoryAll,
        deleteMessage
    };
});
