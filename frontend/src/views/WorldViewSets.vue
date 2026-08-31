<template>
    <div class="page-card">
        <div class="page-header">
            <div class="page-title-block">
                <span class="page-title-icon"><CollectionRecords theme="filled" size="16" /></span>
                <div>
                    <h2>世界观管理</h2>
                    <p class="page-subtitle">世界观条目经向量检索注入角色扮演上下文</p>
                </div>
            </div>
            <div class="header-actions">
                <el-button type="primary" @click="openCreateCollection"
                    ><Plus theme="outline" size="14" class="btn-icon" />新建世界观集</el-button
                >
                <el-button type="success" plain @click="triggerImport"
                    ><Upload theme="outline" size="14" class="btn-icon" />导入世界观</el-button
                >
                <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileSelected" />
            </div>
        </div>

        <el-empty v-if="!store.loading && !store.collections.length" description="还没有世界观集">
            <el-button type="primary" @click="openCreateCollection">创建第一个世界观集</el-button>
        </el-empty>
        <el-collapse v-else v-model="activeCollapse" @change="handleCollapseChange" class="wvc-collapse">
            <el-collapse-item
                v-for="col in store.collections"
                :key="col.worldviewCollectionID"
                :name="col.worldviewCollectionID"
            >
                <template #title>
                    <span class="wvc-col-icon"><CollectionRecords theme="outline" size="15" /></span>
                    <span class="wvc-col-title">{{ col.worldviewCollectionName }}</span>
                    <span class="wvc-col-desc">{{ col.worldviewDescription }}</span>
                </template>
                <div class="wvc-toolbar">
                    <el-button size="small" @click="openEditCollection(col)"
                        ><EditOne theme="outline" size="14" /> 编辑</el-button
                    >
                    <el-button size="small" @click="handleExport(col)"
                        ><Download theme="outline" size="14" /> 导出</el-button
                    >
                    <el-button size="small" type="danger" plain @click="handleDeleteCollection(col)"
                        ><Delete theme="outline" size="14" /> 删除</el-button
                    >
                    <el-button size="small" type="primary" @click="openCreateEntry(col.worldviewCollectionID)"
                        ><Plus theme="outline" size="14" /> 添加条目</el-button
                    >
                </div>
                <el-empty
                    v-if="!(entriesMap[col.worldviewCollectionID] || []).length"
                    description="该世界观集暂无条目"
                />
                <el-table
                    v-else
                    :data="entriesMap[col.worldviewCollectionID] || []"
                    stripe
                    size="small"
                    class="data-table"
                >
                    <el-table-column
                        prop="worldviewCollectionEntryContent"
                        label="内容"
                        min-width="400"
                        show-overflow-tooltip
                    />
                    <el-table-column label="常驻" width="80">
                        <template #default="{ row }">
                            <span class="perm-badge" :class="row.isPermanent ? 'is-perm' : 'is-normal'">
                                <i class="perm-dot"></i>{{ row.isPermanent ? "常驻" : "普通" }}
                            </span>
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" width="180">
                        <template #default="{ row }">
                            <el-button size="small" @click="openEditEntry(col.worldviewCollectionID, row)"
                                ><EditOne theme="outline" size="14" /> 编辑</el-button
                            >
                            <el-button
                                size="small"
                                type="danger"
                                plain
                                @click="handleDeleteEntry(col.worldviewCollectionID, row)"
                                ><Delete theme="outline" size="14" /> 删除</el-button
                            >
                        </template>
                    </el-table-column>
                </el-table>
            </el-collapse-item>
        </el-collapse>

        <el-dialog
            v-model="colDialog"
            :title="isEditCol ? '编辑世界观集' : '新建世界观集'"
            width="500px"
            class="rp-dialog"
        >
            <el-form :model="colForm" label-width="60px">
                <el-form-item label="名称"><el-input v-model="colForm.worldviewCollectionName" /></el-form-item>
                <el-form-item label="描述"
                    ><el-input v-model="colForm.worldviewDescription" type="textarea" :rows="3"
                /></el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="colDialog = false">取消</el-button>
                <el-button type="primary" @click="submitCollection" :loading="submitting">确定</el-button>
            </template>
        </el-dialog>

        <el-dialog v-model="entryDialog" :title="isEditEntry ? '编辑条目' : '添加条目'" width="600px" class="rp-dialog">
            <el-form :model="entryForm" label-width="60px">
                <el-form-item label="内容"
                    ><el-input v-model="entryForm.worldviewCollectionEntryContent" type="textarea" :rows="5"
                /></el-form-item>
                <el-form-item label="常驻"><el-switch v-model="entryForm.isPermanent" /></el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="entryDialog = false">取消</el-button>
                <el-button type="primary" @click="submitEntry" :loading="submitting">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Upload, Download, Delete, EditOne, CollectionRecords } from "@icon-park/vue-next";
