<#
.SYNOPSIS
  Обновление деплоя на сервере: через Git (рекомендуется) или загрузка архива с Windows.
.DESCRIPTION
  -UseGit: на сервере выполнить git pull и scripts/deploy_from_git.sh (код уже в репозитории на сервере).
  Без -UseGit: упаковать код в архив, скопировать по SCP, распаковать и запустить docker compose + миграции.
.PARAMETER UseGit
  Обновлять через Git (git pull + deploy_from_git.sh на сервере). Не загружать архив с Windows.
.PARAMETER ServerUser
  Имя пользователя SSH на сервере.
.PARAMETER ServerHost
  IP или хост сервера.
.PARAMETER ServerPath
  Каталог проекта на сервере (при -UseGit — путь к клонированному репозиторию).
.PARAMETER KeyPath
  Путь к приватному ключу SSH (опционально).
.PARAMETER BackupBefore
  Перед обновлением выполнить на сервере backup Postgres.
.PARAMETER SkipBuild
  Не пересобирать образы (только перезапуск). Игнорируется при -UseGit.
.EXAMPLE
  .\update_server.ps1 -ServerUser glame -ServerHost portal.glamejewelry.ru -ServerPath /home/glame/glame-platform -UseGit
#>
param(
  [Parameter(Mandatory = $true)][string]$ServerUser,
  [Parameter(Mandatory = $true)][string]$ServerHost,
  [Parameter(Mandatory = $true)][string]$ServerPath,
  [string]$KeyPath = "",
  [switch]$UseGit,
  [switch]$BackupBefore,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot "..")

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
  if ($LASTEXITCODE -ne 0) { throw "scp failed" }
}

function Invoke-Ssh {
  param([string]$Command)
  $sshArgs = @(SshScpArgs) + @("-o", "StrictHostKeyChecking=accept-new", "${ServerUser}@${ServerHost}", $Command)
  & ssh @sshArgs
  if ($LASTEXITCODE -ne 0) { throw "ssh failed: $Command" }
}

if ($UseGit) {
  Write-Host "=== Update via Git (pull + deploy_from_git.sh) ==="
  if ($BackupBefore) {
    Invoke-Ssh "cd $ServerPath && chmod +x scripts/*.sh 2>/dev/null; ./scripts/backup_postgres_docker.sh 2>/dev/null || true"
  }
  Invoke-Ssh "cd $ServerPath && chmod +x scripts/deploy_from_git.sh 2>/dev/null; ./scripts/deploy_from_git.sh"
  Write-Host ""
  Write-Host "=== Update complete ===" -ForegroundColor Green
  Write-Host "  Site: http://${ServerHost}/"
  Write-Host "  API:  http://${ServerHost}/api/"
  exit 0
}

# Build code archive (exclude heavy/unnecessary dirs: node_modules, venv, etc. removed after copy)
$archiveName = "glame_code_update_$(Get-Date -Format 'yyyyMMddHHmmss').zip"
$archivePath = Join-Path $env:TEMP $archiveName
$toZip = @(
  "backend\app",
  "backend\alembic.ini",
  "backend\requirements.txt",
  "backend\Dockerfile",
  "backend\Dockerfile.prod",
  "frontend\src",
  "frontend\public",
  "frontend\package.json",
  "frontend\package-lock.json",
  "frontend\next.config.js",
  "frontend\Dockerfile",
  "frontend\tsconfig.json",
  "frontend\tailwind.config.js",
  "frontend\postcss.config.js",
  "data\migrations",
  "infra",
  ".env.example"
)
# Add root files (relative paths only; do not include .env)
Get-ChildItem -Path $repoRoot -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne ".env" } | ForEach-Object { $toZip += $_.Name }
$tempDir = Join-Path $env:TEMP "glame_update_src"
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

Write-Host "=== Preparing code archive ==="
foreach ($item in $toZip) {
  $full = Join-Path $repoRoot $item
  if (-not (Test-Path $full)) { continue }
  $dest = Join-Path $tempDir $item
  $parent = Split-Path -Parent $dest
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  if (Test-Path $full -PathType Container) {
    Copy-Item -Path $full -Destination $dest -Recurse -Force
  } else {
    Copy-Item -Path $full -Destination $dest -Force
  }
}
# Remove excluded
foreach ($e in @("node_modules", "venv", "__pycache__", ".next")) {
  Get-ChildItem -Path $tempDir -Recurse -Directory -Filter $e -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Compress-Archive -Path "$tempDir\*" -DestinationPath $archivePath -Force
Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
$size = (Get-Item $archivePath).Length / 1MB
Write-Host "  Archive: $archivePath ($([math]::Round($size, 2)) MB)"

# Copy to server
Write-Host "=== Uploading to server ==="
Invoke-Scp $archivePath "$ServerPath/$archiveName"

# Remote commands
$composeCmd = "docker compose -f infra/docker-compose.prod.yml"
if ($BackupBefore) {
  Write-Host "=== Backup Postgres on server ==="
  Invoke-Ssh "cd $ServerPath && chmod +x scripts/*.sh 2>/dev/null; ./scripts/backup_postgres_docker.sh 2>/dev/null || true"
}
Write-Host "=== Extracting and deploying on server ==="
$upCmd = if ($SkipBuild) { "up -d" } else { "up -d --build" }
Invoke-Ssh "cd $ServerPath && unzip -o -q $archiveName -d . && rm -f $archiveName && $composeCmd $upCmd && docker exec glame_backend alembic upgrade head"
Remove-Item $archivePath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Update complete ===" -ForegroundColor Green
Write-Host "  Site: http://${ServerHost}/"
Write-Host "  API:  http://${ServerHost}/api/"
