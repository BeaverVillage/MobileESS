$ErrorActionPreference = 'Stop'
$r025Name = 'MobileESS_V44_Campaign004_Recovery_R025'
$r025Args = '-X utf8 -u -m v44_recovery_r025.operations --handover'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R024A'
if ($oldTask.Settings.Enabled) { throw 'R024A_TASK_MUST_BE_DISABLED' }
if (Get-ScheduledTask -TaskName $r025Name -ErrorAction SilentlyContinue) { throw 'R025_TASK_ALREADY_EXISTS' }
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument $r025Args -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r025Name -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'r025 all B1/B3 A1/A2 Native3600 PhaseI400 then original integer feasible UB freeze, current A2 clock continued and all prior PASS preserved.' | Out-Null
Enable-ScheduledTask -TaskName $r025Name | Out-Null
$task=Get-ScheduledTask -TaskName $r025Name
[pscustomobject]@{Task=$task.TaskName;State=$task.State.ToString();Enabled=$task.Settings.Enabled;Arguments=$task.Actions[0].Arguments;ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R025_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R025_WINDOWS_TASK.json'
