import request from "./request";

export function listSessionHistory(sessionId) {
    return request.get(`/api/sessions/${sessionId}/history`);
}
export function clearSessionHistory(sessionId) {
    return request.delete(`/api/sessions/${sessionId}/history`);
}
export function deleteSessionHistory(id) {
    return request.delete(`/api/session-history/${id}`);
}
