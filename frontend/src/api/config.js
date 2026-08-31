import request from "./request";

export function getLlmConfig() {
    return request.get("/api/config/llm");
}
export function updateLlmConfig(data) {
    return request.put("/api/config/llm", data);
}
export function testLlmConfig(data) {
    return request.post("/api/config/llm/test", data);
}
export function clearAll() {
    return request.post("/api/clear-all");
}
export function getNodeLlmConfig() {
    return request.get("/api/config/node-llm");
}
export function updateNodeLlmConfig(data) {
    return request.put("/api/config/node-llm", data);
}
export function getNodeParams() {
    return request.get("/api/config/node-params");
}
export function updateNodeParams(data) {
    return request.put("/api/config/node-params", data);
}
export function getNodePrompts() {
    return request.get("/api/config/node-prompts");
}
export function getNodePromptDefaults() {
    return request.get("/api/config/node-prompts/defaults");
}
export function updateNodeConfig(data) {
    return request.put("/api/config/node-config", data);
}
export function updateNodePrompt(nodeName, data) {
    return request.put(`/api/config/node-prompt/${nodeName}`, data);
}
export function getSystemRules() {
    return request.get("/api/config/system-rules");
}
export function getNodeContexts() {
    return request.get("/api/config/node-contexts");
}
export function updateNodeContexts(data) {
    return request.put("/api/config/node-contexts", data);
}
export function updateSystemRules(data) {
    return request.put("/api/config/system-rules", data);
}
export function getImageGenerationConfig() {
    return request.get("/api/config/image-generation");
}
export function updateImageGenerationConfig(data) {
    return request.put("/api/config/image-generation", data);
}
export function testImageGenerationConfig(data) {
    return request.post("/api/config/image-generation/test", data || {});
}
export function getFeatures() {
    return request.get("/api/config/features");
}
export function updateFeatures(data) {
    return request.put("/api/config/features", data);
}
export function exportNodeConfig() {
    return request.get("/api/config/node-config/export", { responseType: "blob" });
}
export function importNodeConfig(data) {
    return request.post("/api/config/node-config/import", data);
}
