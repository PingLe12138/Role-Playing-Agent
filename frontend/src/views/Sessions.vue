<template>
    <div class="page-card sessions-page">
        <div class="page-header">
            <div class="header-left">
                <div class="page-title-block">
                    <span class="page-title-icon"><Message theme="filled" size="15" /></span>
                    <div>
                        <h2>会话列表</h2>
                        <p class="page-subtitle">共 {{ store.sessionTotal }} 个会话 · 双击进入或继续冒险</p>
                    </div>
                </div>
            </div>
            <div class="header-right">
                <el-input
                    v-model="keyword"
                    class="search-input"
                    placeholder="搜索会话标题"
                    clearable
                    :prefix-icon="Search"
                    @input="onKeywordInput"
                    @clear="reload(1)"
                />
                <el-button type="primary" @click="openCreate">
                    <Plus theme="outline" size="14" class="btn-icon" />新建会话
                </el-button>
                <el-button type="success" plain @click="triggerImport">
                    <Upload theme="outline" size="14" class="btn-icon" />导入会话
                </el-button>
            </div>
        </div>
        <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileSelected" />
        <el-empty v-if="!store.loading && !store.sessions.length" description="还没有会话">
            <el-button type="primary" @click="openCreate">创建第一个会话</el-button>
        </el-empty>
        <el-table
            v-else
            :data="store.sessions"
            v-loading="store.loading"
            class="data-table"
            @row-dblclick="enterSession"
        >
            <el-table-column label="标题" min-width="220">
                <template #default="{ row }">
                    <div class="title-cell">
                        <span class="title-icon"><Message theme="filled" size="14" fill="#5d9eff" /></span>
                        <el-tooltip
                            :content="row.sessionTitle"
                            :disabled="String(row.sessionTitle).length <= 24"
                            placement="top"
                        >
                            <span class="title-text">{{ row.sessionTitle }}</span>
                        </el-tooltip>
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="世界观" min-width="140">
                <template #default="{ row }">{{ worldviewName(row.worldviewCollectionID) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
                <template #default="{ row }">
                    <span class="status-badge" :class="row.status === 'active' ? 'is-active' : 'is-ended'">
                        <i class="status-dot"></i>{{ row.status === "active" ? "进行中" : "已结束" }}
                    </span>
                </template>
            </el-table-column>
            <el-table-column label="创建时间" width="150">
                <template #default="{ row }">
                    <span class="time-cell">{{ formatTime(row.recordCreatedTime) }}</span>
                </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right" align="center">
                <template #default="{ row }">
                    <el-button size="small" type="primary" class="enter-btn" @click="enterSession(row)">
                        进入
                    </el-button>
                    <el-tooltip content="导出会话" placement="top">
                        <el-button size="small" class="icon-btn" @click="handleExport(row)">
                            <Download theme="outline" size="14" />
                        </el-button>
                    </el-tooltip>
                    <el-tooltip content="删除会话" placement="top">
                        <el-button size="small" type="danger" plain class="icon-btn" @click="handleDelete(row)">
                            <Delete theme="outline" size="14" />
                        </el-button>
                    </el-tooltip>
                </template>
            </el-table-column>
        </el-table>

        <div v-if="store.sessionTotal > 0" class="pagination-wrap">
            <el-pagination
                background
                layout="total, sizes, prev, pager, next, jumper"
                :total="store.sessionTotal"
                :page-sizes="[10, 20, 50]"
                v-model:current-page="store.sessionPage"
                v-model:page-size="store.sessionPageSize"
                @current-change="reload()"
                @size-change="reload(1)"
            />
        </div>

        <CreateSessionDialog
            ref="dialogRef"
            :worldview-collections="wvcStore.collections"
            :user-characters="ucStore.cards"
            :character-cards="characterStore.cards"
            @created="onCreated"
        />
    </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Message, Search, Plus, Download, Delete, Upload } from "@icon-park/vue-next";
