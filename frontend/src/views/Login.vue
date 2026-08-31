<template>
    <div class="login-root">
        <div class="login-shell">
            <div class="login-brand">
                <span class="login-brand-orb login-brand-orb-1"></span>
                <span class="login-brand-orb login-brand-orb-2"></span>
                <span class="login-brand-orb login-brand-orb-3"></span>
                <div class="login-brand-inner">
                    <span class="login-logo"><span class="login-logo-letter">R</span></span>
                    <h1 class="login-title">RPA 角色扮演</h1>
                    <p class="login-tagline">AI 驱动的多智能体叙事引擎</p>
                    <ul class="login-features">
                        <li><Play theme="outline" size="14" class="login-feature-icon" />多 NPC 并行角色扮演</li>
                        <li><Message theme="outline" size="14" class="login-feature-icon" />实时事件流与玩家抉择</li>
                        <li><MindMapping theme="outline" size="14" class="login-feature-icon" />记忆与关系图谱驱动一致性</li>
                    </ul>
                </div>
            </div>
            <div class="login-panel">
                <div class="login-card">
                    <div v-if="loading && enabled === null" class="login-loading">检查认证状态...</div>
                    <template v-else-if="!enabled">
                        <p class="login-hint">未设置密码，无需认证即可使用</p>
                        <el-button type="primary" class="login-btn" @click="enterApp">进入应用</el-button>
                    </template>
                    <el-form v-else @submit.prevent="onLogin">
                        <el-input
                            v-model="password"
                            type="password"
                            placeholder="输入密码"
                            size="large"
                            :prefix-icon="Lock"
                            @keyup.enter="onLogin"
                        />
                        <el-button type="primary" class="login-btn" :loading="submitting" @click="onLogin"
                            >登录<ArrowRight theme="outline" size="14" class="login-btn-icon"
                        /></el-button>
                    </el-form>
                    <p v-if="error" class="login-error">
                        <Caution theme="filled" size="13" class="login-error-icon" />{{ error }}
                    </p>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { Lock, ArrowRight, Caution, Play, Message, MindMapping } from "@icon-park/vue-next";
import request from "../api/request.js";

const router = useRouter();
const password = ref("");
const enabled = ref(null);
const submitting = ref(false);
const loading = ref(true);
const error = ref("");

function clearSession() {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_bypass");
}

function onBeforeUnload() {
    clearSession();
}

onMounted(async () => {
    clearSession();
    window.addEventListener("beforeunload", onBeforeUnload);
    try {
        const res = await request.get("/api/auth/status");
        if (res?.enabled === true) {
            enabled.value = true;
        } else {
            localStorage.setItem("auth_bypass", "true");
            enabled.value = false;
        }
    } catch {
        enabled.value = false;
        localStorage.setItem("auth_bypass", "true");
    } finally {
        loading.value = false;
    }
});

onUnmounted(() => {
    window.removeEventListener("beforeunload", onBeforeUnload);
});

async function onLogin() {
    if (!password.value) return;
    submitting.value = true;
    error.value = "";
    try {
        const res = await request.post("/api/auth/login", { password: password.value });
        if (res?.token) {
            localStorage.removeItem("auth_bypass");
            localStorage.setItem("auth_token", res.token);
            router.push("/sessions");
        } else {
            error.value = "密码错误";
        }
    } catch (e) {
        error.value = e.message || "登录失败";
    } finally {
        submitting.value = false;
    }
}

function enterApp() {
    router.push("/sessions");
}
</script>

<style scoped>
.login-root {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 24px;
    background:
        radial-gradient(600px 400px at 15% 18%, rgba(93, 158, 255, 0.2), transparent 60%),
        radial-gradient(700px 500px at 85% 82%, rgba(58, 114, 212, 0.18), transparent 60%),
        linear-gradient(135deg, #0f172a 0%, #131c33 55%, #141b33 100%);
}
/* 左右分栏容器 */
.login-shell {
    display: flex;
    width: 880px;
    max-width: 100%;
    border-radius: var(--radius-xl, 20px);
    box-shadow: var(--shadow-4, 0 12px 32px rgba(16, 24, 40, 0.16), 0 24px 64px rgba(16, 24, 40, 0.12));
    overflow: hidden;
    background: #fff;
    animation: login-in 0.35s ease-out;
}
@keyframes login-in {
    from {
        opacity: 0;
        transform: translateY(14px);
    }
    to {
        opacity: 1;
        transform: none;
    }
}
/* 左侧品牌区（纯蓝深色，无紫色调） */
.login-brand {
    flex: 1 1 46%;
    padding: 48px 36px;
    position: relative;
    overflow: hidden;
    background: linear-gradient(160deg, #0f1b33 0%, #13294d 60%, #1a3a66 100%);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
}
.login-brand-inner {
    position: relative;
    z-index: 1;
    max-width: 320px;
}
/* 浮动装饰圆 */
.login-brand-orb {
    position: absolute;
    border-radius: 50%;
    background: rgba(93, 158, 255, 0.14);
}
.login-brand-orb-1 {
    width: 220px;
    height: 220px;
    top: -60px;
    right: -50px;
    animation: orb-float 8s ease-in-out infinite;
}
.login-brand-orb-2 {
    width: 150px;
    height: 150px;
    bottom: -40px;
    left: -30px;
    animation: orb-float 10s ease-in-out infinite reverse;
}
.login-brand-orb-3 {
    width: 90px;
    height: 90px;
    top: 38%;
    left: 10%;
    animation: orb-float 12s ease-in-out infinite;
}
@keyframes orb-float {
    0%,
    100% {
        transform: translateY(0);
    }
    50% {
        transform: translateY(-18px);
    }
}
.login-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    border-radius: 13px;
    background: var(--brand-500, #5d9eff);
    box-shadow: 0 6px 16px rgba(93, 158, 255, 0.45);
    animation: logo-breathe 3s ease-in-out infinite;
}
@keyframes logo-breathe {
    0%,
    100% {
        box-shadow: 0 6px 16px rgba(93, 158, 255, 0.45);
    }
    50% {
        box-shadow: 0 6px 24px rgba(93, 158, 255, 0.65);
    }
}
.login-logo-letter {
    color: #fff;
    font-size: 24px;
    font-weight: 700;
    line-height: 1;
}
.login-title {
    font-size: 24px;
    color: #fff;
    margin: 18px 0 6px;
    letter-spacing: 0.5px;
}
.login-tagline {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.65);
    margin: 0 0 30px;
}
.login-features {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 13px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.88);
}
.login-features li {
    display: flex;
    align-items: center;
    gap: 8px;
}
.login-feature-icon {
    color: #7fb2ff;
    flex-shrink: 0;
}
/* 右侧表单区 */
.login-panel {
    flex: 1 1 54%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px 40px;
    background: #fff;
}
.login-card {
    width: 100%;
    max-width: 320px;
    text-align: center;
}
.login-loading {
    color: #909399;
    font-size: 14px;
    padding: 12px 0;
}
.login-hint {
    color: #909399;
    font-size: 14px;
    margin: 0 0 20px;
}
.login-btn {
    width: 100%;
    margin-top: 18px;
    border-radius: 10px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
}
.login-btn-icon {
    flex-shrink: 0;
}
.login-error {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    color: #f56c6c;
    font-size: 13px;
    margin-top: 12px;
}
.login-error-icon {
    flex-shrink: 0;
}
/* 窄屏：隐藏品牌区 */
@media (max-width: 720px) {
    .login-brand {
        display: none;
    }
    .login-panel {
        padding: 40px 24px;
    }
}
</style>
