# ==============================================================================
# Currency Rate Analyzer - Backend Setup & Launch Script (uv-based)
# ==============================================================================
# Usage:
#   .\setup.ps1              # Create venv & install dependencies
#   .\setup.ps1 -Run         # Setup (if needed) and run FastAPI backend server
#   .\setup.ps1 -Ml          # Include optional ML dependencies (requirements-ml.txt)
#   .\setup.ps1 -Recreate    # Recreate virtual environment from scratch
#   .\setup.ps1 -Help        # Display help information
# ==============================================================================

[CmdletBinding()]
param(
    [Alias("r")]
    [switch]$Run,

    [Alias("m")]
    [switch]$Ml,

    [Alias("f")]
    [switch]$Recreate,

    [switch]$Migrate,

    [Alias("p")]
    [string]$Python = "3.11",

    [Alias("h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host @"
Currency Rate Analyzer - Backend Setup Script (uv)

Usage:
  .\setup.ps1 [OPTIONS]

Options:
  -Run, -r          Set up (if needed) and start the FastAPI backend server
  -Ml, -m           Install optional ML forecasting dependencies (requirements-ml.txt)
  -Python, -p <ver> Specify Python version for uv venv (default: 3.11)
  -Recreate, -f     Remove and recreate the virtual environment (.venv)
  -Migrate          Run Alembic database migrations (alembic upgrade head)
  -Help, -h         Show this help message

Examples:
  .\setup.ps1               # Standard setup: venv + requirements-dev.txt
  .\setup.ps1 -Run          # Set up environment and immediately start backend
  .\setup.ps1 -Ml -Run      # Set up with ML packages and start backend
"@ -ForegroundColor Cyan
}

if ($Help) {
    Show-Help
    exit 0
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Currency Rate Analyzer - Backend Setup (uv)                   " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# Determine paths
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$ProjectRoot = $ScriptDir
$BackendDir = Join-Path $ProjectRoot "project\backend"
$VenvDir = Join-Path $BackendDir ".venv"

# Ensure common paths are in current session PATH
$uvCommonPaths = @(
    (Join-Path $env:USERPROFILE ".cargo\bin"),
    (Join-Path $env:LOCALAPPDATA "uv\bin"),
    (Join-Path $env:LOCALAPPDATA "Programs\uv\bin")
)

foreach ($path in $uvCommonPaths) {
    if (Test-Path $path) {
        if ($env:Path -notlike "*$path*") {
            $env:Path = "$path;$env:Path"
        }
    }
}

# Step 1: Ensure uv is installed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[!] uv is not installed on this system." -ForegroundColor Yellow
    Write-Host "[*] Installing uv via official PowerShell script (https://astral.sh/uv)..." -ForegroundColor Cyan
    try {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    } catch {
        Write-Host "[ERROR] Automatic uv installation failed." -ForegroundColor Red
        Write-Host "Please install uv manually: powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""
        Write-Host "or via winget: winget install --id=astral-sh.uv -e"
        exit 1
    }

    # Refresh PATH after installation
    foreach ($path in $uvCommonPaths) {
        if (Test-Path $path) {
            if ($env:Path -notlike "*$path*") {
                $env:Path = "$path;$env:Path"
            }
        }
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] uv installed but not found in PATH for current session." -ForegroundColor Red
        Write-Host "Please restart your PowerShell window or add uv to your PATH."
        exit 1
    }
}

$uvVersion = uv --version
Write-Host "[✓] Using uv: $uvVersion" -ForegroundColor Green

# Step 2: Ensure .env exists in project\backend
$EnvFile = Join-Path $BackendDir ".env"
$EnvExample = Join-Path $BackendDir ".env.example"

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Write-Host "[*] .env not found. Creating from .env.example..." -ForegroundColor Yellow
        Copy-Item $EnvExample $EnvFile
        Write-Host "[✓] Created $EnvFile" -ForegroundColor Green
    } else {
        Write-Host "[!] .env.example not found in $BackendDir." -ForegroundColor Yellow
    }
} else {
    Write-Host "[✓] Backend .env file already exists." -ForegroundColor Green
}

# Step 3: Create or recreate virtual environment
if ($Recreate -and (Test-Path $VenvDir)) {
    Write-Host "[*] Removing existing virtual environment at $VenvDir..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $VenvDir
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "[*] Creating virtual environment at $VenvDir (Python $Python)..." -ForegroundColor Cyan
    uv venv $VenvDir --python $Python
    Write-Host "[✓] Virtual environment created successfully." -ForegroundColor Green
} else {
    Write-Host "[✓] Virtual environment already exists at $VenvDir." -ForegroundColor Green
}

# Step 4: Install dependencies
$ReqDev = Join-Path $BackendDir "requirements-dev.txt"
Write-Host "[*] Installing backend dependencies (requirements-dev.txt)..." -ForegroundColor Cyan
uv pip install --python $VenvDir -r $ReqDev

if ($Ml) {
    $ReqMl = Join-Path $BackendDir "requirements-ml.txt"
    Write-Host "[*] Installing ML forecasting dependencies (requirements-ml.txt)..." -ForegroundColor Cyan
    uv pip install --python $VenvDir -r $ReqMl
}

Write-Host "[✓] All requested dependencies are installed." -ForegroundColor Green

# Step 5: Optional Migration & Run Server
if ($Migrate) {
    Write-Host "[*] Applying database migrations (alembic upgrade head)..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        uv run --python $VenvDir alembic upgrade head
    } catch {
        Write-Host "[!] Alembic migration failed. Please ensure PostgreSQL is running." -ForegroundColor Yellow
    } finally {
        Pop-Location
    }
}

if ($Run) {
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "[*] Starting FastAPI backend with uvicorn..." -ForegroundColor Green
    Write-Host "    API URL: http://127.0.0.1:8000" -ForegroundColor Cyan
    Write-Host "    Health check: http://127.0.0.1:8000/health" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
    Set-Location $BackendDir
    uv run --python $VenvDir uvicorn app.main:app --reload --reload-dir app
    exit 0
}

# Completion Guide
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "[✓] Backend environment setup is complete!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "To start the backend immediately:"
Write-Host "  .\setup.ps1 -Run" -ForegroundColor Yellow
Write-Host ""
Write-Host "Or activate the virtual environment manually:"
Write-Host "  .\project\backend\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  cd project\backend" -ForegroundColor Yellow
Write-Host "  alembic upgrade head               # (PostgreSQL required)" -ForegroundColor Yellow
Write-Host "  uvicorn app.main:app --reload --reload-dir app" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan
