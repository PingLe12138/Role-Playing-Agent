<template>
    <el-drawer v-if="!inline" v-model="isVisible" size="75%" @close="emit('close')">
        <template #header>
            <div class="drawer-header">
                <MindMapping theme="outline" size="16" class="drawer-header-icon" />图结构
            </div>
        </template>
        <GraphCanvas
            :graph-data="graphData"
            :current-graph-id="currentGraphId"
            :active-nodes="props.activeNodes"
            :layout="curLayout"
            :loaded="loaded"
            @switch="switchGraph"
            @node-click="handleNodeClick"
            @refresh="loadTopology"
        />
    </el-drawer>

    <div v-else class="graph-view-inline">
        <GraphCanvas
            :graph-data="graphData"
            :current-graph-id="currentGraphId"
            :active-nodes="props.activeNodes"
            :layout="curLayout"
            :loaded="loaded"
            @switch="switchGraph"
            @node-click="handleNodeClick"
            @refresh="loadTopology"
        />
    </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from "vue";
import ELK from "elkjs/lib/elk.bundled.js";
import { MindMapping } from "@icon-park/vue-next";
import request from "../api/request.js";
import GraphCanvas from "./GraphCanvas.vue";

const elk = new ELK();

const props = defineProps({
    visible: Boolean,
    activeNodes: { type: Object, default: () => ({}) },
    inline: { type: Boolean, default: false }
});

const emit = defineEmits(["close"]);

const isVisible = ref(false);
const loaded = ref(false);
const graphData = ref([]);
const currentGraphId = ref("supervisor");

onMounted(() => {
    if (props.inline) {
        loadTopology();
    }
});

watch(
    () => props.visible,
    async (val) => {
        isVisible.value = val;
        if (val) {
            await loadTopology();
        }
    }
);

watch(isVisible, (val) => {
    if (!val) emit("close");
});

const curGraph = computed(() => {
    return graphData.value.find((g) => g.id === currentGraphId.value);
});

const curLayout = ref({ nodes: [], edges: [] });
const layoutLoading = ref(false);

watch(
    curGraph,
    async (graph) => {
        if (!graph) {
            curLayout.value = { nodes: [], edges: [] };
            return;
        }
        layoutLoading.value = true;
        try {
            curLayout.value = await computeLayoutElk(graph);
            const runningNodes = new Set(
                Object.keys(props.activeNodes).filter((k) => props.activeNodes[k] === "running")
            );
            for (const edge of curLayout.value.edges) {
                edge.animated = runningNodes.has(edge.from) || runningNodes.has(edge.to);
            }
        } catch (e) {
            console.error("Elk layout error:", e);
            curLayout.value = { nodes: [], edges: [] };
        }
        layoutLoading.value = false;
    },
    { immediate: true }
);

watch(
    () => props.activeNodes,
    (nodes) => {
        if (!curLayout.value.edges.length) return;
        const runningNodes = new Set(Object.keys(nodes).filter((k) => nodes[k] === "running"));
        for (const edge of curLayout.value.edges) {
            edge.animated = runningNodes.has(edge.from) || runningNodes.has(edge.to);
        }
    },
    { deep: true }
);

async function loadTopology() {
    try {
        const res = await request.get("/api/graph/topology");
        graphData.value = res.graphs || [];
        if (graphData.value.length === 0 && res.data?.graphs) {
            graphData.value = res.data.graphs;
        }
        loaded.value = true;
        await nextTick();
    } catch (e) {
        console.error("Failed to load graph topology:", e);
    }
}

function switchGraph(id) {
    currentGraphId.value = id;
}

function handleNodeClick(node) {
    if (node.type === "subgraph" && node.id === "director_subgraph") {
        switchGraph("director");
    }
}

let _measureCtx = null;
function measureTextWidth(str, fontSize = 11) {
    try {
        if (!_measureCtx) _measureCtx = document.createElement("canvas").getContext("2d");
        _measureCtx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
        return Math.ceil(_measureCtx.measureText(str).width);
    } catch {
        return [...str].reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? fontSize : fontSize * 0.55), 0);
    }
}

function orthogonalPath(points) {
    if (!points || points.length < 2) return "";

    let path = `M${Math.round(points[0].x)},${Math.round(points[0].y)}`;

    for (let i = 1; i < points.length; i++) {
        const dx = Math.abs(points[i].x - points[i - 1].x);
        const dy = Math.abs(points[i].y - points[i - 1].y);

        if (dx > dy) {
            path += `H${Math.round(points[i].x)}`;
            if (dy > 0.5) path += `V${Math.round(points[i].y)}`;
        } else {
            path += `V${Math.round(points[i].y)}`;
            if (dx > 0.5) path += `H${Math.round(points[i].x)}`;
        }
    }

    return path;
}

async function computeLayoutElk(graphDef) {
    const NODE_W = 180;
    const NODE_H = 44;

    if (!graphDef || !graphDef.nodes.length) return { nodes: [], edges: [] };

    const nodeIds = new Set(graphDef.nodes.map((n) => n.id));

    const elkGraph = {
        id: "root",
        layoutOptions: {
            "elk.algorithm": "layered",
            "elk.direction": "DOWN",
            "elk.layered.spacing.nodeNodeBetweenLayers": "90",
            "elk.spacing.nodeNode": "60",
            "elk.layered.thoroughness": "15",
            "elk.layered.nodePlacement.strategy": "SIMPLE",
            "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP"
        },
        children: graphDef.nodes.map((n) => ({
            id: n.id,
            width: NODE_W,
            height: NODE_H
        })),
        edges: graphDef.edges
            .filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to))
            .map((e) => ({
                id: `${e.from}\x00${e.to}`,
                sources: [e.from],
                targets: [e.to]
            }))
    };

    const layout = await elk.layout(elkGraph);

    const childMap = {};
    for (const c of layout.children || []) {
        childMap[c.id] = c;
    }

    const nodes = graphDef.nodes.map((n) => {
        const c = childMap[n.id];
        return { ...n, x: c.x, y: c.y };
    });

    const edges = graphDef.edges.map((e) => {
        const edgeObj = layout.edges?.find((ed) => ed.id === `${e.from}\x00${e.to}`);
        const section = edgeObj?.sections?.[0];
        const points = [];
        if (section) {
            points.push({ x: section.startPoint.x, y: section.startPoint.y });
            if (section.bendPoints) {
                for (const bp of section.bendPoints) {
                    points.push({ x: bp.x, y: bp.y });
                }
            }
            points.push({ x: section.endPoint.x, y: section.endPoint.y });
        }
        let path = "";
        let labelX = 0;
        let labelY = 0;
        if (points.length >= 2) {
            path = orthogonalPath(points);
            const mid = Math.floor((points.length - 1) / 2);
            labelX = (points[mid].x + points[mid + 1].x) / 2;
            labelY = (points[mid].y + points[mid + 1].y) / 2 - 8;
        }
        return {
            ...e,
            path,
            labelX,
            labelY,
            labelW: e.label ? measureTextWidth(e.label) + 20 : 0,
            pointList: points,
            animated: false
        };
    });

    return { nodes, edges };
}

defineExpose({ loadTopology });
</script>

<style scoped>
.drawer-header {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary, #1e2a3a);
}
.drawer-header-icon {
    color: #5d9eff;
}
.graph-view-inline {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 400px;
    overflow: hidden;
}
</style>
