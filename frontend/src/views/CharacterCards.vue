<template>
    <div class="page-card">
        <div class="page-header">
            <div class="page-title-block">
                <span class="page-title-icon"><Avatar theme="filled" size="16" /></span>
                <div>
                    <h2>角色信息卡</h2>
                    <p class="page-subtitle">管理 NPC 角色卡：性格、外貌、默认关系与初始情绪</p>
                </div>
            </div>
            <div>
                <el-button type="primary" @click="openCreate"
                    ><Plus theme="outline" size="14" class="btn-icon" />新建角色</el-button
                >
                <el-button type="success" plain @click="triggerImport"
                    ><Upload theme="outline" size="14" class="btn-icon" />导入角色</el-button
                >
            </div>
        </div>
        <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileSelected" />
        <el-empty v-if="!store.loading && !store.cards.length" description="还没有角色信息卡">
            <el-button type="primary" @click="openCreate">创建第一个角色</el-button>
        </el-empty>
        <el-table v-else :data="store.cards" v-loading="store.loading" class="data-table">
            <el-table-column label="名称" min-width="220">
                <template #default="{ row }">
                    <div class="name-cell">
                        <span class="name-avatar" :style="avatarStyle(row.characterName)">{{
                            (row.characterName || "?").charAt(0)
                        }}</span>
                        <div class="name-main">
                            <div class="name-text">{{ row.characterName }}</div>
                            <div class="name-id">{{ row.characterID }}</div>
                        </div>
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="信息" min-width="300" show-overflow-tooltip>
                <template #default="{ row }">
                    {{ summaryInfo(row.characterInfo) }}
                </template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right" align="center">
                <template #default="{ row }">
                    <el-button size="small" type="primary" class="enter-btn" @click="openEdit(row)">编辑</el-button>
                    <el-tooltip content="导出角色卡" placement="top">
                        <el-button size="small" class="icon-btn" @click="handleExport(row)"
                            ><Download theme="outline" size="14"
                        /></el-button>
                    </el-tooltip>
                    <el-tooltip content="删除角色卡" placement="top">
                        <el-button size="small" type="danger" plain class="icon-btn" @click="handleDelete(row)"
                            ><Delete theme="outline" size="14"
                        /></el-button>
                    </el-tooltip>
                </template>
            </el-table-column>
        </el-table>

        <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑角色' : '新建角色'" width="720px" class="rp-dialog">
            <el-form :model="form" label-width="80px">
                <el-form-item label="名称">
                    <el-input v-model="form.characterName" placeholder="角色名称" />
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

                    <div class="group-section">
                        <div v-if="group.isGlobal" class="emo-block">
                            <div class="block-label">初始情绪</div>
                            <el-form-item label="情绪">
                                <el-input v-model="form.initialEmotion.emotionLabel" placeholder="如：平静、愤怒、悲伤" />
                            </el-form-item>
                            <el-form-item label="效价">
                                <el-slider v-model="form.initialEmotion.valence" :min="-1" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="唤醒度">
                                <el-slider v-model="form.initialEmotion.arousal" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="强度">
                                <el-slider v-model="form.initialEmotion.intensity" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="精力">
                                <el-slider v-model="form.initialEmotion.energy" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="压力">
                                <el-slider v-model="form.initialEmotion.stress" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                        </div>
                        <div v-else-if="group.emotion" class="emo-block">
                            <div class="block-label">当前情绪</div>
                            <el-form-item label="情绪">
                                <el-input v-model="group.emotion.emotionLabel" placeholder="如：平静、愤怒、悲伤" />
                            </el-form-item>
                            <el-form-item label="效价">
                                <el-slider v-model="group.emotion.valence" :min="-1" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="唤醒度">
                                <el-slider v-model="group.emotion.arousal" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="强度">
                                <el-slider v-model="group.emotion.intensity" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="精力">
                                <el-slider v-model="group.emotion.energy" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                            <el-form-item label="压力">
                                <el-slider v-model="group.emotion.stress" :min="0" :max="1" :step="0.1" show-input size="small" />
                            </el-form-item>
                        </div>

                        <div class="rel-block">
                            <div class="block-label">角色关系</div>
                            <div class="rel-add-row">
                                <el-button size="small" type="primary" @click="openSelectDialog(group)"
                                    >+ 追加已有角色关系</el-button
                                >
                            </div>
                                <div v-for="cid in group.selectedRelChars" :key="cid" class="rel-card">
                                <div class="rel-card-title">
                                    <span>
                                        <template v-if="group.isDefault">→</template>
                                        <template v-else-if="group.relData[cid]?.direction === 'both'">↔</template>
                                        <template v-else-if="group.relData[cid]?.direction === 'incoming'">←</template>
                                        <template v-else>→</template>
                                        {{ charNameMap[cid] || cid }}
                                    </span>
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
                                <div style="text-align:right;margin-top:6px">
                                    <el-button size="small" type="danger" @click="removeRelChar(cid, group)">删除</el-button>
                                </div>
                            </div>
                            <el-empty v-if="!group.selectedRelChars.length" description="暂无关系数据" :image-size="60" />
                        </div>
                    </div>
                </div>
            </el-form>
            <template #footer>
                <el-button @click="dialogVisible = false">取消</el-button>
                <el-button type="primary" @click="submit" :loading="submitting">确定</el-button>
            </template>
        </el-dialog>

        <el-dialog v-model="selectDialogVisible" title="选择已有角色" width="400px" append-to-body>
            <el-table :data="availableChars" max-height="300">
                <el-table-column prop="characterName" label="角色名称" />
                <el-table-column label="操作" width="80">
                    <template #default="{ row }">
                        <el-button size="small" type="primary" @click.stop="addRelChar(row.characterID)">选择</el-button>
                    </template>
                </el-table-column>
            </el-table>
        </el-dialog>
    </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Upload, Download, Delete, Avatar } from "@icon-park/vue-next";
