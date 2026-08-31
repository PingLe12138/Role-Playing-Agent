<template>
    <div class="graph-view">
        <div class="graph-tabs">
            <span
                v-for="g in graphData"
                :key="g.id"
                class="graph-tab"
                :class="{ active: currentGraphId === g.id }"
                @click="$emit('switch', g.id)"
            >
                <component :is="tabIcon(g.id)" theme="outline" size="14" class="graph-tab-icon" />
                {{ g.title }}
            </span>
            <span class="graph-tab-flex"></span>
            <span class="graph-refresh" title="重新加载拓扑" @click="$emit('refresh')">
                <Refresh theme="outline" size="14" />
            </span>
        </div>

        <div v-if="loaded" class="graph-canvas-wrap">
            <div class="graph-svg-wrapper" ref="svgWrapper">
                <div class="graph-stage" :style="stageStyle">
                    <svg :width="svgBounds.w" :height="svgBounds.h" :viewBox="viewBox" :style="svgStyle">
                        <defs>
                            <pattern :id="gridId" width="20" height="20" patternUnits="userSpaceOnUse">
                                <circle cx="1" cy="1" r="0.8" fill="#dfe3ea" />
                            </pattern>

                            <marker
                                :id="arrowId"
                                markerWidth="8"
                                markerHeight="8"
                                refX="7"
                                refY="4"
                                orient="auto"
                            >
                                <path d="M0,0 L8,4 L0,8 Z" fill="#9aa5b1" />
                            </marker>

                            <marker
                                :id="arrowRunId"
                                markerWidth="8"
                                markerHeight="8"
                                refX="7"
                                refY="4"
                                orient="auto"
                            >
                                <path d="M0,0 L8,4 L0,8 Z" fill="#67c23a" />
                            </marker>

                            <filter :id="shadowId" x="-10%" y="-10%" width="130%" height="130%">
                                <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="rgba(0,0,0,0.07)" />
                            </filter>

                            <filter :id="shadowRunId" x="-30%" y="-30%" width="160%" height="160%">
                                <feDropShadow dx="0" dy="2" stdDeviation="8" flood-color="rgba(103,194,58,0.35)" />
                            </filter>

                            <filter :id="shadowDoneId" x="-10%" y="-10%" width="130%" height="130%">
                                <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="rgba(16,24,40,0.05)" />
                            </filter>
                        </defs>

                        <rect width="100%" height="100%" :fill="`url(#${gridId})`" />

                        <g v-for="(edge, i) in layout.edges" :key="'e' + i" class="edge-group">
                            <path
                                :d="edge.path"
                                fill="none"
                                :class="['edge-path', edge.animated ? 'edge-path-running' : '']"
                                :marker-end="edge.animated ? `url(#${arrowRunId})` : `url(#${arrowId})`"
                            />
                            <rect
                                v-if="edge.label"
                                :x="edge.labelX - edge.labelW / 2"
                                :y="edge.labelY - 10"
                                :width="edge.labelW"
                                height="20"
                                rx="10"
                                class="edge-label-bg"
                            />
                            <text v-if="edge.label" :x="edge.labelX" :y="edge.labelY" class="edge-label">
                                {{ edge.label }}
                            </text>
                        </g>

                        <g
                            v-for="node in layout.nodes"
                            :key="node.id"
                            :class="['graph-node', nodeStatus(node.id)]"
                            @click="$emit('node-click', node)"
                            :transform="`translate(${node.x}, ${node.y})`"
                        >
                            <title>{{ node.type === "subgraph" ? "点击查看子图" : node.label }}</title>
                            <rect
                                width="180"
                                height="44"
                                rx="10"
                                ry="10"
                                class="node-bg"
                                :filter="nodeFilter(nodeStatus(node.id))"
                            />
                            <text x="90" y="22" text-anchor="middle" dominant-baseline="central" class="node-label">
                                {{ node.label }}
                            </text>
                            <text
                                v-if="node.type === 'subgraph'"
                                x="164"
                                y="22"
                                text-anchor="middle"
                                dominant-baseline="central"
                                class="node-expand-icon"
                            >
                                ▶
                            </text>
                        </g>
                    </svg>
                </div>
            </div>

            <div class="graph-zoom">
                <button class="zoom-btn" title="缩小" :disabled="scale <= 0.3" @click="zoomBy(-0.15)">
                    <ZoomOut theme="outline" size="14" />
                </button>
                <span class="zoom-pct">{{ Math.round(scale * 100) }}%</span>
                <button class="zoom-btn" title="放大" :disabled="scale >= 1.5" @click="zoomBy(0.15)">
                    <ZoomIn theme="outline" size="14" />
                </button>
                <span class="zoom-sep"></span>
                <button class="zoom-btn" title="适应容器" @click="fitToView()">
                    <FullScreen theme="outline" size="14" />
                </button>
                <button class="zoom-btn zoom-btn-text" title="100%" :class="{ active: scale === 1 }" @click="resetZoom">
                    1:1
                </button>
            </div>
        </div>

        <div v-else class="graph-loading">
            <div class="loading-spinner"></div>
            <p>加载图结构中...</p>
        </div>

        <div class="graph-legend">
            <span class="legend-item"><span class="legend-dot dot-idle"></span> 待执行</span>
            <span class="legend-item"><span class="legend-dot dot-running"></span> 执行中</span>
            <span class="legend-item"><span class="legend-dot dot-completed"></span> 已完成</span>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, useId } from "vue";
