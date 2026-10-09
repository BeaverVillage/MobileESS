param([ValidateSet('baseline','final')][string]$Phase='baseline')
$ErrorActionPreference='Stop'
$repo='D:\MobileESS_v42'
$run=Join-Path $repo 'runtime\v42_may_campaign\native90_build_reuse_20261009_01'
$docs='D:\MobileESS_v42_B3_prep\docs\v42_b3_implementation_completion_20261009'
if ([IO.Path]::GetFullPath($PSScriptRoot) -ne [IO.Path]::GetFullPath($docs)) {throw 'B3_DOCS_OUTPUT_ISOLATION_REQUIRED'}
function SmallJson($path) {if(Test-Path -LiteralPath $path){if((Get-Item -LiteralPath $path).Length -gt 1000000){throw 'BOUNDED_METADATA_READ_REQUIRED'};Get-Content -LiteralPath $path -Raw | ConvertFrom-Json}}
function Evidence($path) {
 if(-not(Test-Path -LiteralPath $path -PathType Leaf)){return [pscustomobject]@{path=$path;exists=$false}}
 $i=Get-Item -LiteralPath $path
 [pscustomobject]@{path=$path;exists=$true;bytes=$i.Length;modified_utc=$i.LastWriteTimeUtc.ToString('o');sha256=$(if($i.Length -le 1000000){(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null});content_hash_deferred=($i.Length -gt 1000000)}
}
$manifest=SmallJson (Join-Path $run 'CONTINUATION_V6_MANIFEST.json')
$source=@($manifest.sources.PSObject.Properties|ForEach-Object{$p=[IO.Path]::GetFullPath((Join-Path $repo $_.Name));if(-not $p.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'SOURCE_PATH_ESCAPE'};[pscustomobject]@{relative_path=$_.Name;evidence=(Evidence $p)}})
$stable=@('CAMPAIGN_MANIFEST.json','CONTINUATION_V5_MANIFEST.json','CONTINUATION_V6_MANIFEST.json','HOLD.json','HOLD_V5.json','WINDOWS_TASK_REGISTRATION_V6.json')|ForEach-Object{Evidence (Join-Path $run $_)}
$stable+=Evidence (Join-Path $env:USERPROFILE '.codex\automations\v42-may-b1-b2-hourly-recovery\automation.toml')
$mutable=@('ACTIVES_V6.json','COORDINATOR_HEARTBEAT.json','COORDINATOR_V6_HOST.json','WATCHDOG_V6_HOST.json','WATCHDOG_STATUS.json','CHECKPOINT_V6.json','CHECKPOINT_V5.json','CHECKPOINT.json','hourly_maintenance\SESSION_HEARTBEAT.json')|ForEach-Object{Evidence (Join-Path $run $_)}
$actives=SmallJson (Join-Path $run 'ACTIVES_V6.json')
$workers=@($actives.workers.PSObject.Properties|ForEach-Object{$r=SmallJson $_.Value.request;$a=Split-Path -Parent $_.Value.request;[pscustomobject]@{active=$_.Value;request=$r;heartbeat=(SmallJson (Join-Path $a 'HEARTBEAT.json'));native_ledger=(SmallJson (Join-Path $a 'NATIVE_RUNTIME_LEDGER.json'));ledger_evidence=(Evidence (Join-Path $a 'NATIVE_RUNTIME_LEDGER.json'))}})
$pids=@(Get-CimInstance Win32_Process|Where-Object{$_.Name -match '^python(w)?\.exe$|gurobi|OpenDSS' -and $_.CommandLine -match 'native90_build_reuse_20261009_01'}|ForEach-Object{[pscustomobject]@{PID=$_.ProcessId;parent_PID=$_.ParentProcessId;name=$_.Name;creation=$_.CreationDate.ToUniversalTime().ToString('o');command=($_.CommandLine-replace '(--token\s+)\S+','$1[REDACTED]')}})
$tasks=@(Get-ScheduledTask|Where-Object{$_.TaskName-like 'MobileESS_V42_B1B2_P1_native90_build_reuse_20261009_01*'}|Sort-Object TaskName|ForEach-Object{[pscustomobject]@{name=$_.TaskName;path=$_.TaskPath;state=[string]$_.State;actions=@($_.Actions|ForEach-Object{[pscustomobject]@{execute=$_.Execute;arguments=$_.Arguments;working_directory=$_.WorkingDirectory}});triggers=@($_.Triggers|ForEach-Object{[pscustomobject]@{enabled=$_.Enabled;start=$_.StartBoundary;interval=$_.Repetition.Interval;duration=$_.Repetition.Duration}});settings=[pscustomobject]@{multiple_instances=$_.Settings.MultipleInstances;execution_time_limit=$_.Settings.ExecutionTimeLimit;priority=$_.Settings.Priority}}})
$snapshot=[pscustomobject]@{schema='B3_IMPLEMENTATION_RESOURCE_SNAPSHOT_V1';captured_utc=[DateTime]::UtcNow.ToString('o');head=(& git -C $repo rev-parse HEAD);branch=(& git -C $repo branch --show-current);existing_tracked_changes=@(& git -C $repo diff --name-only);run_id=$manifest.run_id;manifest_source_head=$manifest.source_HEAD;implementation_source_sha=$manifest.implementation.source_SHA;policy=$manifest.policy;workers=$workers;live_processes=$pids;source_files=$source;stable_files=$stable;runtime_files=$mutable;tasks=$tasks;notes=@('V6 source and live process changes since preparation occurred externally before this follow-up; previous preparation audit is preserved.','Read-only bounded metadata/source hashes; no large input data, source modules, solver/model/engine were loaded.','Runtime owner changes are observed separately; this audit does not identify exclusive writers.');campaign_write_calls=0;process_or_scheduler_mutation_calls=0;native_or_OpenDSS_or_model_calls=0}
$baseline=Join-Path $docs 'B3_RESOURCE_ISOLATION_BASELINE.json'
$audit=Join-Path $docs 'B3_RESOURCE_ISOLATION_AUDIT.json'
if($Phase-eq 'baseline'){if(Test-Path -LiteralPath $baseline){throw 'BASELINE_OVERWRITE_FORBIDDEN'};$snapshot|ConvertTo-Json -Depth 22|Set-Content -LiteralPath $baseline -Encoding utf8;[pscustomobject]@{status='BASELINE_CAPTURED_FINAL_PENDING';baseline=$snapshot;final=$null}|ConvertTo-Json -Depth 24|Set-Content -LiteralPath $audit -Encoding utf8;[pscustomobject]@{phase=$Phase;source_count=$source.Count;head=$snapshot.head;live_pids=@($pids.PID);workers=$workers.Count}|ConvertTo-Json -Compress;exit}
$before=SmallJson $baseline
function Changes($old,$new,$key){@($old|ForEach-Object{$a=$_;$b=$new|Where-Object{$_.$key-eq $a.$key}|Select-Object -First 1;$ae=if($a.evidence){$a.evidence}else{$a};$be=if($b.evidence){$b.evidence}else{$b};if($ae.sha256-ne $be.sha256 -or $ae.exists-ne $be.exists -or $ae.bytes-ne $be.bytes){[pscustomobject]@{key=$a.$key;before=$ae;after=$be}}})}
$sourceChanges=Changes $before.source_files $source 'relative_path'
$stableChanges=Changes $before.stable_files $stable 'path'
$runtimeChanges=Changes $before.runtime_files $mutable 'path'
$taskBefore=@($before.tasks|Select-Object name,path,actions,triggers,settings)|ConvertTo-Json -Depth 8 -Compress
$taskAfter=@($tasks|Select-Object name,path,actions,triggers,settings)|ConvertTo-Json -Depth 8 -Compress
$result=[pscustomobject]@{status='READ_ONLY_COMPARISON_COMPLETED';baseline=$before;final=$snapshot;comparison=[pscustomobject]@{head_unchanged=($before.head-eq $snapshot.head);branch_unchanged=($before.branch-eq $snapshot.branch);source_hash_changes=$sourceChanges;stable_hash_changes=$stableChanges;task_definitions_unchanged=($taskBefore-eq $taskAfter);runtime_hash_or_size_changes=$runtimeChanges;source_status_changes=@(Compare-Object @($before.existing_tracked_changes) @($snapshot.existing_tracked_changes));exclusive_writer_attribution='NOT_CLAIMED';campaign_write_calls_by_this_work=0}}
$result|ConvertTo-Json -Depth 24|Set-Content -LiteralPath $audit -Encoding utf8
[pscustomobject]@{phase=$Phase;source_changes=$sourceChanges.Count;stable_changes=$stableChanges.Count;runtime_changes=$runtimeChanges.Count;tasks_unchanged=$result.comparison.task_definitions_unchanged;head_unchanged=$result.comparison.head_unchanged;live_pids=@($pids.PID)}|ConvertTo-Json -Compress
