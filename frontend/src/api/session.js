import request from "./request";

export function listSessions(params = {}) {
    return request.get("/api/sessions", { params });
}
export function createSession(data) {
    return request.post("/api/sessions", data);
}
export function getSession(id) {
    return request.get(`/api/sessions/${id}`);
}
export function updateSession(id, data) {
    return request.put(`/api/sessions/${id}`, data);
}
export function deleteSession(id) {
    return request.delete(`/api/sessions/${id}`);
}
export function exportSession(id) {
    return request.get(`/api/sessions/${id}/export`, { responseType: "blob" });
}
export function importSession(data) {
    return request.post("/api/sessions/import", data);
}
