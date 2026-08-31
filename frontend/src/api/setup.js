import request from "./request";

export function getSetupStatus() {
    return request.get("/api/setup/status");
}
export function completeSetup(data) {
    return request.post("/api/setup/complete", data || {});
}
export function resetSetup() {
    return request.post("/api/setup/reset");
}
