$groupWorkRoot='D:\v42_m1_group_branching_20261008'
$env:TEMP=Join-Path $groupWorkRoot 'tmp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:GIT_TMPDIR=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $groupWorkRoot 'cache\pip'
$env:PYTHONPYCACHEPREFIX=Join-Path $groupWorkRoot 'cache\pycache'
$env:XDG_CACHE_HOME=Join-Path $groupWorkRoot 'cache'
$env:MPLCONFIGDIR=Join-Path $groupWorkRoot 'cache\matplotlib'
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
Set-Location -LiteralPath (Join-Path $groupWorkRoot 'repo')
