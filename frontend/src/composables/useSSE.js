import { ref, onUnmounted } from "vue";

export function useSSE(eventHandlers = {}) {
    const connected = ref(false);
    let eventSource = null;
    let heartbeatTimer = null;
    let reconnectTimer = null;
    let reconnectAttempts = 0;
    let urlRef = "";
    const HEARTBEAT_TIMEOUT = 20000;
    const RECONNECT_BASE_DELAY = 1000;
    const RECONNECT_MAX_DELAY = 30000;
    const MAX_RECONNECT_ATTEMPTS = 20;

    function _clearTimers() {
        clearTimeout(heartbeatTimer);
        clearTimeout(reconnectTimer);
    }

    function connect(url) {
        const token = localStorage.getItem("auth_token");
        const sep = url.includes("?") ? "&" : "?";
        const fullUrl = token ? `${url}${sep}token=${token}` : url;
        urlRef = fullUrl;
        disconnect();
        eventSource = new EventSource(fullUrl);
        eventSource.onopen = () => {
            connected.value = true;
            reconnectAttempts = 0;
            _resetHeartbeat();
        };

        const wrappedHandlers = { ...eventHandlers };

        for (const [event, handler] of Object.entries(wrappedHandlers)) {
            eventSource.addEventListener(event, (e) => {
                try {
                    handler(JSON.parse(e.data));
                } catch {
                    /* ignore parse errors */
                }
            });
        }

        eventSource.addEventListener("ping", () => {
            _resetHeartbeat();
        });

        eventSource.onerror = () => {
            connected.value = false;
            _clearTimers();
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            _scheduleReconnect();
        };

        _resetHeartbeat();
    }

    function _scheduleReconnect() {
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;
        reconnectAttempts++;
        const delay = Math.min(RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts - 1), RECONNECT_MAX_DELAY);
        reconnectTimer = setTimeout(
            () => {
                connect(urlRef);
            },
            delay + Math.random() * 1000
        );
    }

    function _resetHeartbeat() {
        clearTimeout(heartbeatTimer);
        heartbeatTimer = setTimeout(() => {
            connected.value = false;
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            _scheduleReconnect();
        }, HEARTBEAT_TIMEOUT);
    }

    function disconnect() {
        _clearTimers();
        reconnectAttempts = MAX_RECONNECT_ATTEMPTS;
        if (eventSource) {
            eventSource.close();
            eventSource = null;
            connected.value = false;
        }
    }

    function ensureConnected(url) {
        if (!eventSource || eventSource.readyState !== EventSource.OPEN) {
            reconnectAttempts = 0;
            connect(url);
        }
    }

    onUnmounted(disconnect);
    return { connected, connect, disconnect, ensureConnected };
}
