import axios from "axios";

const request = axios.create({
    baseURL: "/",
    timeout: 60000
});

request.interceptors.request.use((config) => {
    const token = localStorage.getItem("auth_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

request.interceptors.response.use(
    (response) => {
        const res = response.data;
        if (res && res.data === undefined) {
            return res;
        }
        return res && res.data !== undefined ? res.data : res;
    },
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem("auth_token");
            localStorage.removeItem("auth_enabled");
            if (window.location.pathname !== "/login") {
                window.location.href = "/login";
            }
            return Promise.reject(new Error("未登录或登录已过期"));
        }
        const msg = error.response?.data?.msg || error.message || "请求失败";
        return Promise.reject(new Error(msg));
    }
);

export default request;
