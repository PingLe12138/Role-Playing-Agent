<template>
    <div class="page-card">
        <div class="page-header">
            <div class="page-title-block">
                <span class="page-title-icon"><User theme="filled" size="16" /></span>
                <div>
                    <h2>用户角色信息卡</h2>
                    <p class="page-subtitle">玩家扮演的角色——引擎永远不会替它说话或行动</p>
                </div>
            </div>
            <div>
                <el-button type="primary" @click="openCreate"
                    ><Plus theme="outline" size="14" class="btn-icon" />新建用户角色</el-button
                >
                <el-button type="success" plain @click="triggerImport"
                    ><Upload theme="outline" size="14" class="btn-icon" />导入用户角色</el-button
                >
            </div>
        </div>
        <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileSelected" />
        <el-empty v-if="!store.loading && !store.cards.length" description="还没有用户角色">
            <el-button type="primary" @click="openCreate">创建第一个用户角色</el-button>
        </el-empty>
        <el-table v-else :data="store.cards" v-loading="store.loading" class="data-table">
            <el-table-column label="名称" min-width="220">
                <template #default="{ row }">
                    <div class="name-cell">
                        <span class="name-avatar" :style="avatarStyle()">{{
                            (row.userCharacterName || "?").charAt(0)
                        }}</span>
                        <div class="name-main">
                            <div class="name-text">{{ row.userCharacterName }}</div>
                            <div class="name-id">{{ row.userCharacterID }}</div>
                        </div>
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="信息" min-width="300" show-overflow-tooltip>
                <template #default="{ row }">
                    {{ summaryInfo(row.userCharacterInfo) }}
                </template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right" align="center">
                <template #default="{ row }">
                    <el-button size="small" type="primary" class="enter-btn" @click="openEdit(row)">编辑</el-button>
                    <el-tooltip content="导出用户角色" placement="top">
                        <el-button size="small" class="icon-btn" @click="handleExport(row)"
                            ><Download theme="outline" size="14"
                        /></el-button>
                    </el-tooltip>
                    <el-tooltip content="删除用户角色" placement="top">
                        <el-button size="small" type="danger" plain class="icon-btn" @click="handleDelete(row)"
                            ><Delete theme="outline" size="14"
                        /></el-button>
                    </el-tooltip>
                </template>
            </el-table-column>
        </el-table>

        <el-dialog
            v-model="dialogVisible"
            :title="isEdit ? '编辑用户角色' : '新建用户角色'"
            width="720px"
            class="rp-dialog"
        >
            <el-form :model="form" label-width="80px">
                <el-form-item label="名称">
                    <el-input v-model="form.userCharacterName" placeholder="角色名称" />
                </el-form-item>

                <el-divider content-position="left">角色描述</el-divider>

                <el-form-item label="相貌">
                    <el-input v-model="form.appearance" type="textarea" :rows="2" placeholder="外貌、衣着、身材等" />
                </el-form-item>
                <el-form-item label="性格">
                    <el-input v-model="form.personality" type="textarea" :rows="2" placeholder="性格特点、行为习惯等" />
                </el-form-item>
                <el-form-item label="语气">
                    <el-input v-model="form.tone" type="textarea" :rows="1" placeholder="说话方式、语调特点等" />
                </el-form-item>
                <el-form-item label="背景">
                    <el-input v-model="form.background" type="textarea" :rows="2" placeholder="身世、经历等" />
                </el-form-item>
                <el-form-item label="其他">
                    <el-input v-model="form.other" type="textarea" :rows="2" placeholder="其他补充描述" />
                </el-form-item>

                <div v-for="(group, gi) in form.sessionGroups" :key="group.sessionID">
                    <el-divider :content-position="'left'">
                        {{ group.sessionTitle }}
                        <el-tag v-if="!group.isGlobal" size="small" type="info" style="margin-left: 8px"
                            >会话专属</el-tag
                        >
                    </el-divider>

                    <div v-for="cid in group.selectedRelChars" :key="cid" class="rel-card">
                        <div class="rel-card-title">
                            <template v-if="group.isDefault">→</template>
                            <template v-else-if="group.relData[cid]?.direction === 'both'">↔</template>
                            <template v-else-if="group.relData[cid]?.direction === 'incoming'">←</template>
                            <template v-else>→</template>
                            {{ charNameMap[cid] || cid }}
                        </div>
                        <div class="rel-card-body">
                            <el-form-item label="类型" class="rel-field">
                                <el-input v-model="group.relData[cid].type" placeholder="如好友、死敌、师徒…" />
                            </el-form-item>
                            <el-form-item label="强度" class="rel-field">
                                <el-slider
                                    v-model="group.relData[cid].strength"
                                    :min="0"
                                    :max="1"
                                    :step="0.1"
                                    show-input
                                    size="small"
                                />
                            </el-form-item>
                            <el-form-item label="情感" class="rel-field">
                                <el-slider
                                    v-model="group.relData[cid].sentiment"
                                    :min="-1"
                                    :max="1"
                                    :step="0.1"
                                    show-input
                                    size="small"
                                />
                            </el-form-item>
                            <el-form-item label="权力" class="rel-field">
                                <el-slider
                                    v-model="group.relData[cid].power_dynamic"
                                    :min="-1"
                                    :max="1"
                                    :step="0.1"
                                    show-input
                                    size="small"
                                />
                            </el-form-item>
                        </div>
                    </div>
                </div>
            </el-form>
            <template #footer>
                <el-button @click="dialogVisible = false">取消</el-button>
                <el-button type="primary" @click="submit" :loading="submitting">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Upload, Download, Delete, User } from "@icon-park/vue-next";
