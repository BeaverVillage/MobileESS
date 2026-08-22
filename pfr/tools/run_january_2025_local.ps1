[CmdletBinding()]
param(
    [int]$StartDay = 1,
    [int]$EndDay = 31,
    [int]$DayWorkers = 4,
    [int]$GurobiThreads = 4,
    [string]$OutputRoot = '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR11_JAN2025_DAYS01_31_LOCAL_4X4',
    [switch]$MonitorOnly,
    [double]$WatchSeconds = 15
)

$ErrorActionPreference = 'Stop'
$repoWin = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$repoWsl = (& wsl wslpath -a $repoWin).Trim()
$python = '/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python'

function Quote-Bash([string]$Value) {
    if ($Value.Contains("'")) {
        throw "Bash argument contains an unsupported single quote: $Value"
    }
    return "'$Value'"
}

if ($MonitorOnly) {
    $monitor = @(
        (Quote-Bash $python), '-m', 'pfr.tools.show_january_progress',
        '--root', (Quote-Bash $OutputRoot),
        '--start-day', $StartDay, '--end-day', $EndDay,
        '--watch-seconds', $WatchSeconds
    ) -join ' '
    & wsl bash -lc "cd $(Quote-Bash $repoWsl) && $monitor"
    exit $LASTEXITCODE
}

$logicalCpu = [int]((& wsl nproc).Trim())
if ($DayWorkers -lt 1 -or $GurobiThreads -lt 1) {
    throw 'DayWorkers and GurobiThreads must both be positive.'
}
if ($DayWorkers * $GurobiThreads -gt $logicalCpu) {
    throw "DayWorkers x GurobiThreads exceeds WSL logical CPUs: $DayWorkers x $GurobiThreads > $logicalCpu"
}

$arguments = @(
    '-m', 'pfr.tools.run_pfr_daily_campaign',
    '--repo', (Quote-Bash $repoWsl),
    '--start-day', $StartDay, '--end-day', $EndDay,
    '--day-workers', $DayWorkers, '--capture-day-logs',
    '--shared-root', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SHARED_EXOGENOUS_CURRENT',
    '--exact-package-root', '/mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package',
    '--authority-package-root', '/home/jaewon/mobile_ess_work/run_packages/K9H7_V2044R11R1_20260807T191351',
    '--primary-root', '/home/jaewon/mobile_ess_work/processed/power_v70_3ph',
    '--initial-state', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_DAILY_PRE_CURRENT/JAN2025_DAILY_CANONICAL_PRE_MANIFEST.json',
    '--independent-jobs', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_JOB_COHORT_FIXED_AEST_CURRENT/JAN2025_INDEPENDENT_JOB_COHORT.parquet',
    '--canonical-jobs', '/home/jaewon/mobile_ess_work/frozen_artifacts/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet',
    '--power-curve', (Quote-Bash "$repoWsl/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json"),
    '--mobility-root', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_0000/mobility',
    '--mobility-root', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_2304/mobility',
    '--mobility-root', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_4608/mobility',
    '--mobility-root', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_6912/mobility',
    '--route-catalog', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json',
    '--mobility-template-bank', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_0000/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet',
    '--workload-uncertainty', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json',
    '--factorized-uncertainty', '/home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json',
    '--output', (Quote-Bash $OutputRoot)
) -join ' '

$environment = "PFR_GUROBI_THREADS=$GurobiThreads OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0"
Write-Host "Starting $StartDay-$EndDay with $DayWorkers processes x $GurobiThreads Gurobi threads (WSL CPUs=$logicalCpu)."
Write-Host 'Monitor in another PowerShell:'
Write-Host ".\pfr\tools\run_january_2025_local.ps1 -MonitorOnly -OutputRoot '$OutputRoot'"
& wsl bash -lc "cd $(Quote-Bash $repoWsl) && $environment $(Quote-Bash $python) $arguments"
exit $LASTEXITCODE
