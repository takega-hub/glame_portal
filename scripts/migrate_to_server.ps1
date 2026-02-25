<#
.SYNOPSIS
  Перенос данных GLAME (Postgres, Qdrant, файлы backend) с локальной Windows на сервер.
.DESCRIPTION
  Создаёт дамп Postgres, snapshot коллекций Qdrant, архив каталогов backend (uploads, static, generated_messages),
  копирует всё на сервер по SCP и выводит инструкции для восстановления на сервере.
.PARAMETER ServerUser
  Имя пользователя SSH на сервере (например ubuntu).
.PARAMETER ServerHost
  IP или хост сервера (например 5.101.179.47).
.PARAMETER ServerPath
  Каталог проекта на сервере (например /home/ubuntu/glame-platform).
.PARAMETER KeyPath
  Путь к приватному ключу SSH (опционально).
.PARAMETER SkipPostgres
  Не создавать дамп Postgres (использовать существующий в backups).
.PARAMETER SkipQdrant
  Не создавать snapshot Qdrant.
.PARAMETER SkipFiles
  Не архивировать файлы backend.
.EXAMPLE
  .\migrate_to_server.ps1 -ServerUser ubuntu -ServerHost 5.101.179.47 -ServerPath /home/ubuntu/glame-platform
#>
param(
  [Parameter(Mandatory = $true)][string]$ServerUser,
  [Parameter(Mandatory = $true)][string]$ServerHost,
  [Parameter(Mandatory = $true)][string]$ServerPath,
  [string]$KeyPath = "",
  [switch]$SkipPostgres,
  [switch]$SkipQdrant,
  [switch]$SkipFiles
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot "..")
$backupsDir = Join-Path $repoRoot "backups"
$migrationDir = Join-Path $repoRoot "migration_data"

function SshScpArgs {
  $opts = @()
  if (-not [string]::IsNullOrWhiteSpace($KeyPath) -and (Test-Path $KeyPath)) {
    $opts += "-i", $KeyPath
  }
  return $opts
}

function Invoke-Scp {
  param([string]$Local, [string]$Remote)
  $scpArgs = @(SshScpArgs) + @("$($Local)", "${ServerUser}@${ServerHost}:$($Remote)")
  & scp @scpArgs
  if ($LASTEXITCODE -ne 0) { throw "scp failed: $Local -> $Remote" }
}

function Invoke-Ssh {
  param([string]$Command)
  $sshArgs = @(SshScpArgs) + @("-o", "StrictHostKeyChecking=accept-new", "${ServerUser}@${ServerHost}", $Command)
  & ssh @sshArgs
  if ($LASTEXITCODE -ne 0) { throw "ssh failed: $Command" }
}

New-Item -ItemType Directory -Force -Path $backupsDir | Out-Null

# --- 1. Postgres dump ---
if (-not $SkipPostgres) {
  Write-Host "=== Postgres backup ==="
  Set-Location $repoRoot
  & (Join-Path $scriptRoot "backup_postgres_docker.ps1")
  if ($LASTEXITCODE -ne 0) { throw "Postgres backup failed" }
  Set-Location $scriptRoot
} else {
  $latestDump = Get-ChildItem -Path $backupsDir -Filter "glame_db_*.dump" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $latestDump) { throw "SkipPostgres set but no glame_db_*.dump found in $backupsDir" }
  Write-Host "Using existing dump: $($latestDump.FullName)"
}

# --- 2. Qdrant snapshots ---
$qdrantSnapshots = @()
if (-not $SkipQdrant) {
  Write-Host "=== Qdrant snapshots ==="
  $qdrantUrl = "http://localhost:6333"
  try {
    $collectionsJson = Invoke-RestMethod -Uri "$qdrantUrl/collections" -Method Get -ErrorAction Stop
    $collections = $collectionsJson.result.collections | ForEach-Object { $_.name }
  } catch {
    Write-Warning "Qdrant not reachable at $qdrantUrl. Start local stack (docker compose -f infra/docker-compose.yml up -d) or use -SkipQdrant."
    $collections = @()
  }
  foreach ($coll in $collections) {
    try {
      $snap = Invoke-RestMethod -Uri "$qdrantUrl/collections/$coll/snapshots?wait=true" -Method Post -ErrorAction Stop
      $snapName = $snap.result.name
      $outPath = Join-Path $backupsDir "qdrant_${coll}_$snapName"
      Invoke-WebRequest -Uri "$qdrantUrl/collections/$coll/snapshots/$snapName" -OutFile $outPath -UseBasicParsing
      $qdrantSnapshots += $outPath
      Write-Host "  $coll -> $snapName"
    } catch {
      Write-Warning "  $coll : $($_.Exception.Message)"
    }
  }
  if ($qdrantSnapshots.Count -eq 0) { Write-Host "  No Qdrant snapshots created." }
}