import { useUserCharacterStore } from "../stores/userCharacterStore.js";
import { useCharacterStore } from "../stores/characterStore.js";
import { batchCreateRelationships, listCharacterRelationships } from "../api/characterRelationship.js";
import { exportUserCharacter, importUserCharacters } from "../api/userCharacter.js";

const store = useUserCharacterStore();
const npcStore = useCharacterStore();
const dialogVisible = ref(false);
const isEdit = ref(false);
const editId = ref("");
const submitting = ref(false);
const fileInput = ref(null);

const emptyForm = () => ({
    userCharacterName: "",
    appearance: "",
    personality: "",
    tone: "",
    background: "",
    other: "",
    sessionGroups: []
});

const form = reactive(emptyForm());

onMounted(() => {
    store.load();
    npcStore.load();
});

const charNameMap = computed(() => {
    const m = {};
    for (const c of store.cards) m[c.userCharacterID] = c.userCharacterName;
    for (const c of npcStore.cards) m[c.characterID] = c.characterName;
    return m;
});

function summaryInfo(info) {
    if (!info) return "";
    try {
        const obj = JSON.parse(info);
        if (obj && typeof obj === "object") {
            return obj.appearance || obj.personality || obj.background || info;
        }
    } catch {}
    return info;
}

function avatarStyle() {
    return { background: "var(--brand-500, #5d9eff)" };
}

function parseInfo(info) {
    try {
        const obj = JSON.parse(info);
        if (obj && typeof obj === "object" && !Array.isArray(obj)) {
            form.appearance = obj.appearance || "";
            form.personality = obj.personality || "";
            form.tone = obj.tone || "";
            form.background = obj.background || "";
            form.other = obj.other || "";
            return;
        }
    } catch {}
    form.other = info || "";
}

function resetForm() {
    Object.assign(form, emptyForm());
}

function openCreate() {
    isEdit.value = false;
    editId.value = "";
    resetForm();
    dialogVisible.value = true;
}

async function openEdit(row) {
    isEdit.value = true;
    editId.value = row.userCharacterID;
    resetForm();
    form.userCharacterName = row.userCharacterName;
    parseInfo(row.userCharacterInfo);

    const isKnownChar = (cid) =>
        store.cards.find((c) => c.userCharacterID === cid) || npcStore.cards.find((c) => c.characterID === cid);

    try {
        const rels = (await listCharacterRelationships(row.userCharacterID)) || [];

        const groupsMap = {};
        for (const r of rels) {
            const key = r.isDefault ? "__default__" : r.sessionID || r.relationshipID;
            const isGlobal = !!r.isDefault || !r.sessionID;
            if (!groupsMap[key]) {
                groupsMap[key] = {
                    sessionID: isGlobal ? "" : r.sessionID,
                    sessionTitle: isGlobal ? "默认（全局）" : r.sessionTitle || r.sessionID,
                    isGlobal,
                    isDefault: !!r.isDefault,
                    selectedRelChars: [],
                    relData: {}
                };
            }
            let otherId = null;
            if (r.characterID_1 === row.userCharacterID) {
                otherId = r.characterID_2;
            } else if (r.characterID_2 === row.userCharacterID) {
                otherId = r.characterID_1;
            }
            if (!otherId) continue;
            if (!isKnownChar(otherId)) continue;

            const exists = groupsMap[key].selectedRelChars.includes(otherId);
            if (!exists) {
                groupsMap[key].selectedRelChars.push(otherId);
                groupsMap[key].relData[otherId] = {
                    type: r.relationship_type || "neutral",
                    strength: r.strength ?? 0.5,
                    sentiment: r.sentiment ?? 0.0,
                    power_dynamic: r.power_dynamic ?? 0.0,
                    direction: r.characterID_1 === row.userCharacterID ? "outgoing" : "incoming"
                };
            } else {
                const existing = groupsMap[key].relData[otherId];
                if (existing.direction === "incoming" && r.characterID_1 === row.userCharacterID) {
                    existing.type = r.relationship_type || existing.type;
                    existing.strength = r.strength ?? existing.strength;
                    existing.sentiment = r.sentiment ?? existing.sentiment;
                    existing.power_dynamic = r.power_dynamic ?? existing.power_dynamic;
                    existing.direction = "both";
                }
            }
        }

        const sorted = Object.values(groupsMap).sort((a, b) => {
            if (a.isGlobal) return -1;
            if (b.isGlobal) return 1;
            return (a.sessionTitle || "").localeCompare(b.sessionTitle || "");
        });

        form.sessionGroups = sorted;
    } catch {
        /* ignore */
    }

    dialogVisible.value = true;
}

