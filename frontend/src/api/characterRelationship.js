import request from "./request";

export function batchCreateRelationships(data) {
    return request.post("/api/character-relationships", data);
}

export function listCharacterRelationships(characterID) {
    return request.get(`/api/character-relationships/${characterID}`);
}

export function deleteCharacterSessionRelationships(characterID, sessionId) {
    return request.delete(`/api/character-relationships/${characterID}`, { params: { session_id: sessionId } });
}
