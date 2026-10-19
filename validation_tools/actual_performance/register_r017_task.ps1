$ErrorActionPreference = 'Stop'
$r017TaskName = 'MobileESS_V44_Campaign004_Recovery_R017'
$r017Root = 'D:/v44_may01_07_prepare_20261016'
$r017Arguments = '-X utf8 -u -m v44_recovery_r017.operations --handover'
$r017Python = 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R016'
if ($oldTask.Settings.Enabled) { throw 'R016_TASK_MUST_BE_DISABLED_FIRST' }
$existing = Get-ScheduledTask -TaskName $r017TaskName -ErrorAction SilentlyContinue
if ($existing) { throw 'R017_TASK_ALREADY_EXISTS_INSPECT_BEFORE_REPLACING' }
$r017Action = New-ScheduledTaskAction -Execute $r017Python -Argument $r017Arguments -WorkingDirectory $r017Root
Register-ScheduledTask -TaskName $r017TaskName -Action $r017Action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Sealed r017: wait for May01 B3 entire Actual and independent Fresh and natural worker/coordinator exits, then single supervised campaign worker. B0/B1/B3 exact historical audit optimization.' | Out-Null
Enable-ScheduledTask -TaskName $r017TaskName | Out-Null
$registered = Get-ScheduledTask -TaskName $r017TaskName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r017Arguments) { throw 'R017_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Execute=$registered.Actions[0].Execute; Arguments=$registered.Actions[0].Arguments; WorkingDirectory=$registered.Actions[0].WorkingDirectory; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R017_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R017_WINDOWS_TASK.json'
