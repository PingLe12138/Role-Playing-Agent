<template>
    <div class="setup-root">
        <div class="setup-shell">
            <aside class="setup-aside">
                <span class="setup-orb setup-orb-1"></span>
                <span class="setup-orb setup-orb-2"></span>
                <div class="setup-aside-inner">
                    <span class="setup-logo"><span class="setup-logo-letter">R</span></span>
                    <h1 class="setup-brand">RPA 角色扮演</h1>
                    <p class="setup-tagline">首次使用，先花一分钟完成初始化</p>
                    <ol class="setup-steps">
                        <li
                            v-for="(s, i) in STEPS"
                            :key="s.key"
                            :class="{
                                'is-active': i === step,
                                'is-done': i < step
                            }"
                        >
                            <span class="setup-step-mark">
                                <Check v-if="i < step" theme="filled" size="12" />
                                <template v-else>{{ i + 1 }}</template>
                            </span>
                            <span class="setup-step-text">
                                <span class="setup-step-title">{{ s.title }}</span>
                                <span class="setup-step-desc">{{ s.desc }}</span>
                            </span>
                        </li>
                    </ol>
                </div>
            </aside>

            <section class="setup-main">
                <div v-if="loading" class="setup-loading">正在读取当前配置...</div>
                <template v-else>
                    <header class="setup-head">
                        <h2>{{ STEPS[step].head }}</h2>
                        <p>{{ STEPS[step].sub }}</p>
                    </header>

                    <div class="setup-body">
                        <!-- Step 1: 欢迎 -->
                        <div v-if="step === 0" class="step-welcome">
                            <div class="welcome-grid">
                                <div class="welcome-item">
                                    <Api theme="outline" size="18" class="welcome-icon" />
                                    <div>
                                        <div class="welcome-title">接入大模型</div>
                                        <div class="welcome-desc">填写 API Key 与模型，一键测试连通性</div>
                                    </div>
                                </div>
                                <div class="welcome-item">
                                    <Checklist theme="outline" size="18" class="welcome-icon" />
                                    <div>
                                        <div class="welcome-title">选择玩法</div>
                                        <div class="welcome-desc">玩家抉择、记忆总结节奏随你调整</div>
                                    </div>
                                </div>
                                <div class="welcome-item">
                                    <Picture theme="outline" size="18" class="welcome-icon" />
                                    <div>
                                        <div class="welcome-title">可选扩展</div>
                                        <div class="welcome-desc">接入 ComfyUI 后自动为场景生成插画</div>
                                    </div>
                                </div>
                            </div>
                            <p class="welcome-note">
                                所有配置都保存在本地
                                <code>config.json</code>，之后可以在「配置」页面随时修改，也可以重新运行本引导。
                            </p>
                            <el-alert
                                v-if="status && status.llm_configured"
                                type="success"
                                :closable="false"
                                show-icon
                                title="检测到已存在的模型配置，向导会预填当前的连接信息，你可以直接沿用。"
                            />
                        </div>

                        <!-- Step 2: LLM 连接 -->
                        <el-form
                            v-else-if="step === 1"
                            :model="form"
                            label-width="96px"
                            class="setup-form"
                            @submit.prevent
                        >
                            <el-form-item label="协议">
                                <el-select v-model="form.protocol" style="width: 200px" @change="onProtocolChange">
                                    <el-option label="OpenAI 兼容" value="openai" />
                                    <el-option label="Anthropic" value="anthropic" />
                                </el-select>
                            </el-form-item>
                            <el-form-item label="API Key" required>
                                <el-input v-model="form.api_key" type="password" show-password placeholder="sk-..." />
                            </el-form-item>
                            <el-form-item label="Base URL">
                                <el-input v-model="form.base_url" :placeholder="baseUrlPlaceholder" />
                                <div class="field-hint">服务地址，留空则使用 SDK 默认地址</div>
                            </el-form-item>
                            <el-form-item label="模型" required>
                                <el-input v-model="form.default_model" placeholder="deepseek-v4-flash" />
                            </el-form-item>
                            <el-form-item label="默认温度">
                                <el-slider
                                    v-model="form.default_temperature"
                                    :min="0"
                                    :max="2"
                                    :step="0.1"
                                    style="width: 200px"
                                    :disabled="form.is_enable_thinking === 'enabled'"
                                />
                                <span
                                    class="field-val"
                                    :class="{ 'field-val-off': form.is_enable_thinking === 'enabled' }"
                                    >{{ Number(form.default_temperature || 0).toFixed(1) }}</span
                                >
                            </el-form-item>
                            <el-form-item label="思考模式">
                                <el-switch
                                    v-model="form.is_enable_thinking"
                                    active-value="enabled"
                                    inactive-value="disabled"
                                />
                                <span class="field-inline-hint">开启后忽略温度参数</span>
                            </el-form-item>
                            <div class="setup-actions-inline">
                                <el-button :loading="testing" @click="testConnection">
                                    <Link theme="outline" size="14" class="btn-icon" />测试连接
                                </el-button>
                            </div>
                            <div v-if="testResult" :class="['setup-test', testResult.success ? 'is-ok' : 'is-fail']">
                                <Check v-if="testResult.success" theme="filled" size="15" />
                                <Caution v-else theme="filled" size="15" />
                                <span v-if="testResult.success">
                                    连接成功（{{ testResult.elapsed_ms }}ms）：{{ testResult.response }}
                                </span>
                                <span v-else>{{ testResult.error }}</span>
                            </div>
                        </el-form>

                        <!-- Step 3: 功能与扩展 -->
                        <div v-else-if="step === 2" class="step-features">
                            <el-form label-width="110px" class="setup-form">
                                <el-form-item label="玩家选择">
                                    <el-switch v-model="features.player_choice_enabled" />
                                    <span class="field-inline-hint">剧情推进到关键处时弹出选项，由你决定走向</span>
                                </el-form-item>
                                <el-form-item label="记忆间隔">
                                    <el-input-number v-model="features.memory_summarize_interval" :min="1" :step="1" />
                                    <span class="field-inline-hint">每隔 N 轮对话总结一次角色记忆</span>
                                </el-form-item>
                            </el-form>

                            <div class="setup-block">
                                <div class="setup-block-head">
                                    <el-switch v-model="imageGen.enabled" size="small" />
                                    <span class="setup-block-title">
                                        <Picture theme="outline" size="14" />场景插画（ComfyUI）
                                    </span>
                                </div>
                                <p class="setup-block-note">
                                    需要自行部署 ComfyUI 服务；未开启时不影响任何对话功能，可稍后在配置页开启。
                                </p>
                                <el-form v-if="imageGen.enabled" label-width="110px" size="small" class="setup-form">
                                    <el-form-item label="服务地址">
                                        <el-input
                                            v-model="imageGen.comfyui_base_url"
                                            placeholder="http://127.0.0.1:8188"
                                        />
                                    </el-form-item>
                                    <el-form-item label="大模型">
                                        <el-input
                                            v-model="imageGen.checkpoint"
                                            placeholder="animagine-xl-4.0.safetensors"
                                        />
                                    </el-form-item>
                                    <div class="setup-actions-inline">
                                        <el-button :loading="testingComfy" @click="testComfy">
                                            <Link theme="outline" size="14" class="btn-icon" />测试服务
                                        </el-button>
                                    </div>
                                    <div
                                        v-if="comfyResult"
                                        :class="['setup-test', comfyResult.success ? 'is-ok' : 'is-fail']"
                                    >
                                        <Check v-if="comfyResult.success" theme="filled" size="15" />
                                        <Caution v-else theme="filled" size="15" />
                                        <span v-if="comfyResult.success">
                                            服务可用（{{ comfyResult.elapsed_ms }}ms）<template
                                                v-if="comfyResult.checkpoints?.length"
                                                >，检测到 {{ comfyResult.checkpoints.length }} 个模型</template
                                            >
                                        </span>
                                        <span v-else>{{ comfyResult.error }}</span>
                                    </div>
                                </el-form>
                            </div>
                        </div>

                        <!-- Step 4: 完成 -->
                        <div v-else class="step-done">
                            <ul class="done-list">
                                <li>
                                    <Check v-if="llmDone" theme="filled" size="15" class="done-ok" />
                                    <Caution v-else theme="filled" size="15" class="done-warn" />
                                    <div>
                                        <div class="done-title">模型连接</div>
                                        <div class="done-desc">
                                            {{
                                                llmDone
                                                    ? `${form.default_model || "已配置"}${
                                                          form.base_url ? ` · ${form.base_url}` : ""
                                                      }`
                                                    : "尚未填写 API Key，可在配置页补齐后再开始对话"
                                            }}
                                        </div>
                                    </div>
                                </li>
                                <li>
                                    <Check v-if="status?.embedding?.ready" theme="filled" size="15" class="done-ok" />
                                    <Caution v-else theme="filled" size="15" class="done-warn" />
                                    <div>
                                        <div class="done-title">本地嵌入模型</div>
                                        <div class="done-desc">
                                            {{
                                                status?.embedding?.ready
                                                    ? status.embedding.path
                                                    : `未找到模型文件（${status?.embedding?.path || "models/"}），世界观检索可能不可用`
                                            }}
                                        </div>
                                    </div>
                                </li>
                                <li>
                                    <Check
                                        v-if="!imageGen.enabled || comfyOk"
                                        theme="filled"
                                        size="15"
                                        class="done-ok"
                                    />
                                    <Caution v-else theme="filled" size="15" class="done-warn" />
                                    <div>
                                        <div class="done-title">场景插画</div>
                                        <div class="done-desc">
                                            {{
                                                !imageGen.enabled
                                                    ? "未开启（可选功能）"
                                                    : comfyOk
                                                      ? `已连接 ${imageGen.comfyui_base_url}`
                                                      : "已开启但服务未验证，剧情中会自动跳过失败的生成"
                                            }}
                                        </div>
                                    </div>
                                </li>
                            </ul>
                            <p class="done-note">接下来：在「世界观」中创建一个世界观，再到「会话」里开始你的故事。</p>
                        </div>
                    </div>

                    <footer class="setup-foot">
                        <div class="foot-left">
                            <el-button v-if="step > 0" text @click="prev">上一步</el-button>
                        </div>
                        <div class="foot-right">
                            <el-button v-if="step < STEPS.length - 1" text @click="skipSetup">跳过引导</el-button>
                            <el-button v-if="step === 0" type="primary" @click="next">开始配置</el-button>
                            <el-button
                                v-else-if="step < STEPS.length - 1"
                                type="primary"
                                :loading="saving"
                                @click="next"
                            >
                                下一步
                            </el-button>
                            <el-button v-else type="primary" :loading="saving" @click="finish">
                                进入应用<ArrowRight theme="outline" size="14" class="btn-icon" />
                            </el-button>
                        </div>
                    </footer>
                </template>
            </section>
        </div>
    </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Api, ArrowRight, Caution, Check, Checklist, Link, Picture } from "@icon-park/vue-next";
