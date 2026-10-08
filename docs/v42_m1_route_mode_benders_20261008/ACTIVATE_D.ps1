$pilotDDriveRoot = 'D:\v42_m1_route_mode_benders_20261008'
$env:TEMP = Join-Path $pilotDDriveRoot 'tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:GIT_TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $pilotDDriveRoot 'cache\pip'
$env:PYTHONPYCACHEPREFIX = Join-Path $pilotDDriveRoot 'cache\pycache'
$env:XDG_CACHE_HOME = Join-Path $pilotDDriveRoot 'cache'
$env:MPLCONFIGDIR = Join-Path $pilotDDriveRoot 'cache\matplotlib'
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
Set-Location -LiteralPath (Join-Path $pilotDDriveRoot 'repo')
$env:PYTHONUTF8='1'
