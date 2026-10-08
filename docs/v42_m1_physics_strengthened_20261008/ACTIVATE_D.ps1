$physicsRoot='D:\v42_m1_physics_strengthened_20261008'
$env:TEMP=Join-Path $physicsRoot 'tmp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:GIT_TMPDIR=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $physicsRoot 'cache\pip'
$env:PYTHONPYCACHEPREFIX=Join-Path $physicsRoot 'cache\pycache'
$env:XDG_CACHE_HOME=Join-Path $physicsRoot 'cache'
$env:MPLCONFIGDIR=Join-Path $physicsRoot 'cache\matplotlib'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
Set-Location -LiteralPath (Join-Path $physicsRoot 'repo')