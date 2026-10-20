$ErrorActionPreference = 'Stop'
$r024bName = 'MobileESS_V44_Campaign004_Recovery_R024B'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R025B'
Disable-ScheduledTask -TaskName $oldTask.TaskName | Out-Null
if (Get-ScheduledTask -TaskName $r024bName -ErrorAction SilentlyContinue) { throw 'R024B_TASK_ALREADY_EXISTS' }
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 -u -m v44_recovery_r024b.operations --handover' -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r024bName -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Restore r024a/r024 algorithm with A Native5400, no separate PhaseI cutoff, original P1/full-gap acceptance; May02 B3 A2 verified active-row checkpoint and all prior Native costs continued.' | Out-Null
Enable-ScheduledTask -TaskName $r024bName | Out-Null
$task=Get-ScheduledTask -TaskName $r024bName
[pscustomobject]@{Task=$task.TaskName;State=$task.State.ToString();Enabled=$task.Settings.Enabled;Arguments=$task.Actions[0].Arguments;ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R024B_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R024B_WINDOWS_TASK.json'
