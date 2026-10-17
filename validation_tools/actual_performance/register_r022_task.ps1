$ErrorActionPreference = 'Stop'
$r022TaskName = 'MobileESS_V44_Campaign004_Recovery_R022'
$r022Root = 'D:/v44_r022_rowgen_20261017'
$r022Arguments = '-X utf8 -u -m v44_recovery_r022.operations --handover'
$r022Python = 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R021'
if ($oldTask.Settings.Enabled) { throw 'R021_TASK_MUST_BE_DISABLED_FIRST' }
if (Get-ScheduledTask -TaskName $r022TaskName -ErrorAction SilentlyContinue) { throw 'R022_TASK_ALREADY_EXISTS' }
$r022Action = New-ScheduledTaskAction -Execute $r022Python -Argument $r022Arguments -WorkingDirectory $r022Root
Register-ScheduledTask -TaskName $r022TaskName -Action $r022Action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Sealed r022: May02 B3 A2 fresh Native0 from completed M1; certified adaptive active rows, full Phi1e-8, original residual1e-6, semantic remapping, exact fast attribution; B1 A1 and B3 A2 future rollout after pilot PASS.' | Out-Null
Enable-ScheduledTask -TaskName $r022TaskName | Out-Null
$registered = Get-ScheduledTask -TaskName $r022TaskName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r022Arguments) { throw 'R022_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Execute=$registered.Actions[0].Execute; Arguments=$registered.Actions[0].Arguments; WorkingDirectory=$registered.Actions[0].WorkingDirectory; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R022_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R022_WINDOWS_TASK.json'