import { MindMapping, Branch, Refresh, ZoomIn, ZoomOut, FullScreen } from "@icon-park/vue-next";

const props = defineProps({
    graphData: { type: Array, default: () => [] },
    currentGraphId: { type: String, default: "supervisor" },
    activeNodes: { type: Object, default: () => ({}) },
    layout: { type: Object, default: () => ({ nodes: [], edges: [] }) },
    loaded: Boolean
});
defineEmits(["switch", "node-click", "refresh"]);

const uid = useId();
const gridId = `graph-grid-${uid}`;
const arrowId = `graph-arrow-${uid}`;
const arrowRunId = `graph-arrow-running-${uid}`;
const shadowId = `graph-shadow-${uid}`;
const shadowRunId = `graph-shadow-running-${uid}`;
const shadowDoneId = `graph-shadow-completed-${uid}`;

const svgWrapper = ref(null);
const scale = ref(1);
const autoFit = ref(true);
let resizeObserver = null;

const svgBounds = computed(() => {
    const nodes = props.layout.nodes;
    if (!nodes.length) return { w: 600, h: 400, ox: 0, oy: 0 };
    let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity;
    for (const n of nodes) {
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x + 180);
        maxY = Math.max(maxY, n.y + 44);
    }
    for (const e of props.layout.edges) {
        const pts = e.pointList || [];
        for (const p of pts) {
            minX = Math.min(minX, p.x);
            minY = Math.min(minY, p.y);
            maxX = Math.max(maxX, p.x);
            maxY = Math.max(maxY, p.y);
        }
    }
    const pad = 50;
    minX = minX - pad;
    minY = minY - pad;
    maxX = maxX + pad;
    maxY = maxY + pad;
    return { w: Math.ceil(maxX - minX), h: Math.ceil(maxY - minY), ox: minX, oy: minY };
});

const viewBox = computed(() => `${svgBounds.value.ox} ${svgBounds.value.oy} ${svgBounds.value.w} ${svgBounds.value.h}`);

const pad = computed(() => {
    const w = svgWrapper.value?.clientWidth || 0;
    const h = svgWrapper.value?.clientHeight || 0;
    const sw = svgBounds.value.w * scale.value;
    const sh = svgBounds.value.h * scale.value;
    return { x: Math.max(0, (w - sw) / 2), y: Math.max(0, (h - sh) / 2) };
});

