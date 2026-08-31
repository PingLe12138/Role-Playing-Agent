<template>
    <div class="page-card logs-layout">
        <div class="logs-sidebar">
            <div class="logs-sidebar-header">
                <strong class="logs-sidebar-title"
                    ><FileText theme="outline" size="14" class="logs-sidebar-icon" />日志文件</strong
                >
                <el-button size="small" text class="logs-refresh-btn" @click="loadFiles" :loading="loading"
                    ><Refresh theme="outline" size="13" /> 刷新</el-button
                >
            </div>
            <el-input
                v-model="search"
                size="small"
                placeholder="过滤文件名"
                clearable
                :prefix-icon="Search"
                class="logs-search"
            />
            <div class="logs-file-list">
                <div
                    v-for="f in filtered"
                    :key="f.name"
                    :class="['logs-file-item', { active: f.name === activeFile }]"
                    @click="selectFile(f.name)"
                >
                    <div class="logs-file-name">{{ f.name }}</div>
                    <div class="logs-file-meta">{{ (f.size / 1024).toFixed(1) }} KB · {{ formatTime(f.mtime) }}</div>
                </div>
                <div v-if="!filtered.length" class="logs-file-empty">暂无日志文件</div>
            </div>
        </div>
        <div class="logs-content">
            <template v-if="activeFile">
                <div class="logs-content-header">
                    <span class="logs-content-name"
                        ><FileTxt theme="outline" size="14" class="logs-content-icon" />{{ activeFile }}</span
                    >
                    <span class="logs-live-badge"><i class="live-dot"></i>实时</span>
                </div>
                <pre ref="preRef" class="logs-pre">{{ content }}</pre>
            </template>
            <div v-else class="logs-placeholder">
                <FileText theme="outline" size="36" class="logs-placeholder-icon" />
                <p>选择一个日志文件查看内容</p>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { FileText, FileTxt, Refresh, Search } from "@icon-park/vue-next";
import { getLogFiles, getLogContent, streamLogUrl } from "../api/logs.js";

const files = ref([]);
const activeFile = ref("");
const content = ref("");
const search = ref("");
const loading = ref(false);
const preRef = ref(null);
let eventSource = null;

const filtered = computed(() => {
    const q = search.value.toLowerCase();
    return q ? files.value.filter((f) => f.name.toLowerCase().includes(q)) : files.value;
});

function scrollToBottom() {
    nextTick(() => {
        const el = preRef.value;
        if (el) el.scrollTop = el.scrollHeight;
    });
}

function stopStream() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
}

function startStream(name) {
    stopStream();
    activeFile.value = name;
    content.value = "";

    getLogContent(name).then((data) => {
        content.value = data?.content || "";
        scrollToBottom();
    });

    eventSource = new EventSource(streamLogUrl(name));
    eventSource.addEventListener("append", (e) => {
        const data = JSON.parse(e.data);
        content.value += data.content;
        scrollToBottom();
    });
}

async function loadFiles() {
    loading.value = true;
    try {
        files.value = (await getLogFiles()) || [];
        if (!activeFile.value && files.value.length) {
            startStream(files.value[0].name);
        }
    } catch {
        /* ignore */
    } finally {
        loading.value = false;
    }
}

async function selectFile(name) {
    if (name === activeFile.value) return;
    startStream(name);
}

function formatTime(ts) {
    if (!ts) return "";
    try {
        return new Date(ts * 1000).toLocaleString("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit"
        });
    } catch {
        return "";
    }
}

onMounted(loadFiles);
onUnmounted(stopStream);
</script>

<style scoped>
.logs-layout {
    display: flex;
    height: 100%;
    gap: 16px;
    padding: 0;
    overflow: hidden;
}
.logs-sidebar {
    width: 260px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    padding: 16px 0 16px 16px;
}
.logs-sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
    padding-right: 16px;
}
.logs-sidebar-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-primary, #1e2a3a);
    line-height: 1;
}
.logs-sidebar-icon {
    color: var(--brand-500, #5d9eff);
}
.logs-refresh-btn {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: var(--text-secondary, #5b6779);
}
.logs-search {
    margin-bottom: 8px;
    padding-right: 16px;
}
.logs-file-list {
    flex: 1;
    overflow-y: auto;
    border: 1px solid var(--border-light, #e9edf3);
    border-radius: 10px;
    margin-right: 0;
}
.logs-file-item {
    position: relative;
    padding: 10px 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--border-light, #e9edf3);
    transition: background 0.15s;
}
.logs-file-item:last-child {
    border-bottom: none;
}
.logs-file-item:hover {
    background: var(--brand-50, #f0f6ff);
}
.logs-file-item.active {
    background: linear-gradient(90deg, var(--brand-50, #f0f6ff), #f7faff);
}
.logs-file-item.active::before {
    content: "";
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 2px;
    background: var(--brand-500, #5d9eff);
}
.logs-file-item.active .logs-file-name {
    color: var(--brand-600, #4a8af2);
    font-weight: 600;
}
.logs-file-name {
    font-size: 13px;
    line-height: 1.3;
    color: var(--text-secondary, #5b6779);
}
.logs-file-meta {
    font-size: 11px;
    color: var(--text-muted, #909399);
    margin-top: 2px;
}
.logs-file-empty {
    text-align: center;
    color: var(--text-muted, #909399);
    padding: 24px;
    font-size: 13px;
}
.logs-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 16px 16px 16px 0;
}
.logs-content-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 2px 8px;
}
.logs-content-name {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.logs-content-icon {
    color: var(--brand-500, #5d9eff);
    flex-shrink: 0;
}
.logs-live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 12px;
    color: #18a058;
    background: rgba(24, 160, 88, 0.08);
    border: 1px solid rgba(24, 160, 88, 0.3);
    flex-shrink: 0;
}
.live-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #18a058;
    box-shadow: 0 0 0 3px rgba(24, 160, 88, 0.15);
    animation: live-pulse 1.4s ease-in-out infinite;
}
@keyframes live-pulse {
    0%,
    100% {
        opacity: 0.6;
    }
    50% {
        opacity: 1;
    }
}
.logs-placeholder {
    text-align: center;
    margin-top: 80px;
    color: var(--text-muted, #909399);
}
.logs-placeholder-icon {
    color: #c0c4cc;
}
.logs-placeholder p {
    font-size: 13px;
}
.logs-pre {
    margin: 0;
    padding: 14px;
    background: #161b22;
    border: 1px solid #2d333b;
    color: #d4d4d4;
    font-size: 12px;
    line-height: 1.6;
    border-radius: 10px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
    flex: 1;
    font-family: var(--font-mono, "JetBrains Mono", Consolas, monospace);
}
</style>
