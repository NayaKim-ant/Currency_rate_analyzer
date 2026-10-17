$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "BasisMarket\PostgreSQL\17"
$binCandidates = @(
    (Join-Path $installRoot "pgsql\bin"),
    (Join-Path $installRoot "bin")
)
$binPath = $binCandidates | Where-Object { Test-Path (Join-Path $_ "pg_ctl.exe") } | Select-Object -First 1
if (-not $binPath) {
    throw "PostgreSQL binaries not found. Run scripts\install-postgres-portable.ps1 first."
}

$dataPath = Join-Path $env:LOCALAPPDATA "BasisMarket\PostgreSQL\data"
$logPath = Join-Path $env:LOCALAPPDATA "BasisMarket\PostgreSQL\postgresql.log"
New-Item -ItemType Directory -Path (Split-Path $logPath) -Force | Out-Null

if (-not (Test-Path (Join-Path $dataPath "PG_VERSION"))) {
    & (Join-Path $binPath "initdb.exe") -D $dataPath -U postgres --auth-local=trust --auth-host=trust --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL initialization failed" }
}

& (Join-Path $binPath "pg_ctl.exe") status -D $dataPath *> $null
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $binPath "pg_ctl.exe") -D $dataPath -l $logPath -o "-h 127.0.0.1 -p 5432" -w start
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL failed to start; inspect $logPath" }
}

$roleExists = & (Join-Path $binPath "psql.exe") -h 127.0.0.1 -p 5432 -U postgres -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'market_user'"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect PostgreSQL roles" }
if (([string]$roleExists).Trim() -ne "1") {
    & (Join-Path $binPath "createuser.exe") -h 127.0.0.1 -p 5432 -U postgres --no-superuser --no-createdb --no-createrole market_user
    if ($LASTEXITCODE -ne 0) { throw "Could not create market_user" }
}

$databaseExists = & (Join-Path $binPath "psql.exe") -w -h 127.0.0.1 -p 5432 -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'market_data'"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect PostgreSQL databases" }
if (([string]$databaseExists).Trim() -ne "1") {
    & (Join-Path $binPath "createdb.exe") -w -h 127.0.0.1 -p 5432 -U postgres -O market_user market_data
    if ($LASTEXITCODE -ne 0) { throw "Could not create market_data database" }
}
Write-Output "PostgreSQL is ready at 127.0.0.1:5432; data persists in $dataPath"
