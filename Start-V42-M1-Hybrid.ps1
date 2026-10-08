param([switch]$Execute,[string]$RunId='hybrid_may01_20261008_5pct_pilot01')
$ErrorActionPreference='Stop'
$hybridRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Qualifier $hybridRoot) -ine 'D:') { throw 'D drive required' }
Set-Location -LiteralPath $hybridRoot
$env:TEMP="$hybridRoot\tmp"
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
# Native runner is the recorded BASE_HEAD pilot; a later HEAD requires a new
# reviewed preregistration. Default replay is valid on the delivered HEAD.
if ($Execute) { python -m v42_m1_hybrid.runner --execute --run-id $RunId }
else { python -m v42_m1_hybrid.replay }
exit $LASTEXITCODE