import { getSetupStatus, completeSetup } from "../api/setup.js";
import {
    getFeatures,
    getImageGenerationConfig,
    testImageGenerationConfig,
    testLlmConfig,
    updateFeatures,
    updateImageGenerationConfig,
    updateLlmConfig
} from "../api/config.js";
import { markSetupCompleted } from "../router";

const router = useRouter();

const STEPS = [
    {
        key: "welcome",
        title: "欢迎",
        desc: "了解将要配置的内容",
        head: "欢迎使用 RPA 角色扮演",
        sub: "多智能体驱动的沉浸式叙事引擎，先完成几项基础配置即可开始"
    },
    {
        key: "llm",
        title: "模型连接",
        desc: "API Key 与模型",
        head: "接入大模型",
        sub: "系统通过 OpenAI 兼容接口调用模型，填写后建议先测试连通性"
    },
    {
        key: "features",
        title: "功能偏好",
        desc: "玩法与可选扩展",
        head: "选择你的玩法",
        sub: "这些设置之后都能在配置页随时调整"
    },
    { key: "done", title: "完成", desc: "核对并开始", head: "配置完成", sub: "以下是本次初始化的结果核对" }
];

const URL_PATTERN = /^https?:\/\/.+/;

// Base URL 占位符随协议切换；切换协议时若地址仍为另一协议的默认值则一并替换
const baseUrlPlaceholder = computed(() =>
    form.protocol === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1"
);
const PROTOCOL_DEFAULT_URLS = {
    openai: "https://api.openai.com/v1",
    anthropic: "https://api.anthropic.com"
};
function onProtocolChange() {
    const defaults = Object.values(PROTOCOL_DEFAULT_URLS);
    if (!form.base_url || defaults.includes(form.base_url)) {
        form.base_url = PROTOCOL_DEFAULT_URLS[form.protocol];
    }
}