import { useWorldviewStore } from "../stores/worldviewStore.js";
import { exportWorldviewCollection, importWorldviewCollection } from "../api/worldviewCollection.js";

const store = useWorldviewStore();
const activeCollapse = ref([]);
const colDialog = ref(false);
const isEditCol = ref(false);
const editColId = ref("");
const entryDialog = ref(false);
const isEditEntry = ref(false);
const editEntryId = ref("");
const entryParentId = ref("");
const submitting = ref(false);
const fileInput = ref(null);
const entriesMap = computed(() => store.entriesMap);
const colForm = reactive({ worldviewCollectionName: "", worldviewDescription: "" });
const entryForm = reactive({ worldviewCollectionEntryContent: "", isPermanent: false });

onMounted(() => store.load());

async function handleCollapseChange(names) {
    for (const name of names) {
        if (!store.entriesMap[name]) await store.loadEntries(name);
    }
}

function openCreateCollection() {
    isEditCol.value = false;
    colForm.worldviewCollectionName = "";
    colForm.worldviewDescription = "";
    colDialog.value = true;
}
function openEditCollection(col) {
    isEditCol.value = true;
    editColId.value = col.worldviewCollectionID;
    colForm.worldviewCollectionName = col.worldviewCollectionName;
    colForm.worldviewDescription = col.worldviewDescription;
    colDialog.value = true;
}

async function submitCollection() {
    if (!colForm.worldviewCollectionName.trim()) return ElMessage.warning("请输入名称");
    submitting.value = true;
    try {
        if (isEditCol.value) {
            await store.updateCollection(editColId.value, { ...colForm });
            ElMessage.success("更新成功");
        } else {
            await store.createCollection({ ...colForm });
            ElMessage.success("创建成功");
        }
        colDialog.value = false;
    } catch (e) {
        ElMessage.error(e.message || "操作失败");
    } finally {
        submitting.value = false;
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
        submitting.value = true;
        await importWorldviewCollection(data);
        await store.load();
        ElMessage.success("导入成功");
    } catch (err) {
        ElMessage.error(err.message || "导入失败，请检查文件格式");
    } finally {
        submitting.value = false;
        fileInput.value.value = "";
    }
}

