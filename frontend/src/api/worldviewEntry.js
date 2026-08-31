import request from "./request";

export function createWorldviewEntry(data) {
    return request.post("/api/worldview-entries", data);
}
export function updateWorldviewEntry(id, data) {
    return request.put(`/api/worldview-entries/${id}`, data);
}
export function deleteWorldviewEntry(id) {
    return request.delete(`/api/worldview-entries/${id}`);
}
export function listWorldviewEntriesByCollection(parentId) {
    return request.get(`/api/worldview-entries/by-collection/${parentId}`);
}