const step = ref(0);
const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const testingComfy = ref(false);
const testResult = ref(null);
const comfyResult = ref(null);
const status = ref(null);

const form = reactive({
    protocol: "openai",
    api_key: "",
    base_url: "",
    default_model: "",
    default_temperature: 0.9,
    default_max_tokens: 8192,
    is_enable_thinking: "enabled"
});
const features = reactive({
    player_choice_enabled: true,
    memory_summarize_interval: 10
});
const imageGen = reactive({
    enabled: false,
    comfyui_base_url: "http://127.0.0.1:8188",
    checkpoint: ""
});

const llmDone = computed(() => Boolean((form.api_key || "").trim() && (form.default_model || "").trim()));
const comfyOk = computed(() => Boolean(comfyResult.value?.success));

onMounted(async () => {
    try {
        const st = await getSetupStatus();
        // Already onboarded (e.g. the user typed /setup manually) → back inside.
        if (st?.completed) {
            router.replace("/sessions");
            return;
        }
        status.value = st || {};
        if (st?.llm) Object.assign(form, st.llm);
        if (st?.features) Object.assign(features, st.features);
        if (st?.image_generation) Object.assign(imageGen, st.image_generation);
    } catch (e) {
        ElMessage.error(e.message || "读取配置失败");
    }
    // Backfill anything the status payload left empty (older backends, or a
    // config.json whose features/image_generation sections were removed).
    // / 补齐状态接口未覆盖的字段（旧后端，或 config.json 缺少对应配置段）。
    try {
        const [feats, ig] = await Promise.all([getFeatures(), getImageGenerationConfig()]);
        if (feats) Object.assign(features, feats);
        if (ig?.comfyui_base_url) imageGen.comfyui_base_url = ig.comfyui_base_url;
        if (ig?.checkpoint) imageGen.checkpoint = imageGen.checkpoint || ig.checkpoint;
    } catch {
        /* keep defaults */
    } finally {
        loading.value = false;
    }
});