import { useCharacterStore } from "../stores/characterStore.js";
import { useUserCharacterStore } from "../stores/userCharacterStore.js";
import { batchCreateRelationships, listCharacterRelationships, deleteCharacterSessionRelationships } from "../api/characterRelationship.js";
import { listCharacterEmotions, updateCharacterEmotion, exportCharacterCard, importCharacterCards } from "../api/characterCard.js";
import { getSession } from "../api/session.js";

const store = useCharacterStore();
const ucStore = useUserCharacterStore();
const dialogVisible = ref(false);
const isEdit = ref(false);
const editId = ref("");
const submitting = ref(false);
const emotionsBySession = ref({ sessions: [] });
const selectDialogVisible = ref(false);
const currentGroup = ref(null);
const sessionPresentChars = ref([]);
const fileInput = ref(null);

const emptyForm = () => ({
    characterName: "",
    appearance: "",
    personality: "",
    tone: "",
    background: "",
    other: "",
    initialEmotion: {
        emotionLabel: "平静",
        valence: 0.0,
        arousal: 0.5,
        intensity: 0.0,
        energy: 1.0,
        stress: 0.0
    },
    sessionGroups: []
});

const form = reactive(emptyForm());

onMounted(() => {
    store.load();
    ucStore.load();
});

const charNameMap = computed(() => {
    const m = {};
    for (const c of store.cards) m[c.characterID] = c.characterName;
    for (const c of ucStore.cards) m[c.userCharacterID] = c.userCharacterName;
    return m;
});