import { useSessionStore } from "../stores/sessionStore.js";
import { useWorldviewStore } from "../stores/worldviewStore.js";
import { useUserCharacterStore } from "../stores/userCharacterStore.js";
import { useCharacterStore } from "../stores/characterStore.js";
import CreateSessionDialog from "../components/CreateSessionDialog.vue";
import { exportSession, importSession } from "../api/session.js";

const router = useRouter();
const store = useSessionStore();
const wvcStore = useWorldviewStore();
const ucStore = useUserCharacterStore();
const characterStore = useCharacterStore();
const dialogRef = ref(null);
const fileInput = ref(null);
const keyword = ref("");
let searchTimer = null;

onMounted(async () => {
    await Promise.all([store.loadSessions(), wvcStore.load(), ucStore.load(), characterStore.load()]);
});

onBeforeUnmount(() => {
    if (searchTimer) clearTimeout(searchTimer);
});

function reload(page) {
    store.loadSessions(page ? { reset: true } : {});
}

function onKeywordInput() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => store.loadSessions({ keyword: keyword.value, reset: true }), 300);
}

function formatTime(t) {
    if (!t) return "-";
    return String(t).replace("T", " ").slice(0, 19);
}

function worldviewName(id) {
    const col = wvcStore.collections.find((c) => c.worldviewCollectionID === id);
    return col?.worldviewCollectionName || id?.slice(0, 12) || "无";
}

function openCreate() {
    dialogRef.value?.open();
}

function onCreated(result) {
    store.sessions.push(result.session);
    store.sessionTotal += 1;
    store.currentSession = result.session;
    router.push(`/sessions/${result.session.sessionID}`);
}

function enterSession(row) {
    router.push(`/sessions/${row.sessionID}`);
}

async function handleDelete(row) {
    try {
        await ElMessageBox.confirm(`确定删除会话「${row.sessionTitle}」？`, "确认");
        await store.removeSession(row.sessionID);
        await store.loadSessions();
        ElMessage.success("删除成功");
    } catch {
        /* cancelled */
    }
}

function triggerImport() {
    fileInput.value?.click();
}

async function onFileSelected(e) {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        await importSession(data);
        await store.loadSessions({ reset: true });
        ElMessage.success("导入成功");
    } catch (err) {
        ElMessage.error(err.message || "导入失败，请检查文件格式");
    } finally {
        fileInput.value.value = "";
    }
}

async function handleExport(row) {
    try {
        const blob = await exportSession(row.sessionID);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${row.sessionTitle}_session.json`;
        a.click();
        URL.revokeObjectURL(url);
        ElMessage.success("导出成功");
    } catch (err) {
        ElMessage.error(err.message || "导出失败");
    }
}
</script>

<style scoped>
.header-left {
    display: flex;
    align-items: baseline;
    gap: 10px;
}
.header-count {
    font-size: 13px;
    color: #909399;
    font-weight: 400;
}
.header-right {
    display: flex;
    align-items: center;
    gap: 10px;
}
.search-input {
    width: 220px;
}
.btn-icon {
    margin-right: 4px;
}
.title-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
}
.title-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    flex-shrink: 0;
    border-radius: 7px;
    background: #f0f6ff;
}
.title-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.time-cell {
    color: var(--text-secondary, #5b6779);
    font-variant-numeric: tabular-nums;
}
/* 双击进入会话，行指针提示可点 */
.sessions-page .data-table :deep(.el-table__row) {
    cursor: pointer;
}
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 12px;
}
.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
}
.status-badge.is-active {
    background: #e8f7ee;
    color: #18a058;
}
.status-badge.is-active .status-dot {
    background: #18a058;
    box-shadow: 0 0 0 3px rgba(24, 160, 88, 0.15);
}
.status-badge.is-ended {
    background: #f2f3f5;
    color: #909399;
}
.status-badge.is-ended .status-dot {
    background: #c0c4cc;
}
.enter-btn {
    margin-right: 8px;
}
.icon-btn {
    padding: 6px 7px;
    margin-left: 4px;
}
.pagination-wrap {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
}
</style>