const stageStyle = computed(() => ({
    width: `${svgBounds.value.w * scale.value + pad.value.x * 2}px`,
    height: `${svgBounds.value.h * scale.value + pad.value.y * 2}px`,
    padding: `${pad.value.y}px ${pad.value.x}px`
}));

const svgStyle = computed(() => ({
    transform: `scale(${scale.value})`,
    transformOrigin: "0 0"
}));

function tabIcon(id) {
    if (id === "director") return Branch;
    return MindMapping;
}

function nodeStatus(nodeId) {
    const s = props.activeNodes[nodeId];
    if (s === "running") return "running";
    if (s === "completed") return "completed";
    return "idle";
}

function nodeFilter(status) {
    if (status === "running") return `url(#${shadowRunId})`;
    if (status === "completed") return `url(#${shadowDoneId})`;
    return `url(#${shadowId})`;
}

function clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
}

function zoomBy(delta) {
    autoFit.value = false;
    scale.value = Math.round(clamp(scale.value + delta, 0.25, 1.5) * 100) / 100;
}

function resetZoom() {
    autoFit.value = false;
    scale.value = 1;
}

function fitToView() {
    autoFit.value = true;
    const w = svgWrapper.value?.clientWidth || 0;
    const h = svgWrapper.value?.clientHeight || 0;
    const bw = svgBounds.value.w;
    const bh = svgBounds.value.h;
    if (!w || !h || !bw || !bh) return;
    scale.value = clamp(Math.min((w - 24) / bw, (h - 24) / bh, 1), 0.25, 1);
}

watch(
    () => props.layout,
    () => {
        nextTick(() => {
            if (autoFit.value) fitToView();
        });
    }
);

onMounted(() => {
    if (svgWrapper.value && typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => {
            if (autoFit.value) fitToView();
        });
        resizeObserver.observe(svgWrapper.value);
    }
});

onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    resizeObserver = null;
});
</script>

<style scoped>
.graph-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
}

/* ── Tabs ── */
.graph-tabs {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--border-light, #e8eaed);
}
.graph-tab {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 8px 14px;
    font-size: 13px;
    color: #606266;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition:
        color 0.2s,
        border-color 0.2s;
    user-select: none;
    white-space: nowrap;
}
.graph-tab-icon {
    color: #9aa5b1;
}
.graph-tab:hover {
    color: #3a6fd8;
}
.graph-tab.active {
    color: #2b6dd9;
    font-weight: 600;
}
.graph-tab.active .graph-tab-icon {
    color: #5d9eff;
}
.graph-tab.active::after {
    content: "";
    position: absolute;
    left: 14px;
    right: 14px;
    bottom: -1px;
    height: 2px;
    border-radius: 2px;
    background: var(--brand-500, #5d9eff);
}
.graph-tab-flex {
    flex: 1;
}
.graph-refresh {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 5px;
    border-radius: 6px;
    color: #9aa5b1;
    cursor: pointer;
    transition: all 0.15s;
}
.graph-refresh:hover {
    color: #5d9eff;
    background: #f0f4ff;
}

/* ── Canvas ── */
.graph-canvas-wrap {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
}
.graph-svg-wrapper {
    flex: 1;
    min-width: 0;
    overflow: auto;
    background: var(--app-bg, #f3f5f9);
    border-radius: 10px;
    border: 1px solid #e8eaed;
}
.graph-stage {
    box-sizing: border-box;
}
.graph-stage svg {
    display: block;
}

.graph-zoom {
    position: absolute;
    top: 10px;
    right: 10px;
    z-index: 5;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 3px;
    background: #fff;
    border: 1px solid #e8eaed;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(16, 24, 40, 0.1);
}
.zoom-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    padding: 0;
    border: none;
    background: transparent;
    border-radius: 5px;
    color: #606266;
    cursor: pointer;
    transition: all 0.15s;
}
.zoom-btn:hover:not(:disabled) {
    background: #f0f4ff;
    color: #5d9eff;
}
.zoom-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
}
.zoom-btn-text {
    width: auto;
    padding: 0 6px;
    font-size: 11px;
    font-family: inherit;
}
.zoom-btn-text.active {
    color: #5d9eff;
    font-weight: 600;
}
.zoom-pct {
    min-width: 38px;
    text-align: center;
    font-size: 11px;
    color: #909399;
    font-variant-numeric: tabular-nums;
}
.zoom-sep {
    width: 1px;
    height: 14px;
    background: #e8eaed;
    margin: 0 3px;
}