function validURL(url) {
    if (!url) return true;
    if (!URL_PATTERN.test(url)) {
        ElMessage.warning("地址格式不正确，应以 http:// 或 https:// 开头");
        return false;
    }
    return true;
}

async function testConnection() {
    if (!validURL(form.base_url)) return;
    if (!(form.api_key || "").trim() || !(form.default_model || "").trim()) {
        ElMessage.warning("请先填写 API Key 与模型名称");
        return;
    }
    testing.value = true;
    testResult.value = null;
    try {
        testResult.value = await testLlmConfig({
            protocol: form.protocol,
            api_key: form.api_key,
            base_url: form.base_url,
            default_model: form.default_model
        });
    } catch (e) {
        testResult.value = { success: false, error: e.message || "请求失败", elapsed_ms: 0 };
    } finally {
        testing.value = false;
    }
}

async function testComfy() {
    if (!validURL(imageGen.comfyui_base_url)) return;
    testingComfy.value = true;
    try {
        comfyResult.value = await testImageGenerationConfig({
            comfyui_base_url: imageGen.comfyui_base_url
        });
    } catch (e) {
        comfyResult.value = { success: false, error: e.message || "请求失败", elapsed_ms: 0 };
    } finally {
        testingComfy.value = false;
    }
}

function prev() {
    if (step.value > 0) step.value -= 1;
}

async function next() {
    if (step.value === 1) await saveLlm();
    else if (step.value === 2) await saveFeatures();
    else step.value += 1;
}

async function saveLlm() {
    if (!(form.api_key || "").trim() || !(form.default_model || "").trim()) {
        ElMessage.warning("API Key 与模型名称为必填项");
        return;
    }
    if (!validURL(form.base_url)) return;
    saving.value = true;
    try {
        await updateLlmConfig({ ...form });
        step.value += 1;
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        saving.value = false;
    }
}

