param(
    [ValidateSet('baseline', 'final')][string]$Phase = 'baseline'
)

# Read-only inspection of B1/B2. Every write is confined to this B3 docs folder.
# No campaign module is imported, no solver/native model is constructed, and no
# task/process/configuration mutation API is used.
$ErrorActionPreference = 'Stop'
$activeRepo = 'D:\MobileESS_v42'
$runRoot = Join-Path $activeRepo 'runtime\v42_may_campaign\native90_build_reuse_20261009_01'
$docsRoot = $PSScriptRoot
$expectedDocs = 'D:\MobileESS_v42_B3_prep\docs\v42_b3_preparation_20261009'
if ([IO.Path]::GetFullPath($docsRoot) -ne [IO.Path]::GetFullPath($expectedDocs)) {
    throw 'Resource audit output must stay in the independent B3 worktree.'
}
$baselinePath = Join-Path $docsRoot 'B3_RESOURCE_ISOLATION_BASELINE.json'
$auditPath = Join-Path $docsRoot 'B3_RESOURCE_ISOLATION_AUDIT.json'

function Read-SmallJson([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    if ((Get-Item -LiteralPath $Path).Length -gt 1000000) { throw "Metadata size guard: $Path" }
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Get-BoundedFileEvidence([string]$Path, [bool]$Hash = $true) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]@{ path=$Path; exists=$false; bytes=$null; sha256=$null }
    }
    $item = Get-Item -LiteralPath $Path
    $sha = $null
    if ($Hash -and $item.Length -le 1000000) { $sha = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    [pscustomobject]@{ path=$Path; exists=$true; bytes=$item.Length; last_write_utc=$item.LastWriteTimeUtc.ToString('o'); sha256=$sha; content_hash_deferred=($Hash -and $item.Length -gt 1000000) }
}

$manifest = Read-SmallJson (Join-Path $runRoot 'CONTINUATION_V5_MANIFEST.json')
$active = Read-SmallJson (Join-Path $runRoot 'ACTIVE_V5.json')
$requestPath = $active.request
$request = Read-SmallJson $requestPath
$attempt = Split-Path -Parent $requestPath
$heartbeat = Read-SmallJson (Join-Path $attempt 'HEARTBEAT.json')
$ledgerPath = Join-Path $attempt 'NATIVE_RUNTIME_LEDGER.json'
$ledger = Read-SmallJson $ledgerPath

