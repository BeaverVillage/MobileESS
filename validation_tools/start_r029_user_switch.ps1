$ErrorActionPreference = 'Stop'
$taskName = 'MobileESS_V44_Campaign004_Recovery_R029_UserSwitch'
$taskPython = 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$taskRoot = 'D:\v44_r022_rowgen_20261017'
$action = New-ScheduledTaskAction -Execute $taskPython -WorkingDirectory $taskRoot -Argument '-X utf8 -u -m v44_recovery_r029_switch.operations --watchdog --algorithm v44_recovery_r029.operations'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Trigger $trigger -Description 'User-directed r029 campaign: May02 B3 fresh A2 first; May07 B1 validated A1 checkpoint then fresh Actual.' -Force | Select-Object TaskName, State
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime, LastTaskResult
