$ErrorActionPreference = 'Stop'
$r024aName = 'MobileESS_V44_Campaign004_Recovery_R024A'
$r024aArgs = '-X utf8 -u -m v44_recovery_r024a.operations --handover'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R024'
if ($oldTask.Settings.Enabled) { throw 'R024_TASK_MUST_BE_DISABLED' }
if (Get-ScheduledTask -TaskName $r024aName -ErrorAction SilentlyContinue) { throw 'R024A_TASK_ALREADY_EXISTS' }
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument $r024aArgs -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r024aName -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'r024a Phase I Adaptive Multi-Column Pricing. User-authorized May02 B3 A2 Native0 fresh restart; all unstarted B1 B3 A stages unconditional, exact proofs and all prior PASS preserved.' | Out-Null
Enable-ScheduledTask -TaskName $r024aName | Out-Null
$task=Get-ScheduledTask -TaskName $r024aName
[pscustomobject]@{Task=$task.TaskName;State=$task.State.ToString();Enabled=$task.Settings.Enabled;Arguments=$task.Actions[0].Arguments;ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R024A_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R024A_WINDOWS_TASK.json'
