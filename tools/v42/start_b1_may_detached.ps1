param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$worktree=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$freeze=Get-Content -LiteralPath (Join-Path $Root 'B1_PRODUCTION_FREEZE_MANIFEST.json') -Raw | ConvertFrom-Json
Set-Location -LiteralPath $worktree
& $freeze.Python -m v42_b1_production.detach --root $Root
if ($LASTEXITCODE -ne 0) { throw "Detached launch failed: $LASTEXITCODE" }