async function saveFeatures() {
    if (imageGen.enabled && !validURL(imageGen.comfyui_base_url)) return;
    saving.value = true;
    try {
        await updateFeatures({ ...features });
        await updateImageGenerationConfig({
            enabled: imageGen.enabled,
            comfyui_base_url: imageGen.comfyui_base_url,
            checkpoint: imageGen.checkpoint
        });
        step.value += 1;
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        saving.value = false;
    }
}

async function finish() {
    saving.value = true;
    try {
        await completeSetup({ skipped: false });
        markSetupCompleted();
        ElMessage.success("初始化完成");
        router.replace("/sessions");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        saving.value = false;
    }
}

async function skipSetup() {
    try {
        await ElMessageBox.confirm(
            "跳过后将直接进入系统，未配置的模型会导致对话无法生成内容。确定跳过吗？",
            "跳过初始化引导",
            { confirmButtonText: "仍要跳过", cancelButtonText: "继续配置", type: "warning" }
        );
    } catch {
        return;
    }
    saving.value = true;
    try {
        await completeSetup({ skipped: true });
        markSetupCompleted();
        router.replace("/sessions");
    } catch (e) {
        ElMessage.error(e.message || "保存失败");
    } finally {
        saving.value = false;
    }
}
</script>

<style scoped>
.setup-root {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 28px 20px;
    background:
        radial-gradient(620px 420px at 12% 14%, rgba(93, 158, 255, 0.14), transparent 60%),
        radial-gradient(700px 480px at 88% 86%, rgba(58, 114, 212, 0.12), transparent 60%),
        linear-gradient(135deg, #f4f7fb 0%, #eaf1fb 100%);
}
.setup-shell {
    display: flex;
    width: 940px;
    max-width: 100%;
    min-height: 560px;
    border-radius: 18px;
    overflow: hidden;
    background: #fff;
    box-shadow:
        0 12px 32px rgba(16, 24, 40, 0.12),
        0 24px 64px rgba(16, 24, 40, 0.08);
}
/* 左侧品牌 + 步骤条 */
.setup-aside {
    flex: 0 0 300px;
    position: relative;
    overflow: hidden;
    padding: 40px 30px;
    color: #fff;
    background: linear-gradient(160deg, #0f1b33 0%, #13294d 60%, #1a3a66 100%);
    display: flex;
    align-items: center;
}
.setup-orb {
    position: absolute;
    border-radius: 50%;
    background: rgba(93, 158, 255, 0.16);
}
.setup-orb-1 {
    width: 200px;
    height: 200px;
    top: -70px;
    right: -60px;
}
.setup-orb-2 {
    width: 130px;
    height: 130px;
    bottom: -40px;
    left: -40px;
}
.setup-aside-inner {
    position: relative;
    z-index: 1;
    width: 100%;
}
.setup-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: var(--brand-500, #5d9eff);
    box-shadow: 0 6px 16px rgba(93, 158, 255, 0.45);
}
.setup-logo-letter {
    color: #fff;
    font-size: 22px;
    font-weight: 700;
}
.setup-brand {
    font-size: 20px;
    color: #fff;
    margin: 16px 0 4px;
    letter-spacing: 0.5px;
}
.setup-tagline {
    font-size: 12.5px;
    color: rgba(255, 255, 255, 0.62);
    margin: 0 0 28px;
}
.setup-steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 18px;
}
.setup-steps li {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    opacity: 0.5;
    transition: opacity 0.2s;
}
.setup-steps li.is-active,
.setup-steps li.is-done {
    opacity: 1;
}
.setup-step-mark {
    flex-shrink: 0;
    width: 22px;
    height: 22px;
    margin-top: 1px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 0.35);
    color: rgba(255, 255, 255, 0.8);
}
.setup-steps li.is-active .setup-step-mark {
    background: var(--brand-500, #5d9eff);
    border-color: transparent;
    color: #fff;
    box-shadow: 0 0 0 4px rgba(93, 158, 255, 0.22);
}
.setup-steps li.is-done .setup-step-mark {
    background: rgba(82, 196, 127, 0.9);
    border-color: transparent;
    color: #fff;
}
.setup-step-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.setup-step-title {
    font-size: 13.5px;
    font-weight: 600;
    color: #fff;
}
.setup-step-desc {
    font-size: 11.5px;
    color: rgba(255, 255, 255, 0.55);
}
/* 右侧内容区 */
.setup-main {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    padding: 34px 36px 24px;
    min-width: 0;
}
.setup-loading {
    margin: auto;
    color: #909399;
    font-size: 14px;
}
.setup-head h2 {
    margin: 0 0 6px;
    font-size: 19px;
    font-weight: 600;
    color: #1f2d3d;
}
.setup-head p {
    margin: 0 0 22px;
    font-size: 13px;
    color: #909399;
    line-height: 1.6;
}
.setup-body {
    flex: 1 1 auto;
    min-height: 300px;
}
/* 欢迎步 */
.welcome-grid {
    display: flex;
    flex-direction: column;
    gap: 14px;
}
.welcome-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 14px 16px;
    border: 1px solid #e6ecf5;
    border-radius: 12px;
    background: #f8fbff;
}
.welcome-icon {
    color: var(--brand-500, #5d9eff);
    flex-shrink: 0;
    margin-top: 1px;
}
.welcome-title {
    font-size: 14px;
    font-weight: 600;
    color: #1f2d3d;
}
.welcome-desc {
    font-size: 12.5px;
    color: #7b8794;
    margin-top: 2px;
}
.welcome-note {
    margin: 18px 0;
    font-size: 12.5px;
    color: #7b8794;
    line-height: 1.7;
}
.welcome-note code {
    background: #f2f5fa;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 12px;
}
/* 表单 */
.setup-form :deep(.el-form-item) {
    margin-bottom: 18px;
}
.field-hint {
    font-size: 11.5px;
    color: #a8b2bd;
    line-height: 1.5;
    margin-top: 2px;
}
.field-inline-hint {
    margin-left: 10px;
    font-size: 12.5px;
    color: #909399;
}
.field-val {
    margin-left: 12px;
    font-size: 13px;
    color: #606266;
}
.field-val-off {
    color: #c0c4cc;
}
.setup-actions-inline {
    margin: 4px 0 14px;
}
.setup-test {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 9px 12px;
    border-radius: 8px;
    font-size: 12.5px;
    line-height: 1.5;
    word-break: break-all;
}
.setup-test.is-ok {
    background: #f0f9eb;
    color: #67c23a;
}
.setup-test.is-fail {
    background: #fef0f0;
    color: #f56c6c;
}
/* 功能偏好步 */
.setup-block {
    margin-top: 8px;
    padding: 16px;
    border: 1px solid #e6ecf5;
    border-radius: 12px;
    background: #fbfcfe;
}
.setup-block-head {
    display: flex;
    align-items: center;
    gap: 10px;
}
.setup-block-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    font-weight: 600;
    color: #1f2d3d;
}
.setup-block-note {
    margin: 8px 0 0;
    font-size: 12px;
    color: #909399;
    line-height: 1.6;
}
.setup-block .setup-form {
    margin-top: 14px;
}
/* 完成步 */
.done-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
}
.done-list li {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 13px 16px;
    border: 1px solid #e6ecf5;
    border-radius: 12px;
}
.done-ok {
    color: #67c23a;
    margin-top: 2px;
    flex-shrink: 0;
}
.done-warn {
    color: #e6a23c;
    margin-top: 2px;
    flex-shrink: 0;
}
.done-title {
    font-size: 13.5px;
    font-weight: 600;
    color: #1f2d3d;
}
.done-desc {
    font-size: 12.5px;
    color: #7b8794;
    margin-top: 2px;
    word-break: break-all;
}
.done-note {
    margin: 20px 0 0;
    font-size: 12.5px;
    color: #909399;
    line-height: 1.7;
}
/* 底部操作区 */
.setup-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-top: 18px;
    margin-top: 18px;
    border-top: 1px solid #eef2f7;
}
.foot-right {
    display: flex;
    align-items: center;
    gap: 10px;
}
.btn-icon {
    flex-shrink: 0;
}
@media (max-width: 820px) {
    .setup-aside {
        display: none;
    }
    .setup-main {
        padding: 28px 22px 20px;
    }
}
</style>
