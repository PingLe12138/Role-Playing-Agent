import { createRouter, createWebHistory } from "vue-router";
import { getSetupStatus } from "../api/setup.js";

const routes = [
    { path: "/", redirect: "/sessions" },
    { path: "/login", name: "Login", component: () => import("../views/Login.vue") },
    { path: "/setup", name: "Setup", component: () => import("../views/SetupWizard.vue") },
    {
        path: "/",
        component: () => import("../components/AppLayout.vue"),
        children: [
            { path: "character-cards", name: "CharacterCards", component: () => import("../views/CharacterCards.vue") },
            { path: "user-characters", name: "UserCharacters", component: () => import("../views/UserCharacters.vue") },
            { path: "worldview-sets", name: "WorldViewSets", component: () => import("../views/WorldViewSets.vue") },
            { path: "sessions", name: "Sessions", component: () => import("../views/Sessions.vue") },
            { path: "sessions/:id", name: "Roleplay", component: () => import("../views/Roleplay.vue"), props: true },
            { path: "config", name: "Config", component: () => import("../views/Config.vue") },
            { path: "logs", name: "Logs", component: () => import("../views/Logs.vue") }
        ]
    }
];

const router = createRouter({ history: createWebHistory(), routes });

// ─── First-run setup wizard gate ─────────────────────────────────────────
// The wizard state is fetched once per page load and cached here; a false
// "needs setup" (backend unreachable) intentionally does NOT block navigation.
// / 引导状态每次页面加载只取一次并缓存在此；后端不可达时的「需要引导」判定为
//   false，刻意不阻塞导航。
let setupChecked = false;
let setupCompleted = true;

async function ensureSetupChecked() {
    if (setupChecked) return setupCompleted;
    try {
        const st = await getSetupStatus();
        setupCompleted = st?.completed !== false;
    } catch {
        setupCompleted = true; // 后端异常时不拦截
    }
    setupChecked = true;
    return setupCompleted;
}

/** Called by the wizard after POST /api/setup/complete. */
export function markSetupCompleted() {
    setupChecked = true;
    setupCompleted = true;
}

/** Called by the config page's "re-run wizard" button after POST /setup/reset. */
export function invalidateSetupCache() {
    setupChecked = false;
    setupCompleted = false;
}

router.beforeEach(async (to, from, next) => {
    if (to.path === "/login") return next();
    const token = localStorage.getItem("auth_token");
    const bypass = localStorage.getItem("auth_bypass");
    if (!token && bypass !== "true") return next("/login");
    if (to.path === "/setup") return next();
    if (await ensureSetupChecked()) return next();
    next("/setup");
});

export default router;
