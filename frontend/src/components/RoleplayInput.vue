<template>
    <div class="input-wrapper">
        <el-input
            v-model="text"
            type="textarea"
            :rows="2"
            placeholder="输入你的行动或对话... (Ctrl+Enter 发送)"
            :disabled="disabled"
            @keydown.ctrl.enter="send"
            class="rp-textarea"
        />
        <el-button
            type="primary"
            @click="send"
            :disabled="disabled || !text.trim()"
            :loading="disabled"
            class="rp-send-btn"
        >
            <Send v-if="!disabled" theme="outline" size="14" class="rp-send-icon" />{{ disabled ? "处理中" : "发送" }}
        </el-button>
    </div>
    <div class="rp-input-hint">Ctrl+Enter 发送，支持多行输入</div>
</template>

<script setup>
import { ref } from "vue";
import { Send } from "@icon-park/vue-next";

defineProps({ disabled: { type: Boolean, default: false } });
const emit = defineEmits(["send"]);
const text = ref("");

function send() {
    const val = text.value.trim();
    if (!val) return;
    emit("send", val);
    text.value = "";
}
</script>

<style scoped>
.input-wrapper {
    display: flex;
    gap: 10px;
    align-items: stretch;
}
.rp-textarea {
    flex: 1;
}
.rp-textarea :deep(.el-textarea__inner) {
    border-radius: var(--radius-md, 10px);
    resize: none;
    font-size: 14px;
    line-height: 1.5;
    padding: 10px 12px;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.rp-textarea :deep(.el-textarea__inner:focus) {
    border-color: var(--brand-500, #5d9eff);
    box-shadow: 0 0 0 3px rgba(93, 158, 255, 0.15);
}
.rp-send-btn {
    align-self: stretch;
    min-width: 84px;
    border-radius: var(--radius-md, 10px);
    font-size: 14px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    transition: all 0.2s ease;
}
.rp-send-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(93, 158, 255, 0.35);
}
.rp-send-icon {
    flex-shrink: 0;
}
.rp-input-hint {
    text-align: right;
    font-size: 11px;
    color: var(--text-muted, #909399);
    margin-top: 4px;
    user-select: none;
}
</style>
