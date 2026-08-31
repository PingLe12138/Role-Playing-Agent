import request from "./request";

export function getLogFiles() {
    return request.get("/api/logs");
}
export function getLogContent(filename) {
    return request.get(`/api/logs/${filename}`);
}
export function streamLogUrl(filename) {
    return `/api/logs/stream?filename=${filename}`;
}
