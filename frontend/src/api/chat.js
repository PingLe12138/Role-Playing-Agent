import request from "./request";

export function sendChatMessage(data) {
    return request.post("/api/chat", data);
}
export function submitPlayerChoice(data) {
    return request.post("/api/chat/choice", data);
}
export function cancelPlayerChoice(data) {
    return request.post("/api/chat/choice/cancel", data);
}
