param(
  [Parameter(Mandatory=$true)][string]$DumpFile,
  [string]$Container = $env:POSTGRES_CONTAINER,
  [string]$DbUser = $env:POSTGRES_USER,
  [string]$DbName = $env:POSTGRES_DB
)

if (-not (Test-Path $DumpFile)) { throw "Dump file not found: $DumpFile" }
if ([string]::IsNullOrWhiteSpace($Container)) { $Container = "glame_postgres" }
if ([string]::IsNullOrWhiteSpace($DbUser)) { $DbUser = "glame_user" }
if ([string]::IsNullOrWhiteSpace($DbName)) { $DbName = "glame_db" }

Write-Host "Restoring $DumpFile -> $DbName in $Container"

docker cp "$DumpFile" "$Container`:/tmp/restore.dump" | Out-Null
docker exec $Container sh -lc "pg_restore -U '$DbUser' -d '$DbName' --clean --if-exists --no-owner --no-privileges /tmp/restore.dump" | Out-Null
docker exec $Container sh -lc "rm -f /tmp/restore.dump" | Out-Null

Write-Host "OK: restored"

