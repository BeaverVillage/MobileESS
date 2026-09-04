param(
    [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$progressPath = Join-Path $Repo "progress\V39E_OVERNIGHT_PROGRESS.json"
$logPath = Join-Path $Repo "logs\v39e_overnight.log"

while ($true) {
    Clear-Host
    Write-Host "=================================================="
    Write-Host "MobileESS V39E MAY 2025 OVERNIGHT CAMPAIGN"
    Write-Host "=================================================="
    if (-not (Test-Path -LiteralPath $progressPath)) {
        Write-Host "Waiting for atomic progress evidence..."
        Start-Sleep -Seconds 10
        continue
    }
    try {
        $p = Get-Content -LiteralPath $progressPath -Raw | ConvertFrom-Json
        Write-Host "MODE: $($p.campaign_classification)"
        Write-Host "PHASE: $($p.phase)"
        Write-Host "Git HEAD: $($p.git_HEAD)"
        Write-Host "Branch: $($p.branch)"
        Write-Host "Elapsed: $($p.elapsed_seconds) sec"
        Write-Host ""
        Write-Host "PREFLIGHT: $($p.preflight_READY) READY / $($p.preflight_NOT_READY) NOT_READY / $($p.preflight_missing) missing"
        Write-Host "MAY DAYS: $($p.completed_days.Count) completed / $($p.running_days.Count) running / $($p.pending_days.Count) pending / $($p.failed_days.Count) failed"
        Write-Host "CASE STATUS: B0=$($p.case_status.B0) B1=$($p.case_status.B1) B2=$($p.case_status.B2) B3=$($p.case_status.B3)"
        Write-Host "Running: $($p.running_days -join ', ')"
        Write-Host "Worker PIDs: $($p.worker_PIDs -join ', ')"
        foreach ($workerPid in @($p.worker_PIDs)) {
            $proc = Get-Process -Id $workerPid -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                Write-Host "PID $workerPid CPU=$([math]::Round($proc.CPU,1))s RAM=$([math]::Round($proc.WorkingSet64/1MB,0))MB"
            }
        }
        Write-Host "Latest completed: $($p.latest_completed_day)"
        Write-Host "Latest blocker: $($p.exact_current_blocker)"
        Write-Host "Temporal-only days: $($p.temporal_only_days)"
        Write-Host "Migration-escalated days: $($p.migration_escalated_days)"
        Write-Host "Frozen-DA migrations: $($p.total_migrations_from_frozen_DA)"
        Write-Host "Actual reoptimization: temporal=$($p.Actual_temporal_reoptimization_calls) AIDC=$($p.Actual_AIDC_reoptimization_calls) migration=$($p.Actual_migration_reoptimization_calls) WAN=$($p.Actual_WAN_reroute_calls)"
        Write-Host "Fresh: PASS=$($p.Fresh_PASS) restoration=$($p.Fresh_restoration) FAIL=$($p.Fresh_FAIL)"
        Write-Host "Progress: $($p.overall_progress_percent)%"
        Write-Host "ETA seconds: $($p.estimated_remaining_seconds)"
        Write-Host "Last update: $($p.last_update)"
        if (Test-Path -LiteralPath $logPath) {
            Write-Host ""
            Write-Host "Recent log:"
            Get-Content -LiteralPath $logPath -Tail 12
        }
        if ($p.phase -eq "COMPLETE") {
            Write-Host ""
            Write-Host "Campaign workflow complete. This monitor remains open."
            break
        }
    }
    catch {
        Write-Host "Progress read retry: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 10
}
