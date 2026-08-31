import request from "./request";

export function listWorldviewCollections() {
    return request.get("/api/worldview-collections");
}
export function createWorldviewCollection(data) {
    return request.post("/api/worldview-collections", data);
}
export function updateWorldviewCollection(id, data) {
    return request.put(`/api/worldview-collections/${id}`, data);
}
export function deleteWorldviewCollection(id) {
    return request.delete(`/api/worldview-collections/${id}`);
}
export function exportWorldviewCollection(id) {
    return request.get(`/api/worldview-collections/${id}/export`, { responseType: "blob" });
}
export function importWorldviewCollection(data) {
    return request.post("/api/worldview-collections/import", data);
}
