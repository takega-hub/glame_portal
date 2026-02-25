param(
  [string]$Container = $env:POSTGRES_CONTAINER,
  [string]$DbUser = $env:POSTGRES_USER,
  [string]$DbName = $env:POSTGRES_DB,
  [string]$OutDir = $env:BACKUP_DIR
)

if ([string]::IsNullOrWhiteSpace($Container)) { $Container = "glame_postgres" }
if ([string]::IsNullOrWhiteSpace($DbUser)) { $DbUser = "glame_user" }
if ([string]::IsNullOrWhiteSpace($DbName)) { $DbName = "glame_db" }
if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = ".\\backups" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$outFile = Join-Path $OutDir "$($DbName)_$ts.dump"

Write-Host "Backing up $DbName from $Container -> $outFile"

docker exec $Container sh -lc "pg_dump -U '$DbUser' -d '$DbName' -Fc -f /tmp/$DbName.dump" | Out-Null
docker cp "$Container`:/tmp/$DbName.dump" "$outFile" | Out-Null
docker exec $Container sh -lc "rm -f /tmp/$DbName.dump" | Out-Null

Write-Host "OK: $outFile"