const availableChars = computed(() => {
    if (!currentGroup.value) return [];
    const excludeIds = new Set([editId.value, ...currentGroup.value.selectedRelChars]);
    let candidates = store.cards.filter((c) => !excludeIds.has(c.characterID));
    if (sessionPresentChars.value.length > 0) {
        candidates = candidates.filter((c) => sessionPresentChars.value.includes(c.characterID));
    }
    return candidates;
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

function avatarStyle(name) {
    const n = name || "?";
    let hue = 0;
    for (let i = 0; i < n.length; i++) hue = (hue * 31 + n.charCodeAt(i)) % 360;
    return {
        background: `linear-gradient(135deg, hsl(${hue}, 65%, 62%), hsl(${(hue + 40) % 360}, 70%, 50%))`
    };
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
    emotionsBySession.value = { sessions: [] };
}

function removeRelChar(cid, group) {
    group.selectedRelChars = group.selectedRelChars.filter((id) => id !== cid);
    delete group.relData[cid];
}

async function openSelectDialog(group) {
    currentGroup.value = group;
    if (!group.isGlobal && group.sessionID) {
        try {
            const session = await getSession(group.sessionID);
            sessionPresentChars.value = Array.isArray(session?.sessionPresentCharacter)
                ? session.sessionPresentCharacter
                : [];
        } catch {
            sessionPresentChars.value = [];
        }
    } else {
        sessionPresentChars.value = [];
    }
    selectDialogVisible.value = true;
}

function addRelChar(cid) {
    const group = currentGroup.value;
    if (!group) return;
    group.selectedRelChars.push(cid);
    group.relData[cid] = { type: "neutral", strength: 0.5, sentiment: 0.0, power_dynamic: 0.0 };
    selectDialogVisible.value = false;
}

function openCreate() {
    isEdit.value = false;
    editId.value = "";
    resetForm();
    form.sessionGroups = [
        { sessionID: "", sessionTitle: "默认（全局）", isGlobal: true, isDefault: true, selectedRelChars: [], relData: {} }
    ];
    dialogVisible.value = true;
}

async function openEdit(row) {
    isEdit.value = true;
    editId.value = row.characterID;
    resetForm();
    form.characterName = row.characterName;
    parseInfo(row.characterInfo);

    if (row.initialEmotion) {
        try {
            const e = typeof row.initialEmotion === "string" ? JSON.parse(row.initialEmotion) : row.initialEmotion;
            if (e && e.emotionLabel !== undefined) {
                form.initialEmotion = {
                    emotionLabel: e.emotionLabel || "平静",
                    valence: e.valence ?? 0.0,
                    arousal: e.arousal ?? 0.5,
                    intensity: e.intensity ?? 0.0,
                    energy: e.energy ?? 1.0,
                    stress: e.stress ?? 0.0
                };
            }
        } catch {}
    }

    const isKnownChar = (cid) =>
        store.cards.find((c) => c.characterID === cid) || ucStore.cards.find((c) => c.userCharacterID === cid);

    try {
        const rels = (await listCharacterRelationships(row.characterID)) || [];

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
            if (r.characterID_1 === row.characterID) {
                otherId = r.characterID_2;
            } else if (r.characterID_2 === row.characterID) {
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
                    direction: r.characterID_1 === row.characterID ? "outgoing" : "incoming"
                };
            } else {
                const existing = groupsMap[key].relData[otherId];
                if (existing.direction === "incoming" && r.characterID_1 === row.characterID) {
                    existing.type = r.relationship_type || existing.type;
                    existing.strength = r.strength ?? existing.strength;
                    existing.sentiment = r.sentiment ?? existing.sentiment;
                    existing.power_dynamic = r.power_dynamic ?? existing.power_dynamic;
                    existing.direction = "both";
                }
            }
        }

        // Merge all isGlobal groups into one. The "__default__" group (from the card's
        // defaultRelationships JSON) is the authoritative source of which characters
        // have a default relationship. Other isGlobal groups only supplement relData
        // (direction info) for characters already in the default set — they do NOT
        // add characters that were previously deleted from the card's JSON.
        // / 合并所有 isGlobal 组为以 __default__ 为准。其他 isGlobal 组仅向已存在的
        //   角色补充 relData 信息，不追加被删除的角色。
        const globalKeys = Object.keys(groupsMap).filter((k) => groupsMap[k].isGlobal);
        if (globalKeys.length > 1) {
            const defaultKey = globalKeys.find((k) => groupsMap[k].isDefault);
            const targetKey = defaultKey || globalKeys[0];
            const target = groupsMap[targetKey];
            for (const key of globalKeys) {
                if (key === targetKey) continue;
                const src = groupsMap[key];
                for (const cid of src.selectedRelChars) {
                    if (target.selectedRelChars.includes(cid) && !target.relData[cid]) {
                        target.relData[cid] = src.relData[cid];
                    }
                }
                delete groupsMap[key];
            }
        }

        // Ensure the surviving global group has isDefault=true so submit can find it.
        const globalGroup = Object.values(groupsMap).find((g) => g.isGlobal);
        if (globalGroup) {
            globalGroup.isDefault = true;
        }

        const sorted = Object.values(groupsMap).sort((a, b) => {
            if (a.isGlobal) return -1;
            if (b.isGlobal) return 1;
            return (a.sessionTitle || "").localeCompare(b.sessionTitle || "");
        });

        if (!sorted.find((g) => g.isGlobal)) {
            sorted.unshift({
                sessionID: "",
                sessionTitle: "默认（全局）",
                isGlobal: true,
                isDefault: true,
                selectedRelChars: [],
                relData: {}
            });
        }

        form.sessionGroups = sorted;
    } catch {
        /* ignore */
    }

    try {
        const resp = (await listCharacterEmotions(row.characterID)) || { sessions: [] };
        emotionsBySession.value = resp;
        for (const session of resp.sessions) {
            let group = form.sessionGroups.find(g => g.sessionID === session.sessionID);
            if (!group) {
                group = {
                    sessionID: session.sessionID,
                    sessionTitle: session.sessionTitle || session.sessionID,
                    isGlobal: false,
                    isDefault: false,
                    selectedRelChars: [],
                    relData: {},
                };
                form.sessionGroups.push(group);
            }
            group.emotion = session;
        }
    } catch {
        emotionsBySession.value = { sessions: [] };
    }

    dialogVisible.value = true;
}

