<template>
    <el-container class="app-layout">
        <el-header class="app-topbar">
            <div class="topbar-left">
                <img :src="logoUrl" class="logo-img" alt="RPA 角色扮演" />
                <span class="logo-text">RPA 角色扮演</span>
                <el-menu
                    :ellipsis="false"
                    :default-active="activeMenu"
                    mode="horizontal"
                    class="topbar-menu"
                    @select="handleMenuSelect"
                >
                    <el-menu-item index="/sessions"
                        ><span class="menu-item-inner"
                            ><Message theme="outline" size="16" fill="currentColor" />会话</span
                        ></el-menu-item
                    >
                    <el-menu-item index="/character-cards"
                        ><span class="menu-item-inner"
                            ><People theme="outline" size="16" fill="currentColor" />角色卡</span
                        ></el-menu-item
                    >
                    <el-menu-item index="/user-characters"
                        ><span class="menu-item-inner"
                            ><Avatar theme="outline" size="16" fill="currentColor" />用户角色</span
                        ></el-menu-item
                    >
                    <el-menu-item index="/worldview-sets"
                        ><span class="menu-item-inner"
                            ><CollectionRecords theme="outline" size="16" fill="currentColor" />世界观</span
                        ></el-menu-item
                    >
                    <el-menu-item index="/logs"
                        ><span class="menu-item-inner"
                            ><FileText theme="outline" size="16" fill="currentColor" />日志</span
                        ></el-menu-item
                    >
                    <el-menu-item index="/config"
                        ><span class="menu-item-inner"
                            ><Setting theme="outline" size="16" fill="currentColor" />配置</span
                        ></el-menu-item
                    >
                    <!-- Plugin-contributed pages appear dynamically (from /api/plugins).
                         / 插件贡献页面动态展示（来自 /api/plugins）。 -->
                    <el-menu-item v-for="page in pluginPages" :key="page.path" :index="page.path"
                        ><span class="menu-item-inner"
                            ><component :is="resolvePageIcon(page.icon)" theme="outline" size="16" fill="currentColor" />
                            {{ page.title }}</span
                        ></el-menu-item
                    >
                </el-menu>
            </div>
            <div class="topbar-right">
                <el-tooltip content="清空全部数据（不可恢复）" placement="bottom">
                    <el-button class="clear-all-btn" size="small" @click="handleClearAll">
                        <Caution theme="filled" size="13" fill="#f56c6c" />清除所有数据
                    </el-button>
                </el-tooltip>
            </div>
        </el-header>
        <el-main class="app-main">
            <router-view v-slot="{ Component }">
                <transition name="page-fade" mode="out-in">
                    <keep-alive :include="['Roleplay']">
                        <component :is="Component" />
                    </keep-alive>
                </transition>
            </router-view>
        </el-main>
    </el-container>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Message, People, Avatar, CollectionRecords, FileText, Setting, Caution } from "@icon-park/vue-next";
import { ElMessage, ElMessageBox } from "element-plus";
import { clearAll } from "../api/config.js";
import { pluginPages, resolvePageIcon } from "../plugins/index.js";
import logoUrl from "../assets/logo.svg";

const route = useRoute();
const router = useRouter();

// 会话详情页（/sessions/:id）也高亮"会话"菜单
const activeMenu = computed(() => {
    if (route.path.startsWith("/sessions")) return "/sessions";
    return route.path;
});

function handleMenuSelect(index) {
    router.push(index);
}

async function handleClearAll() {
    try {
        await ElMessageBox.confirm("确定清除所有数据？此操作不可恢复！", "警告", {
            confirmButtonText: "确定",
            cancelButtonText: "取消",
            type: "warning"
        });
        await clearAll();
        ElMessage.success("所有数据已清除");
        location.reload();
    } catch {
        /* cancelled */
    }
}
</script>

<style scoped>
/* 淡蓝色氛围光晕（纯蓝，无紫色调） */
.app-layout {
    height: 100vh;
    background:
        radial-gradient(1100px 520px at 18% -8%, rgba(93, 158, 255, 0.09), transparent 60%),
        radial-gradient(900px 480px at 108% 6%, rgba(93, 158, 255, 0.06), transparent 60%),
        var(--app-bg, #f4f7fb);
    min-width: 100%;
}
.app-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    background: var(--app-nav-bg, #0f1b33);
    height: 56px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
    border-bottom: 1px solid rgba(93, 158, 255, 0.55);
}
.topbar-left {
    display: flex;
    align-items: center;
    gap: 12px;
    overflow: visible;
    flex: 1;
}
.logo-img {
    width: 30px;
    height: 30px;
    flex-shrink: 0;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(60, 120, 220, 0.45);
}
.logo-text {
    color: #fff;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.5px;
    white-space: nowrap;
    flex-shrink: 0;
}
/* 颜色统一走 CSS 变量（不再硬编码），与 --app-nav-bg 保持一致 */
.topbar-menu {
    --el-menu-bg-color: transparent;
    --el-menu-text-color: #a0afbe;
    --el-menu-active-color: #ffffff;
    --el-menu-hover-bg-color: rgba(255, 255, 255, 0.05);
    --el-menu-hover-text-color: #ffffff;
    border-bottom: none;
    background: transparent;
    overflow: visible !important;
    flex-shrink: 0;
    min-width: max-content;
}
.topbar-menu .el-menu-item {
    position: relative;
    border-bottom: none;
    height: 56px;
    line-height: normal;
    padding: 0 10px;
    white-space: nowrap;
    flex-shrink: 0;
}
.topbar-menu .el-menu-item:hover {
    background-color: rgba(255, 255, 255, 0.05) !important;
}
.topbar-menu .el-menu-item.is-active {
    color: #fff !important;
}
.topbar-menu .el-menu-item.is-active::after {
    content: "";
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 0;
    height: 3px;
    border-radius: 3px 3px 0 0;
    background: var(--brand-500, #5d9eff);
}
.menu-item-inner {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
}
.topbar-right {
    flex-shrink: 0;
}
.clear-all-btn {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: #c9d4e3;
    border-radius: 6px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: all 0.2s;
}
.clear-all-btn:hover {
    background: rgba(245, 108, 108, 0.16);
    border-color: rgba(245, 108, 108, 0.5);
    color: #f56c6c;
}
.app-main {
    background: transparent;
    padding: 20px;
    overflow-y: auto;
    height: calc(100vh - 56px);
}
</style>
