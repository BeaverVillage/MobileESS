param([string]$Python = 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe')
$ErrorActionPreference = 'Stop'
$v41Workspace = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location -LiteralPath $v41Workspace
try { & $Python -m dayahead.v41.campaign --stop; if ($LASTEXITCODE -ne 0) { throw 'V41 stop request failed' } }
finally { Pop-Location }
