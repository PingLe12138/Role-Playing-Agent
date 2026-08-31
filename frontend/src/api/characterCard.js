import request from "./request";

export function listCharacterCards() {
    return request.get("/api/character-cards");
}
export function createCharacterCard(data) {
    return request.post("/api/character-cards", data);
}
export function updateCharacterCard(id, data) {
    return request.put(`/api/character-cards/${id}`, data);
}
export function deleteCharacterCard(id) {
    return request.delete(`/api/character-cards/${id}`);
}
export function listCharacterEmotions(characterID) {
    return request.get(`/api/characters/${characterID}/emotions`);
}
export function updateCharacterEmotion(id, data) {
    return request.put(`/api/characters/${id}/emotions`, data);
}
export function exportCharacterCard(id) {
    return request.get(`/api/character-cards/${id}/export`, { responseType: "blob" });
}
export function importCharacterCards(data) {
    return request.post("/api/character-cards/import", data);
}
