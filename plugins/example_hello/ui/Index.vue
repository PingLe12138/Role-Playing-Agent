<template>
    <div class="page-card plugin-demo">
        <div class="plugin-hero">
            <div class="plugin-hero-badge"><Plug theme="outline" size="28" fill="currentColor" /></div>
            <div>
                <h2 class="plugin-hero-title">示例插件 Hello</h2>
                <p class="plugin-hero-desc">
                    演示插件系统的全部接入点：Director 图节点（扇出观测）、Supervisor 挂载子图、REST 端点与前端页面。
                </p>
            </div>
        </div>

        <el-row :gutter="16" class="plugin-cards">
            <el-col :span="12">
                <el-card shadow="never" class="plugin-card">
                    <template #header>
                        <strong class="plugin-card-header"><Link theme="outline" size="14" /> REST 端点</strong>
                    </template>
                    <el-button type="primary" size="small" :loading="loadingHello" @click="callHello">
                        调用 /api/plugins/example_hello/hello
                    </el-button>
                    <pre v-if="hello" class="plugin-json">{{ hello }}</pre>
                </el-card>
            </el-col>
            <el-col :span="12">
                <el-card shadow="never" class="plugin-card">
                    <template #header>
                        <strong class="plugin-card-header"><Share theme="outline" size="14" /> 图贡献</strong>
                    </template>
                    <el-empty v-if="!contributions.length" :image-size="60" description="暂无图贡献" />
                    <ul v-else class="plugin-list">
                        <li v-for="item in contributions" :key="item" class="plugin-list-item">{{ item }}</li>
                    </ul>
                    <div v-if="loadErrors.length" class="plugin-errors">
                        <p v-for="e in loadErrors" :key="e" class="plugin-error-item">{{ e }}</p>
                    </div>
                </el-card>
            </el-col>
        </el-row>
    </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Plug, Link, Share } from "@icon-park/vue-next";
import request from "@rpa/api/request.js";

const hello = ref("");
const loadingHello = ref(false);
const loadErrors = ref([]);

const contributions = computed(() => {
    try {
        return JSON.parse(hello.value)?.graph_contributions || [];
    } catch {
        return [];
    }
});

async function callHello() {
    loadingHello.value = true;
    try {
        const res = await request.get("/api/plugins/example_hello/hello");
        hello.value = JSON.stringify(res, null, 2);
    } catch (err) {
        hello.value = JSON.stringify({ error: err.message }, null, 2);
    } finally {
        loadingHello.value = false;
    }
}

onMounted(async () => {
    await callHello();
    try {
        const data = await request.get("/api/plugins");
        loadErrors.value = (data?.errors || []).map((e) => `[${e.stage}] ${e.message}`);
    } catch {
        /* 插件列表接口异常时忽略，页面内已有端点演示 */
    }
});
</script>

<style scoped>
.plugin-demo {
    max-width: 900px;
}
.plugin-hero {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 16px 4px 20px;
}
.plugin-hero-badge {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    background: linear-gradient(135deg, var(--brand-500, #5d9eff), #3a7de0);
    flex-shrink: 0;
}
.plugin-hero-title {
    margin: 0;
    font-size: 18px;
    color: var(--text-primary, #1e2a3a);
    line-height: 1.4;
}
.plugin-hero-desc {
    margin: 4px 0 0;
    font-size: 13px;
    line-height: 1.7;
    color: var(--text-secondary, #5b6779);
}
.plugin-cards {
    margin-top: 8px;
}
.plugin-card {
    border-radius: 10px;
}
.plugin-card :deep(.el-card__header) {
    padding: 12px 16px;
}
.plugin-card-header {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-primary, #1e2a3a);
}
.plugin-json {
    margin: 12px 0 0;
    padding: 10px;
    background: #161b22;
    border: 1px solid #2d333b;
    color: #d4d4d4;
    font-size: 12px;
    line-height: 1.6;
    border-radius: 8px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: var(--font-mono, "JetBrains Mono", Consolas, monospace);
}
.plugin-list {
    margin: 0;
    padding: 0;
    list-style: none;
}
.plugin-list-item {
    padding: 8px 0;
    font-size: 13px;
    color: var(--text-secondary, #5b6779);
    border-bottom: 1px dashed var(--border-light, #e9edf3);
}
.plugin-list-item:last-child {
    border-bottom: none;
}
.plugin-errors {
    margin-top: 12px;
    padding: 8px 12px;
    border-radius: 8px;
    background: rgba(245, 108, 108, 0.08);
    border: 1px solid rgba(245, 108, 108, 0.25);
}
.plugin-error-item {
    margin: 0;
    font-size: 12px;
    color: #f56c6c;
    line-height: 1.6;
}
</style>
