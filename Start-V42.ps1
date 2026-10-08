param([ValidateSet('run','replay','status','audit','build-only','handoff-check')][string]$Mode='status', [string]$Handoff)
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Qualifier $repoRoot) -ine 'D:') { throw 'V42 requires the D drive' }
Set-Location -LiteralPath $repoRoot
New-Item -ItemType Directory -Force -Path "$repoRoot\tmp","$repoRoot\cache" | Out-Null
$env:TEMP="$repoRoot\tmp"
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
if ($Mode -eq 'handoff-check') { python -m v42_unified $Mode --handoff $Handoff }
else { python -m v42_unified $Mode }
exit $LASTEXITCODE
