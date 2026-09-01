import request from "./request";

export function getPlugins() {
    return request.get("/api/plugins");
}
