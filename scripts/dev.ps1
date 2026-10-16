# Starts Postgres, the API, the LiveKit worker, and the dashboard.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Docker {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker @args 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Stop-PortListener {
    param([int]$Port)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Start-DevProcess {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    Write-Host "Starting $Label..."
    $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -PassThru -NoNewWindow
    if (-not $proc) {
        throw "Failed to start $Label"
    }
    return $proc
}

# --- Docker / Postgres ---
$docker = $false
for ($i = 0; $i -lt 30; $i++) {
    if ((Invoke-Docker info) -eq 0) { $docker = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $docker) {
    Write-Error "Docker Desktop is not running. Start it, then run this script again."
}

if ((Invoke-Docker compose up -d) -ne 0) {
    Write-Error "docker compose up failed."
}

$deadline = (Get-Date).AddMinutes(2)
do {
    if ((Invoke-Docker compose exec -T postgres pg_isready -U helpline -d helpline) -eq 0) { break }
    if ((Get-Date) -gt $deadline) { Write-Error "Postgres did not become ready." }
    Start-Sleep -Seconds 2
} while ($true)

# --- Preflight ---
$backend = Join-Path $root "backend"
$web = Join-Path $root "web"

if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Error "Missing backend/.env - copy backend/.env.example and fill in your keys."
}

if (-not (Test-Path (Join-Path $web "node_modules"))) {
    Write-Host "Installing web dependencies..."
    Push-Location $web
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed." }
    Pop-Location
}

# Free ports from a previous dev.ps1 run (or orphaned background processes).
Stop-PortListener -Port 8000
Stop-PortListener -Port 5173
Start-Sleep -Seconds 1

$api = $null
$worker = $null
$ui = $null

try {
    $api = Start-DevProcess -Label "API" -FilePath "uv" -ArgumentList @(
        "run", "uvicorn", "helpline.api:app", "--host", "127.0.0.1", "--port", "8000"
    ) -WorkingDirectory $backend

    $worker = Start-DevProcess -Label "LiveKit worker" -FilePath "uv" -ArgumentList @(
        "run", "python", "-m", "helpline.worker", "dev"
    ) -WorkingDirectory $backend

    # npm/npx on Windows are .cmd shims - Start-Process needs the .cmd extension.
    $ui = Start-DevProcess -Label "dashboard" -FilePath "npm.cmd" -ArgumentList @(
        "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"
    ) -WorkingDirectory $web

    Write-Host ""
    Write-Host "Dashboard  http://127.0.0.1:5173"
    Write-Host "API        http://127.0.0.1:8000/api/health"
    Write-Host "Press Ctrl+C to stop all services."
    Write-Host ""

    Wait-Process -Id $api.Id, $worker.Id, $ui.Id
} finally {
    foreach ($proc in @($api, $worker, $ui)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
