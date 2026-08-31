$ErrorActionPreference = "Stop"

# Backend port must match frontend/vite.config.js (server.proxy targets);
# frontend port must match vite.config.js (server.port).
# Keep this file pure ASCII: PowerShell 5.1 reads BOM-less scripts in the ANSI
# codepage, and multi-byte comment characters can swallow line breaks.
$BackendPort  = 8000
$FrontendPort = 5173

Write-Host "========================================"
Write-Host "  Start RPA Backend + Frontend"
Write-Host "========================================"
Write-Host ""

# ComfyUI is a standalone service now - start it yourself and configure its
# URL in the frontend config page (scene-image section of the config page).

# --- Helpers -------------------------------------------
function Get-PortOwnerPid([int]$Port) {
    # PID of the process listening on $Port, or $null when the port is free.
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
    return $null
}

function Get-ProcessName([int]$ProcessId) {
    try { return (Get-Process -Id $ProcessId -ErrorAction Stop).ProcessName } catch { return "unknown" }
}

function Test-IsDescendantOf([int]$ProcessId, [int]$AncestorId) {
    # Walk the parent chain (bounded) to check whether $ProcessId was spawned
    # by $AncestorId. The vite node process is a grandchild of the cmd wrapper,
    # so ownership must be verified along the parent chain.
    $current = $ProcessId
    for ($i = 0; $i -lt 8 -and $current; $i++) {
        if ($current -eq $AncestorId) { return $true }
        try {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction Stop
            if (-not $proc.ParentProcessId) { return $false }
            $current = [int]$proc.ParentProcessId
        } catch { return $false }
    }
    return $false
}

function Stop-ProcessTree([int]$ProcessId) {
    # /T kills the whole child tree; a bare Kill() on "cmd /c npm run dev"
    # would leave the node.exe grandchild orphaned and holding the port.
    cmd /c "taskkill /PID $ProcessId /T /F >nul 2>&1"
}

function Stop-StartedComponents {
    if ($script:backend -and -not $script:backend.HasExited) { Stop-ProcessTree $script:backend.Id }
    if ($script:frontend -and -not $script:frontend.HasExited) { Stop-ProcessTree $script:frontend.Id }
}

function Wait-BeforeExit {
    # Pause before exiting so the window does not flash-close and bury the
    # error message (double-clicked scripts close instantly on exit).
    Write-Host ""
    Read-Host "Press Enter to close this window" | Out-Null
    exit 1
}

function Wait-PortFree([int]$Port, [string]$Component) {
    # Explicit-reminder policy: when the port is taken, do not abort - tell the
    # user who holds it and let them resolve it, then re-check on Enter.
    while ($true) {
        $ownerPid = Get-PortOwnerPid $Port
        if (-not $ownerPid) { return }
        Write-Host ""
        Write-Host "[Port] $Component port $Port is currently occupied by '$(Get-ProcessName $ownerPid)' (PID $ownerPid)." -ForegroundColor Yellow
        Write-Host "[Port] A foreign app on this port would pass the health checks and the app would come up empty." -ForegroundColor Yellow
        Write-Host "[Port] Stop that process, then press Enter here to re-check. (Close this window to cancel.)" -ForegroundColor Yellow
        Read-Host "Press Enter to re-check port $Port" | Out-Null
        Start-Sleep -Seconds 1
    }
}

# --- Pre-flight: both ports must be free ---------------
# Occupied ports are not fatal: remind the user explicitly and wait for them
# to free the port, instead of exiting (which flash-closes the window).
Wait-PortFree $BackendPort "Backend"
Wait-PortFree $FrontendPort "Frontend"

# --- Backend -------------------------------------------
Write-Host "[Backend] Starting uvicorn..."
$backend = Start-Process -FilePath "python" -ArgumentList "-m uvicorn app:app --host 0.0.0.0 --port $BackendPort" -PassThru -NoNewWindow -RedirectStandardError "backend_err.log"

Write-Host "[Backend] Waiting for backend (up to 30s)..." -NoNewline
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
    if ($backend.HasExited) { break }
    try {
        $null = Invoke-WebRequest "http://127.0.0.1:$BackendPort/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        $ready = $true
        break
    } catch {}
}
if (-not $ready) {
    Write-Host " FAILED"
    if ($backend.HasExited) {
        Write-Host "[Backend] Backend exited during startup (most likely the port was taken between the pre-flight check and binding). stderr:"
    } else {
        Write-Host "[Backend] Backend did not start within 30 seconds. Stopping it. stderr:"
        Stop-ProcessTree $backend.Id
    }
    Get-Content "backend_err.log" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Wait-BeforeExit
}
# The /docs response must come from OUR backend: any other FastAPI app on the
# port would pass the health check and the UI would come up empty.
# Poll 127.0.0.1 explicitly: "localhost" may resolve to ::1 first and time out
# against an IPv4-only uvicorn bind.
$ownerPid = Get-PortOwnerPid $BackendPort
if ($ownerPid -ne $backend.Id) {
    Write-Host " FAILED"
    Write-Host "[Backend] Port $BackendPort is answered by PID $ownerPid ($(Get-ProcessName $ownerPid)), not by this script's backend (PID $($backend.Id))." -ForegroundColor Red
    Stop-StartedComponents
    Wait-BeforeExit
}
Write-Host " Ready!"

# --- Frontend ------------------------------------------
Write-Host "[Frontend] Starting npm dev..."
$frontend = Start-Process -FilePath "cmd" -ArgumentList "/c npm run dev" -WorkingDirectory (Join-Path $PSScriptRoot "frontend") -PassThru -NoNewWindow -RedirectStandardError "frontend_err.log"

Write-Host "[Frontend] Waiting for frontend (up to 60s)..." -NoNewline
$ready = $false
# vite binds the IPv6 ::1 stack by default while uvicorn binds IPv4 only, so
# try both loopback forms - a single fixed host name is not reliable for both.
$frontendUrls = @("http://localhost:$FrontendPort/", "http://127.0.0.1:$FrontendPort/")
for ($i = 1; $i -le 60; $i++) {
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
    if ($frontend.HasExited) { break }
    foreach ($u in $frontendUrls) {
        try {
            $null = Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            $ready = $true
            break
        } catch {}
    }
    if ($ready) { break }
}
if (-not $ready) {
    Write-Host " FAILED"
    Write-Host "[Frontend] Frontend did not start. Stopping all components. stderr:"
    Get-Content "frontend_err.log" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    Stop-StartedComponents
    Wait-BeforeExit
}
$vitePid = Get-PortOwnerPid $FrontendPort
if (-not $vitePid -or -not (Test-IsDescendantOf $vitePid $frontend.Id)) {
    Write-Host " FAILED"
    Write-Host "[Frontend] Port $FrontendPort is served by an unexpected process (PID $vitePid). Stopping all components." -ForegroundColor Red
    Stop-StartedComponents
    Wait-BeforeExit
}
Write-Host " Ready!"

Write-Host ""
Write-Host "Backend  : http://localhost:$BackendPort"
Write-Host "Frontend : http://localhost:$FrontendPort"
Write-Host "Docs     : http://localhost:$BackendPort/docs"
Write-Host ""
Write-Host "Close this window or press Enter to stop all services."
Write-Host "========================================"
Read-Host | Out-Null

Stop-StartedComponents
