<template>
    <el-dialog v-model="visible" title="创建新会话" width="520px" class="rp-dialog" @close="reset">
        <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
            <el-form-item label="会话名称" prop="sessionTitle">
                <el-input v-model="form.sessionTitle" placeholder="输入会话名称" />
            </el-form-item>
            <el-form-item label="世界观" prop="worldviewCollectionID">
                <el-select v-model="form.worldviewCollectionID" placeholder="选择世界观集" style="width: 100%">
                    <el-option
                        v-for="c in worldviewCollections"
                        :key="c.worldviewCollectionID"
                        :label="c.worldviewCollectionName"
                        :value="c.worldviewCollectionID"
                    />
                </el-select>
            </el-form-item>
            <el-form-item label="用户角色">
                <el-select v-model="form.userCharacterID" placeholder="选择用户角色" style="width: 100%" clearable>
                    <el-option
                        v-for="c in userCharacters"
                        :key="c.userCharacterID"
                        :label="c.userCharacterName"
                        :value="c.userCharacterID"
                    />
                </el-select>
            </el-form-item>
            <el-divider content-position="left">初始场景设置</el-divider>
            <el-form-item label="地点">
                <el-input v-model="form.sessionEnvData.location" placeholder="场景所在地点" />
            </el-form-item>
            <el-form-item label="时间">
                <el-input v-model="form.sessionEnvData.time" placeholder="场景时间（如：清晨、黄昏、深夜）" />
            </el-form-item>
            <el-form-item label="氛围">
                <el-input v-model="form.sessionEnvData.atmosphere" placeholder="场景氛围（如：安静、紧张、欢快）" />
            </el-form-item>
            <el-form-item label="在场角色">
                <el-select
                    v-model="form.sessionPresentCharacter"
                    multiple
                    placeholder="选择初始在场的NPC角色"
                    style="width: 100%"
                >
                    <el-option
                        v-for="c in characterCards"
                        :key="c.characterID"
                        :label="c.characterName"
                        :value="c.characterID"
                    />
                </el-select>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="visible = false">取消</el-button>
            <el-button type="primary" @click="submit" :loading="submitting">创建</el-button>
        </template>
    </el-dialog>
</template>

<script setup>
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";

const props = defineProps({
    worldviewCollections: { type: Array, default: () => [] },
    userCharacters: { type: Array, default: () => [] },
    characterCards: { type: Array, default: () => [] }
});

const emit = defineEmits(["created"]);
const visible = ref(false);
const submitting = ref(false);
const formRef = ref(null);

const form = reactive({
    sessionTitle: "",
    worldviewCollectionID: "",
    userCharacterID: "",
    sessionEnvData: { location: "", time: "", atmosphere: "" },
    sessionPresentCharacter: []
});
const rules = {
    sessionTitle: [{ required: true, message: "请输入会话名称", trigger: "blur" }],
    worldviewCollectionID: [{ required: true, message: "请选择世界观", trigger: "change" }]
};

function open() {
    visible.value = true;
}

async function submit() {
    const valid = await formRef.value.validate().catch(() => false);
    if (!valid) return;
    submitting.value = true;
    try {
        const { createSession } = await import("../api/session.js");
        const result = await createSession({
            sessionTitle: form.sessionTitle,
            worldviewCollectionID: form.worldviewCollectionID,
            userCharacterID: form.userCharacterID,
            sessionEnvData: { ...form.sessionEnvData },
            sessionPresentCharacter: form.sessionPresentCharacter
        });
        emit("created", result);
        visible.value = false;
        ElMessage.success("会话创建成功");
    } catch (e) {
        ElMessage.error(e.message || "创建失败");
    } finally {
        submitting.value = false;
    }
}

function reset() {
    form.sessionTitle = "";
    form.worldviewCollectionID = "";
    form.userCharacterID = "";
    form.sessionEnvData = { location: "", time: "", atmosphere: "" };
    form.sessionPresentCharacter = [];
    formRef.value?.clearValidate();
}

defineExpose({ open });
</script>