$sourceEvidence = @($manifest.sources.PSObject.Properties | ForEach-Object {
    $path = [IO.Path]::GetFullPath((Join-Path $activeRepo $_.Name))
    if (-not $path.StartsWith(([IO.Path]::GetFullPath($activeRepo) + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest source escaped active repository.' }
    $evidence = Get-BoundedFileEvidence $path
    [pscustomobject]@{ relative_path=$_.Name; evidence=$evidence; manifest_sha256=$_.Value }
})
$stablePaths = @('CAMPAIGN_MANIFEST.json','CONTINUATION_V5_MANIFEST.json','HOLD.json','HOLD_V5.json','WINDOWS_TASK_REGISTRATION.json','WINDOWS_TASK_REGISTRATION_V5.json') | ForEach-Object { Join-Path $runRoot $_ }
$stablePaths += $requestPath
$automationPath = Join-Path $env:USERPROFILE '.codex\automations\v42-may-b1-b2-hourly-recovery\automation.toml'
$stablePaths += $automationPath
$stableEvidence = @($stablePaths | ForEach-Object { Get-BoundedFileEvidence $_ })
$mutablePaths = @('ACTIVE_V5.json','ACTIVES_V5.json','COORDINATOR_HEARTBEAT.json','WATCHDOG_HOST.json','WATCHDOG_V5_HOST.json','WATCHDOG_STATUS.json','CHECKPOINT_V5.json','CHECKPOINT.json') | ForEach-Object { Join-Path $runRoot $_ }
$mutablePaths += @($ledgerPath,(Join-Path $attempt 'HEARTBEAT.json'),(Join-Path $runRoot 'hourly_maintenance\SESSION_HEARTBEAT.json'))
$mutableEvidence = @($mutablePaths | ForEach-Object { Get-BoundedFileEvidence $_ })

$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$|gurobi|OpenDSS' -and $_.CommandLine -match 'native90_build_reuse_20261009_01'
} | ForEach-Object {
    [pscustomobject]@{ PID=$_.ProcessId; parent_PID=$_.ParentProcessId; name=$_.Name; creation=$_.CreationDate.ToUniversalTime().ToString('o'); command=($_.CommandLine -replace '(--token\s+)\S+', '$1[REDACTED]') }
})
$tasks = @(Get-ScheduledTask | Where-Object { $_.TaskName -like 'MobileESS_V42_B1B2_P1_native90_build_reuse_20261009_01*' } | Sort-Object TaskName | ForEach-Object {
    [pscustomobject]@{
        task_name=$_.TaskName; task_path=$_.TaskPath; state=[string]$_.State
        actions=@($_.Actions | ForEach-Object { [pscustomobject]@{execute=$_.Execute;arguments=$_.Arguments;working_directory=$_.WorkingDirectory} })
        triggers=@($_.Triggers | ForEach-Object { [pscustomobject]@{enabled=$_.Enabled;start_boundary=$_.StartBoundary;interval=$_.Repetition.Interval;duration=$_.Repetition.Duration} })
        settings=[pscustomobject]@{multiple_instances=$_.Settings.MultipleInstances;execution_time_limit=$_.Settings.ExecutionTimeLimit;allow_hard_terminate=$_.Settings.AllowHardTerminate;priority=$_.Settings.Priority}
    }
})
$automationText = Get-Content -LiteralPath $automationPath -Raw
$snapshot = [pscustomobject]@{
    schema='V42_B3_RESOURCE_ISOLATION_SNAPSHOT_V1'; captured_utc=[DateTime]::UtcNow.ToString('o'); captured_seoul=[DateTime]::UtcNow.AddHours(9).ToString('yyyy-MM-ddTHH:mm:ss') + '+09:00'
    active_repo=$activeRepo; run_root=$runRoot; git_head=(& git -C $activeRepo rev-parse HEAD); git_branch=(& git -C $activeRepo branch --show-current)
    run_id=$manifest.run_id; manifest_source_head=$manifest.source_HEAD; implementation_source_sha=$manifest.implementation.source_SHA; scientific_authority=$manifest.scientific_authority; policy=$manifest.policy
    recorded_active=$active; input_sha=$heartbeat.input_SHA; input_sha_basis='Existing worker heartbeat; original input data were not loaded or rewritten.'
    recorded_coordinator=(Read-SmallJson (Join-Path $runRoot 'COORDINATOR_V5_HOST.json')).process
    recorded_watchdog=(Read-SmallJson (Join-Path $runRoot 'WATCHDOG_V5_HOST.json')).process
    worker_heartbeat=$heartbeat; native_ledger=$ledger; native_ledger_path=$ledgerPath; live_processes=$processes; scheduled_tasks=$tasks
    hourly_automation=[pscustomobject]@{path=$automationPath;status=([regex]::Match($automationText,'(?m)^status\s*=\s*"([^"]+)"').Groups[1].Value);rrule=([regex]::Match($automationText,'(?m)^rrule\s*=\s*"([^"]+)"').Groups[1].Value)}
    stable_files=$stableEvidence; source_files=$sourceEvidence; mutable_runtime_files=$mutableEvidence
    observations=@('V5 recorded Coordinator 97144 and Worker 96616 were absent from live process enumeration at the initial audit; pre-existing HOLD_V5 was present. No repair, restart, HOLD modification, or scheduler mutation was attempted.', 'A watchdog task may start and exit between snapshots; a recorded host PID is not proof of a currently live process.', 'Running ledgers and checkpoints may change through their existing owners. A changed hash alone does not identify the writer; causal attribution is not claimed.')
    audit_actions=[pscustomobject]@{native_optimize_calls=0;OpenDSS_calls=0;FULL_model_builds=0;process_start_stop_restart_calls=0;scheduler_mutation_calls=0;campaign_write_calls=0;original_input_load_calls=0}
}
if ($Phase -eq 'baseline') {
    if (Test-Path -LiteralPath $baselinePath) { throw 'Baseline already exists; refusing to replace historical evidence.' }
    $snapshot | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $baselinePath -Encoding utf8
    [pscustomobject]@{schema='V42_B3_RESOURCE_ISOLATION_AUDIT_V1';status='BASELINE_CAPTURED_FINAL_COMPARISON_PENDING';baseline=$snapshot;final=$null;limitations=$snapshot.observations} | ConvertTo-Json -Depth 22 | Set-Content -LiteralPath $auditPath -Encoding utf8
    [pscustomobject]@{phase=$Phase;path=$auditPath;head=$snapshot.git_head;source_files=$sourceEvidence.Count;live_pids=@($processes.PID)} | ConvertTo-Json -Compress
    exit
}
$baseline = Read-SmallJson $baselinePath
$sourceChanges = @($baseline.source_files | ForEach-Object {
    $before = $_
    $after = $snapshot.source_files | Where-Object { $_.relative_path -eq $before.relative_path } | Select-Object -First 1
    if ($before.evidence.sha256 -ne $after.evidence.sha256 -or $before.evidence.exists -ne $after.evidence.exists) { [pscustomobject]@{relative_path=$before.relative_path;before=$before.evidence;after=$after.evidence} }
})
$stableChanges = @($baseline.stable_files | ForEach-Object {
    $before = $_
    $after = $snapshot.stable_files | Where-Object { $_.path -eq $before.path } | Select-Object -First 1
    if ($before.sha256 -ne $after.sha256 -or $before.exists -ne $after.exists) { [pscustomobject]@{path=$before.path;before=$before;after=$after} }
})
$runtimeChanges = @($baseline.mutable_runtime_files | ForEach-Object {
    $before = $_
    $after = $snapshot.mutable_runtime_files | Where-Object { $_.path -eq $before.path } | Select-Object -First 1
    # ConvertFrom-Json may deserialize ISO strings as DateTime. Compare UTC ticks
    # to avoid treating equivalent string/DateTime representations as changes.
    $beforeWriteTicks = if ($before.last_write_utc) { ([DateTimeOffset]$before.last_write_utc).UtcTicks } else { $null }
    $afterWriteTicks = if ($after.last_write_utc) { ([DateTimeOffset]$after.last_write_utc).UtcTicks } else { $null }
    if ($before.sha256 -ne $after.sha256 -or $before.bytes -ne $after.bytes -or $beforeWriteTicks -ne $afterWriteTicks -or $before.exists -ne $after.exists) { [pscustomobject]@{path=$before.path;before=$before;after=$after;classification='OWNER_MANAGED_RUNTIME_CHANGE_WRITER_NOT_ATTRIBUTED'} }
})
$beforeTaskDefinitions = @($baseline.scheduled_tasks | Select-Object task_name,task_path,actions,triggers,settings) | ConvertTo-Json -Depth 8 -Compress
$afterTaskDefinitions = @($snapshot.scheduled_tasks | Select-Object task_name,task_path,actions,triggers,settings) | ConvertTo-Json -Depth 8 -Compress
$comparison = [pscustomobject]@{original_head_unchanged=($baseline.git_head -eq $snapshot.git_head);original_branch_unchanged=($baseline.git_branch -eq $snapshot.git_branch);source_hash_changes=$sourceChanges;stable_file_hash_changes=$stableChanges;scheduled_task_definitions_unchanged=($beforeTaskDefinitions -eq $afterTaskDefinitions);runtime_observation_changes=$runtimeChanges;campaign_write_calls_by_this_task=0;exclusive_writer_attribution='NOT_CLAIMED';running_ledger_hash_immutability='NOT_REQUIRED_RUNTIME_OWNER_MAY_UPDATE'}
$result = [pscustomobject]@{schema='V42_B3_RESOURCE_ISOLATION_AUDIT_V1';status='READ_ONLY_COMPARISON_COMPLETED';baseline=$baseline;final=$snapshot;comparison=$comparison;limitations=$snapshot.observations}
$result | ConvertTo-Json -Depth 24 | Set-Content -LiteralPath $auditPath -Encoding utf8
[pscustomobject]@{phase=$Phase;path=$auditPath;source_hash_changes=$sourceChanges.Count;stable_changes=$stableChanges.Count;task_definitions_unchanged=$comparison.scheduled_task_definitions_unchanged;runtime_changes=$runtimeChanges.Count;live_pids=@($processes.PID)} | ConvertTo-Json -Compress
