#!/usr/bin/env bash
# Start RPA backend + frontend. Linux/macOS counterpart of start.ps1.
#
# Keep this file pure ASCII and bash 3.2 compatible (macOS ships 3.2, so no
# associative arrays / mapfile / ${var,,}). Mirrors start.ps1's robustness:
# port pre-flight with explicit reminder, /docs ownership check, IPv4/IPv6
# dual-stack probe for the vite frontend, and graceful shutdown on exit.

set -euo pipefail

BACKEND_PORT=8000
FRONTEND_PORT=5173
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
BACKEND_PID=""
FRONTEND_PID=""

mkdir -p "$LOG_DIR"

# Print the PID listening on $1, or empty when the port is free.
port_pid() {
    local port="$1" pid=""
    pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -n 1) || true
    if [ -z "$pid" ]; then
        # lsof may be absent (minimal containers); ss is the fallback.
        pid=$(ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $NF}' | head -n 1 | sed 's/.*pid=//;s/,.*//') || true
    fi
    echo "$pid"
}

# Test whether $1 is a (transitive) child of $2, bounded depth 8.
is_descendant() {
    local cur="$1" ancestor="$2" ppid="" i
    for ((i = 0; i < 8 && cur; i++)); do
        [ "$cur" = "$ancestor" ] && return 0
        ppid=$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ') || true
        [ -z "$ppid" ] && return 1
        cur="$ppid"
    done
    return 1
}

# Stop backend/frontend started by this script (TERM, escalate to KILL).
stop_started() {
    local pid
    for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
        [ -z "$pid" ] && continue
        kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 2
    for pid in "$BACKEND_PID" "$FRONTEND_PID"; do
        [ -z "$pid" ] && continue
        kill -KILL "$pid" 2>/dev/null || true
    done
    BACKEND_PID=""
    FRONTEND_PID=""
}

# Wait until port $1 is free. Interactive: prompt the user to release it,
# then re-check on Enter (same explicit-reminder policy as start.ps1).
# Non-interactive: poll every 5s.
wait_port_free() {
    local port="$1" name="$2" owner=""
    while true; do
        owner=$(port_pid "$port") || true
        [ -z "$owner" ] && return 0
        echo "[Port] $name port $port is occupied by PID $owner. Stop that process, then press Enter to re-check."
        if [ -t 0 ]; then
            read -r -p "Press Enter to re-check port $port: "
        else
            echo "[Port] Non-interactive shell: waiting 5s and retrying..."
            sleep 5
        fi
    done
}

# Poll $1 (space-separated URLs) until one answers, $3 secs elapse, or $2
# (the component PID) exits. IPv4/IPv6 dual-stack covers vite binding ::1.
wait_ready() {
    local urls="$1" pid="$2" name="$3" secs="$4" i=0 u=""
    while [ "$i" -lt "$secs" ]; do
        i=$((i + 1))
        if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
            echo " FAILED"
            echo "[$name] Process exited during startup. Log: $LOG_DIR/${name}_err.log"
            return 1
        fi
        for u in $urls; do
            if curl -fsS --max-time 2 "$u" >/dev/null 2>&1; then
                return 0
            fi
        done
        sleep 1
    done
    echo " FAILED"
    echo "[$name] Did not become ready within ${secs}s. Log: $LOG_DIR/${name}_err.log"
    return 1
}

trap stop_started EXIT

echo "========================================"
echo "  Start RPA Backend + Frontend"
echo "========================================"
echo ""

wait_port_free "$BACKEND_PORT" "Backend"
wait_port_free "$FRONTEND_PORT" "Frontend"

# --- Backend -------------------------------------------
echo "[Backend] Starting uvicorn..."
(
    cd "$ROOT_DIR" || exit 1
    exec python -m uvicorn app:app --host 0.0.0.0 --port "$BACKEND_PORT"
) >"$LOG_DIR/backend_err.log" 2>&1 &
BACKEND_PID=$!

echo -n "[Backend] Waiting for backend (up to 30s)..."
if ! wait_ready "http://127.0.0.1:$BACKEND_PORT/docs" "$BACKEND_PID" backend 30; then
    stop_started
    exit 1
fi
# The /docs response must come from OUR backend: any other FastAPI app on the
# port would pass the health check and the UI would come up empty.
OWNER=$(port_pid "$BACKEND_PORT") || true
if [ -n "$OWNER" ] && [ "$OWNER" != "$BACKEND_PID" ]; then
    echo " FAILED"
    echo "[Backend] Port $BACKEND_PORT is answered by PID $OWNER, not this script's backend (PID $BACKEND_PID)."
    stop_started
    exit 1
fi
echo " Ready!"

# --- Frontend ------------------------------------------
echo "[Frontend] Starting npm dev..."
(
    cd "$ROOT_DIR/frontend" || exit 1
    exec npm run dev
) >"$LOG_DIR/frontend_err.log" 2>&1 &
FRONTEND_PID=$!

echo -n "[Frontend] Waiting for frontend (up to 60s)..."
if ! wait_ready "http://localhost:$FRONTEND_PORT/ http://127.0.0.1:$FRONTEND_PORT/" "$FRONTEND_PID" frontend 60; then
    stop_started
    exit 1
fi
# vite is a grandchild of the npm wrapper; verify the listener's ancestry.
VITE_PID=$(port_pid "$FRONTEND_PORT") || true
if [ -z "$VITE_PID" ] || ! is_descendant "$VITE_PID" "$FRONTEND_PID"; then
    echo " FAILED"
    echo "[Frontend] Port $FRONTEND_PORT is served by an unexpected process (PID $VITE_PID)."
    stop_started
    exit 1
fi
echo " Ready!"

echo ""
echo "Backend  : http://localhost:$BACKEND_PORT"
echo "Frontend : http://localhost:$FRONTEND_PORT"
echo "Docs     : http://localhost:$BACKEND_PORT/docs"
echo ""
echo "Press Enter to stop all services."
echo "========================================"
if [ -t 0 ]; then
    read -r
fi
# trap EXIT stops the services.