async function submit() {
    if (!form.userCharacterName.trim()) return ElMessage.warning("请输入名称");

    const infoParts = {};
    if (form.appearance) infoParts.appearance = form.appearance;
    if (form.personality) infoParts.personality = form.personality;
    if (form.tone) infoParts.tone = form.tone;
    if (form.background) infoParts.background = form.background;
    if (form.other) infoParts.other = form.other;
    const infoStr = Object.keys(infoParts).length ? JSON.stringify(infoParts) : "";

    submitting.value = true;
    try {
        if (isEdit.value) {
            const defaultGroup = form.sessionGroups.find((g) => g.isDefault);
            const defaults = defaultGroup
                ? defaultGroup.selectedRelChars
                      .filter((cid) => defaultGroup.relData[cid])
                      .map((targetId) => ({
                          characterID: targetId,
                          relationship_type: defaultGroup.relData[targetId]?.type || "neutral",
                          strength: defaultGroup.relData[targetId]?.strength ?? 0.5,
                          sentiment: defaultGroup.relData[targetId]?.sentiment ?? 0.0,
                          power_dynamic: defaultGroup.relData[targetId]?.power_dynamic ?? 0.0
                      }))
                : [];

            await store.update(editId.value, {
                userCharacterName: form.userCharacterName,
                userCharacterInfo: infoStr,
                defaultRelationships: defaults
            });
        } else {
            const card = await store.create({
                userCharacterName: form.userCharacterName,
                userCharacterInfo: infoStr
            });
            editId.value = card.userCharacterID;

            const defaultGroup = form.sessionGroups.find((g) => g.isDefault);
            const defaults = defaultGroup
                ? defaultGroup.selectedRelChars
                      .filter((cid) => defaultGroup.relData[cid])
                      .map((targetId) => ({
                          characterID: targetId,
                          relationship_type: defaultGroup.relData[targetId]?.type || "neutral",
                          strength: defaultGroup.relData[targetId]?.strength ?? 0.5,
                          sentiment: defaultGroup.relData[targetId]?.sentiment ?? 0.0,
                          power_dynamic: defaultGroup.relData[targetId]?.power_dynamic ?? 0.0
                      }))
                : [];

            if (defaults.length) {
                await store.update(editId.value, { defaultRelationships: defaults });
            }
        }

        for (const group of form.sessionGroups) {
            if (group.isDefault) continue;
            const relsToSave = group.selectedRelChars
                .filter((cid) => group.relData[cid])
                .map((targetId) => ({
                    sessionID: group.sessionID,
                    characterID_1: editId.value,
                    characterID_2: targetId,
                    relationship_type: group.relData[targetId]?.type || "neutral",
                    strength: group.relData[targetId]?.strength ?? 0.5,
                    sentiment: group.relData[targetId]?.sentiment ?? 0.0,
                    power_dynamic: group.relData[targetId]?.power_dynamic ?? 0.0
                }));

            if (relsToSave.length > 0) {
                await batchCreateRelationships({ relationships: relsToSave });
            }
        }

        ElMessage.success(isEdit.value ? "更新成功" : "创建成功");
        dialogVisible.value = false;
    } catch (e) {
        ElMessage.error(e.message || "操作失败");
    } finally {
        submitting.value = false;
    }
}

async function handleDelete(row) {
    try {
        await ElMessageBox.confirm(`确定删除用户角色「${row.userCharacterName}」？`, "确认");
    } catch {
        return;
    }
    try {
        await store.remove(row.userCharacterID);
        ElMessage.success("删除成功");
    } catch (e) {
        ElMessage.error(e.message || "删除失败");
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
        await importUserCharacters(data);
        await store.load();
        ElMessage.success("导入成功");
    } catch (err) {
        ElMessage.error(err.message || "导入失败，请检查文件格式");
    } finally {
        submitting.value = false;
        fileInput.value.value = "";
    }
}

async function handleExport(row) {
    try {
        const blob = await exportUserCharacter(row.userCharacterID);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${row.userCharacterName}_user_character.json`;
        a.click();
        URL.revokeObjectURL(url);
        ElMessage.success("导出成功");
    } catch (err) {
        ElMessage.error(err.message || "导出失败");
    }
}
</script>

<style scoped>
.rel-card {
    border: 1px solid var(--border-light, #e9edf3);
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 10px;
    background: var(--el-fill-color-lighter, #fafbfd);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.rel-card:hover {
    border-color: var(--brand-200, #c8dcff);
    box-shadow: var(--shadow-1, 0 1px 2px rgba(16, 24, 40, 0.05));
}
.rel-card-title {
    font-weight: 600;
    font-size: 13px;
    margin-bottom: 8px;
    color: var(--brand-600, #4a8af2);
}
.rel-card-body {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.rel-field {
    flex: 1 1 45%;
    min-width: 180px;
}
</style>