async function handleExport(col) {
    try {
        const blob = await exportWorldviewCollection(col.worldviewCollectionID);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${col.worldviewCollectionName}_worldview.json`;
        a.click();
        URL.revokeObjectURL(url);
        ElMessage.success("导出成功");
    } catch (err) {
        ElMessage.error(err.message || "导出失败");
    }
}

async function handleDeleteCollection(col) {
    try {
        await ElMessageBox.confirm(`确定删除世界观集「${col.worldviewCollectionName}」？`, "确认");
        await store.removeCollection(col.worldviewCollectionID);
        ElMessage.success("删除成功");
    } catch {
        /* cancelled */
    }
}

function openCreateEntry(parentId) {
    isEditEntry.value = false;
    entryParentId.value = parentId;
    entryForm.worldviewCollectionEntryContent = "";
    entryForm.isPermanent = false;
    entryDialog.value = true;
}
function openEditEntry(parentId, entry) {
    isEditEntry.value = true;
    entryParentId.value = parentId;
    editEntryId.value = entry.worldviewCollectionEntryID;
    entryForm.worldviewCollectionEntryContent = entry.worldviewCollectionEntryContent;
    entryForm.isPermanent = !!entry.isPermanent;
    entryDialog.value = true;
}

async function submitEntry() {
    if (!entryForm.worldviewCollectionEntryContent.trim()) return ElMessage.warning("请输入内容");
    submitting.value = true;
    try {
        const data = {
            parentID: entryParentId.value,
            worldviewCollectionEntryContent: entryForm.worldviewCollectionEntryContent,
            isPermanent: entryForm.isPermanent
        };
        if (isEditEntry.value) {
            await store.updateEntry(editEntryId.value, data, entryParentId.value);
            ElMessage.success("更新成功");
        } else {
            await store.createEntry(data);
            ElMessage.success("创建成功");
        }
        entryDialog.value = false;
    } catch (e) {
        ElMessage.error(e.message || "操作失败");
    } finally {
        submitting.value = false;
    }
}

async function handleDeleteEntry(parentId, entry) {
    try {
        await ElMessageBox.confirm("确定删除该条目？", "确认");
        await store.removeEntry(entry.worldviewCollectionEntryID, parentId);
        ElMessage.success("删除成功");
    } catch {
        /* cancelled */
    }
}
</script>

<style scoped>
.wvc-collapse {
    border: none;
}
.wvc-collapse :deep(.el-collapse-item) {
    margin-bottom: 8px;
    border: 1px solid var(--border-light, #e9edf3);
    border-radius: 10px;
    overflow: hidden;
    transition: box-shadow 0.2s ease;
}
.wvc-collapse :deep(.el-collapse-item:hover) {
    box-shadow: var(--shadow-1, 0 1px 2px rgba(16, 24, 40, 0.05));
}
.wvc-collapse :deep(.el-collapse-item:last-child) {
    margin-bottom: 0;
}
.wvc-collapse :deep(.el-collapse-item__header) {
    padding: 0 12px;
    height: 46px;
    border-bottom: 1px solid var(--border-light, #e9edf3);
    background: #fff;
    transition: background 0.15s;
}
.wvc-collapse :deep(.el-collapse-item__header:hover) {
    background: var(--brand-50, #f0f6ff);
}
.wvc-collapse :deep(.el-collapse-item__wrap) {
    background: #fafbfc;
}
.wvc-collapse :deep(.el-collapse-item__content) {
    padding: 14px 16px;
}
.wvc-col-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-right: 8px;
    color: var(--text-muted, #909399);
    line-height: 1;
}
.wvc-collapse :deep(.el-collapse-item__header.is-active .wvc-col-icon) {
    color: var(--brand-500, #5d9eff);
}
.wvc-col-title {
    font-weight: 600;
    font-size: 14px;
    margin-right: 8px;
    color: var(--text-primary, #1e2a3a);
}
.wvc-collapse :deep(.el-collapse-item__header.is-active .wvc-col-title) {
    color: var(--brand-600, #4a8af2);
}
.wvc-col-desc {
    color: var(--text-muted, #909399);
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    text-align: left;
}
.wvc-toolbar {
    display: flex;
    gap: 8px;
    margin-top: 4px;
    margin-bottom: 12px;
}
.wvc-toolbar .el-button--small {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.data-table :deep(.el-table td.el-table__cell) {
    border-bottom-color: var(--border-light, #e9edf3);
}
.perm-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 12px;
}
.perm-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}
.perm-badge.is-perm {
    background: #e8f7ee;
    color: #18a058;
}
.perm-badge.is-normal {
    background: #f2f3f5;
    color: #909399;
}
</style>
