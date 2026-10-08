param([switch]$Execute,[string]$RunId='anytime_may01_20261008_frontier01')
$ErrorActionPreference='Stop'
$anytimeRoot=Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Qualifier $anytimeRoot) -ine 'D:') { throw 'D drive required' }
Set-Location -LiteralPath $anytimeRoot
$env:TEMP="$anytimeRoot\tmp"
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
if ($Execute) { python -m v42_m1_anytime.runner --execute --run-id $RunId }
else { python -m v42_m1_anytime.runner --run-id $RunId }
exit $LASTEXITCODE