# --- 3. Backend files archive ---
$backendArchive = $null
if (-not $SkipFiles) {
  Write-Host "=== Backend files archive ==="
  New-Item -ItemType Directory -Force -Path $migrationDir | Out-Null
  $backendRoot = Join-Path $repoRoot "backend"
  $uploadsSrc = Join-Path $backendRoot "uploads"
  $staticSrc = Join-Path $backendRoot "static"
  $gm1 = Join-Path $backendRoot "generated_messages"
  $gm2 = Join-Path $backendRoot "backend\generated_messages"
  $gmDest = Join-Path $migrationDir "generated_messages"
  if (Test-Path $uploadsSrc) {
    $dest = Join-Path $migrationDir "uploads"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -Path "$uploadsSrc\*" -Destination $dest -Recurse -Force
    Write-Host "  uploads"
  }
  if (Test-Path $staticSrc) {
    $dest = Join-Path $migrationDir "static"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -Path "$staticSrc\*" -Destination $dest -Recurse -Force
    Write-Host "  static"
  }
  New-Item -ItemType Directory -Force -Path $gmDest | Out-Null
  if (Test-Path $gm1) {
    Copy-Item -Path "$gm1\*" -Destination $gmDest -Recurse -Force
    Write-Host "  generated_messages (backend/)"
  }
  if (Test-Path $gm2) {
    Copy-Item -Path "$gm2\*" -Destination $gmDest -Recurse -Force
    Write-Host "  generated_messages (backend/backend/)"
  }
  $ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $archiveName = "data_backend_files_$ts.zip"
  $backendArchive = Join-Path $backupsDir $archiveName
  Compress-Archive -Path "$migrationDir\*" -DestinationPath $backendArchive -Force
  Write-Host "  Archive: $backendArchive"
}

# --- 4. Copy to server ---
Write-Host "=== Copy to server ==="
$remoteBackups = "$ServerPath/backups"
Invoke-Ssh "mkdir -p $remoteBackups"

# Latest Postgres dump
$dumps = Get-ChildItem -Path $backupsDir -Filter "glame_db_*.dump" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
if ($dumps) {
  Invoke-Scp $dumps[0].FullName "$remoteBackups/"
  Write-Host "  Postgres: $($dumps[0].Name)"
}

# Qdrant snapshots
foreach ($s in $qdrantSnapshots) {
  Invoke-Scp $s "$remoteBackups/"
  Write-Host "  Qdrant: $(Split-Path -Leaf $s)"
}

# Backend files archive
if ($backendArchive -and (Test-Path $backendArchive)) {
  Invoke-Scp $backendArchive "$remoteBackups/"
  Write-Host "  Backend files: $(Split-Path -Leaf $backendArchive)"
}

Write-Host ""
Write-Host "=== Done. Next steps ON THE SERVER ===" -ForegroundColor Green
Write-Host "1. Restore Postgres:"
Write-Host "   ./scripts/restore_postgres_docker.sh ./backups/glame_db_<timestamp>.dump"
Write-Host ""
Write-Host "2. Restore backend files into volumes (see docs/DEPLOY_SERVER.md section 8.2):"
Write-Host "   unzip -o backups/data_backend_files_*.zip -d migration_data"
Write-Host "   # then copy migration_data/uploads, migration_data/static, migration_data/generated_messages into backend volumes"
Write-Host ""
if ($qdrantSnapshots.Count -gt 0) {
  Write-Host "3. Restore Qdrant (for each snapshot):"
  Write-Host "   ./scripts/restore_qdrant_from_snapshot.sh ./backups/qdrant_<collection>_<name>.snapshot"
}
Write-Host ""
Write-Host "4. Restart backend: docker compose -f infra/docker-compose.prod.yml start backend"
Write-Host "   Full manual: docs/DEPLOY_SERVER.md"
