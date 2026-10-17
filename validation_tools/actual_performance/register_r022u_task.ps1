$ErrorActionPreference = 'Stop'
$r022uName = 'MobileESS_V44_Campaign004_Recovery_R022U'
$r022uArgs = '-X utf8 -u -m v44_recovery_r022u.operations --handover'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R022'
if ($oldTask.Settings.Enabled) { throw 'R022_TASK_MUST_BE_DISABLED_FIRST' }
if (Get-ScheduledTask -TaskName $r022uName -ErrorAction SilentlyContinue) { throw 'R022U_TASK_ALREADY_EXISTS' }
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument $r022uArgs -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r022uName -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Unconditional r022 Phase I improvement for every unstarted B1 A1 and B3 A2. No pilot PASS gate. Protect current r022 May02 B3 worker and all PASS; natural terminal boundary only.' | Out-Null
Enable-ScheduledTask -TaskName $r022uName | Out-Null
$registered = Get-ScheduledTask -TaskName $r022uName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r022uArgs) { throw 'R022U_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Arguments=$registered.Actions[0].Arguments; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R022U_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R022U_WINDOWS_TASK.json'
