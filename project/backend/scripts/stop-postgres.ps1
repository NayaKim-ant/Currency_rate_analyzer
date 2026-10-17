$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "BasisMarket\PostgreSQL\17"
$binCandidates = @(
    (Join-Path $installRoot "pgsql\bin"),
    (Join-Path $installRoot "bin")
)
$binPath = $binCandidates | Where-Object { Test-Path (Join-Path $_ "pg_ctl.exe") } | Select-Object -First 1
$dataPath = Join-Path $env:LOCALAPPDATA "BasisMarket\PostgreSQL\data"
if (-not $binPath -or -not (Test-Path (Join-Path $dataPath "PG_VERSION"))) {
    Write-Output "PostgreSQL data directory is not initialized"
    exit 0
}

& (Join-Path $binPath "pg_ctl.exe") -D $dataPath -m fast -w stop
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL failed to stop cleanly" }
