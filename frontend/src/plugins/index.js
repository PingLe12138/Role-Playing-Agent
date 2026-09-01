import { markRaw, ref } from "vue";
import { Dashboard, Fire, Plug, PlugOne, Setting } from "@icon-park/vue-next";
import { getPlugins } from "../api/plugins.js";

// Plugin pages are picked up at build time via a Vite glob. The pattern is
// relative to THIS MODULE (frontend/src/plugins/), so the project-root plugins/
// dir is three levels up; keys come back as POSIX paths like
// `../../../plugins/<plugin_id>/ui/<component>`.
// / 插件页面通过 Vite glob 在构建期收集；模式相对本模块目录（frontend/src/plugins/），
//   项目根 plugins/ 需上三级；返回 key 形如 ../../../plugins/<plugin_id>/ui/<component>。
const pageModules = import.meta.glob("../../../plugins/*/ui/*.vue", { eager: true });

function findPageModule(plugin, component) {
    // Glob entries are module namespace objects ({ default: Component }), but
    // vue-router needs the raw component itself.
    // / glob 条目是模块命名空间对象（{ default: Component }），路由需要原始组件。
    const unwrap = (mod) => (mod && mod.default !== undefined ? mod.default : mod);
    const want = `plugins/${plugin}/${component}`.replace(/\\/g, "/");
    for (const key of Object.keys(pageModules)) {
        if (key.replace(/\\/g, "/").endsWith(want)) return unwrap(pageModules[key]);
    }
    // Fall back to the conventional default component path.
    // / 兜底默认组件路径。
    const fallback = `plugins/${plugin}/ui/Index.vue`;
    for (const key of Object.keys(pageModules)) {
        if (key.replace(/\\/g, "/").endsWith(fallback)) return unwrap(pageModules[key]);
    }
    return undefined;
}

// Resolved pages (available for the top bar menu) and load errors.
// / 已解析页面（供顶栏菜单使用）与加载错误。
export const pluginPages = ref([]);
export const pluginLoadErrors = ref([]);

// Plugin manifests may declare any icon-park name ("Plugin", "PluginTwo", ...);
// unknown names fall back to the Plug icon.
// / 插件清单可声明任意 icon-park 图标名；未知名称回退到 Plug 图标。
const ICON_ALIASES = {
    Plug,
    PlugOne,
    Plugin: Plug,
    PluginTwo: PlugOne,
    Setting,
    Dashboard,
    Fire
};

export function resolvePageIcon(name) {
    const Icon = ICON_ALIASES[name];
    return markRaw(Icon || Plug);
}

let loaded = false;

/** Fetch `/api/plugins` once and resolve component modules for every page.
 *  Never throws: plugin problems must not block navigation.
 *  / 拉取 /api/plugins 一次并为每个页面解析组件模块。绝不抛异常：插件问题
 *    不能阻塞导航。
 */
export async function ensurePluginPages() {
    if (loaded) return;
    loaded = true;
    let data;
    try {
        data = await getPlugins();
    } catch {
        return; // 后端不可达/未登录：保持空页面列表
    }

    pluginLoadErrors.value = (data?.errors || []).map((e) => `[${e.stage}] ${e.message}`);

    const pages = [];
    for (const page of data?.pages || []) {
        const plugin = page.plugin || "";
        const component = findPageModule(plugin, page.component || "ui/Index.vue");
        if (!component) {
            pluginLoadErrors.value.push(
                `[page] 页面 ${page.path} 缺少组件文件（plugins/${plugin}/${page.component || "ui/Index.vue"}）`
            );
            continue;
        }
        pages.push({
            path: page.path,
            title: page.title || plugin,
            icon: page.icon || "Plug",
            plugin,
            component
        });
    }
    pluginPages.value = pages;
}

/** Register every plugin page as a child of the app layout.
 *  / 将每个插件页面注册为应用布局的子路由。
 */
export function installPluginRoutes(router) {
    let existing = new Set(router.getRoutes().map((r) => r.name));
    for (const page of pluginPages.value) {
        const name = `plugin-${page.plugin}-${page.path}`;
        if (existing.has(name)) continue;
        router.addRoute("AppLayout", {
            path: page.path,
            name,
            component: page.component,
            meta: { title: page.title }
        });
        existing.add(name);
    }
}