/* ── Edges ── */
.edge-group {
    transition: opacity 0.25s;
}
.edge-path {
    stroke: #9aa5b1;
    stroke-width: 1.5;
    transition: stroke 0.3s;
}
.edge-path-running {
    stroke: #67c23a;
    stroke-width: 2;
    stroke-dasharray: 6 4;
    animation: edge-dash 0.8s linear infinite;
}
.edge-label-bg {
    fill: #fff;
    stroke: #e0e3e8;
    stroke-width: 0.5;
}
.edge-label {
    fill: #606266;
    font-size: 11px;
    text-anchor: middle;
    dominant-baseline: middle;
}

/* ── Nodes ── */
.graph-node {
    cursor: default;
    transition: opacity 0.25s;
}
.node-bg {
    fill: #fff;
    stroke: var(--brand-200, #c8dcff);
    transition:
        fill 0.3s,
        stroke 0.3s;
}
.node-label {
    fill: #1e2a3a;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.3px;
    transition: fill 0.3s;
}
.graph-node:not(.running):not(.completed):not(.subgraph):hover .node-bg {
    stroke: var(--brand-500, #5d9eff);
    fill: var(--brand-50, #f0f6ff);
}

/* ── Running ── */
.graph-node.running .node-bg {
    fill: #e6f7e6;
    stroke: #67c23a;
    animation: node-pulse 1.6s ease-in-out infinite;
}
.graph-node.running .node-label {
    fill: #2b7a2b;
    font-weight: 600;
}

/* ── Completed ── */
.graph-node.completed .node-bg {
    fill: #f4f6f8;
    stroke: #c8cdd4;
}
.graph-node.completed .node-label {
    fill: #606266;
}

/* ── Subgraph ── */
.graph-node.subgraph {
    cursor: pointer;
}
.graph-node.subgraph .node-bg {
    fill: var(--brand-50, #f0f6ff);
    stroke: var(--brand-300, #a3c6ff);
}
.graph-node.subgraph .node-label {
    fill: #2b6dd9;
}
.graph-node.subgraph:hover .node-bg {
    fill: var(--brand-100, #e2edff);
    stroke: var(--brand-500, #5d9eff);
}
.graph-node.subgraph.running .node-bg {
    fill: #e6f7e6;
    stroke: #67c23a;
    animation: node-pulse 1.6s ease-in-out infinite;
}

.node-expand-icon {
    font-size: 10px;
    fill: #6b93d6;
    opacity: 0.8;
    pointer-events: none;
}

/* ── Legend ── */
.graph-legend {
    display: flex;
    gap: 24px;
    margin-top: 12px;
    padding: 10px 16px;
    background: var(--app-bg, #f3f5f9);
    border-radius: 8px;
    font-size: 12px;
    color: #606266;
    align-items: center;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 7px;
}
.legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 1.5px solid #d8dce3;
}
.dot-idle {
    background: #fff;
}
.dot-running {
    background: #67c23a;
    border-color: #67c23a;
    box-shadow: 0 0 6px rgba(103, 194, 58, 0.4);
}
.dot-completed {
    background: #c8cdd4;
    border-color: #c8cdd4;
}

/* ── Animations ── */
@keyframes edge-dash {
    to {
        stroke-dashoffset: -10;
    }
}
@keyframes node-pulse {
    0%,
    100% {
        stroke-width: 1.5;
    }
    50% {
        stroke-width: 2.8;
    }
}

/* ── Loading ── */
.graph-loading {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #909399;
    gap: 12px;
}
.loading-spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #e8eaed;
    border-top-color: #5d9eff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}
</style>