async function submit() {
    if (!form.characterName.trim()) return ElMessage.warning("请输入名称");

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
                characterName: form.characterName,
                characterInfo: infoStr,
                initialEmotion: form.initialEmotion,
                defaultRelationships: defaults
            });
        } else {
            const card = await store.create({
                characterName: form.characterName,
                characterInfo: infoStr,
                initialEmotion: form.initialEmotion
            });
            editId.value = card.characterID;

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
            await deleteCharacterSessionRelationships(editId.value, group.sessionID);
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

        if (isEdit.value) {
            for (const group of form.sessionGroups) {
                if (group.isGlobal || !group.emotion) continue;
                await updateCharacterEmotion(editId.value, {
                    sessionID: group.sessionID,
                    emotionLabel: group.emotion.emotionLabel,
                    valence: group.emotion.valence,
                    arousal: group.emotion.arousal,
                    intensity: group.emotion.intensity,
                    energy: group.emotion.energy,
                    stress: group.emotion.stress,
                    triggerSummary: "手动编辑",
                });
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
        await ElMessageBox.confirm(`确定删除角色「${row.characterName}」？`, "确认");
    } catch {
        return;
    }
    try {
        await store.remove(row.characterID);
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
        await importCharacterCards(data);
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
        const blob = await exportCharacterCard(row.characterID);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${row.characterName}_character.json`;
        a.click();
        URL.revokeObjectURL(url);
        ElMessage.success("导出成功");
    } catch (err) {
        ElMessage.error(err.message || "导出失败");
    }
}
</script>

<style scoped>
.rel-add-row {
    margin-bottom: 10px;
}
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
.group-section {
    border: 1px solid var(--border-light, #e9edf3);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 16px;
    background: var(--el-fill-color-lighter, #fafbfd);
}
.emo-block {
    border: 1px solid var(--brand-200, #c8dcff);
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 12px;
    background: var(--brand-50, #f0f6ff);
}
.rel-block {
    border: 1px solid var(--border-light, #e9edf3);
    border-radius: 10px;
    padding: 12px;
    background: #fff;
}
.block-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted, #909399);
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px dashed var(--border-light, #e9edf3);
}
</style>
