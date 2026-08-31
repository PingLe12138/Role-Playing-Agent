import request from "./request";

export function listUserCharacters() {
    return request.get("/api/user-characters");
}
export function createUserCharacter(data) {
    return request.post("/api/user-characters", data);
}
export function updateUserCharacter(id, data) {
    return request.put(`/api/user-characters/${id}`, data);
}
export function deleteUserCharacter(id) {
    return request.delete(`/api/user-characters/${id}`);
}
export function exportUserCharacter(id) {
    return request.get(`/api/user-characters/${id}/export`, { responseType: "blob" });
}
export function importUserCharacters(data) {
    return request.post("/api/user-characters/import", data);
}
