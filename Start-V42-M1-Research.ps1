param([switch]$Execute, [string]$RunId='joint_gap_20261008')
$ErrorActionPreference='Stop'
$researchRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Qualifier $researchRoot) -ine 'D:') { throw 'V42 research requires D drive' }
Set-Location -LiteralPath $researchRoot
New-Item -ItemType Directory -Force -Path "$researchRoot\tmp","$researchRoot\cache" | Out-Null
$env:TEMP="$researchRoot\tmp"
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
if ($Execute) { python -m v42_m1_research.runner --execute --run-id $RunId }
else { python -m v42_m1_research.runner --run-id $RunId }
exit $LASTEXITCODE
