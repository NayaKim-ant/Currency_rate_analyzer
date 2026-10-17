$ErrorActionPreference = "Stop"
$version = "17.11-5"
$archiveName = "postgresql-$version-windows-x64-binaries.zip"
$archivePath = Join-Path $env:TEMP $archiveName
$installRoot = Join-Path $env:LOCALAPPDATA "BasisMarket\PostgreSQL\17"
$downloadUrl = "https://get.enterprisedb.com/postgresql/$archiveName"
$expectedBytes = 381531864

if (-not (Test-Path -LiteralPath $archivePath) -or (Get-Item -LiteralPath $archivePath).Length -ne $expectedBytes) {
    Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $archivePath
}

$archive = Get-Item -LiteralPath $archivePath
if ($archive.Length -ne $expectedBytes) {
    throw "Unexpected PostgreSQL archive size: $($archive.Length) bytes"
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Expand-Archive -LiteralPath $archivePath -DestinationPath $installRoot -Force

$binCandidates = @(
    (Join-Path $installRoot "pgsql\bin"),
    (Join-Path $installRoot "bin")
)
$binPath = $binCandidates | Where-Object { Test-Path (Join-Path $_ "initdb.exe") } | Select-Object -First 1
if (-not $binPath) {
    throw "initdb.exe was not found in the extracted PostgreSQL archive"
}

Write-Output "PostgreSQL installed at $installRoot"
& (Join-Path $binPath "postgres.exe") --version
