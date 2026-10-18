$ErrorActionPreference = 'Stop'
$taskName = 'MobileESS_V44_Campaign004_Recovery_R032'
$taskPython = 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$taskRoot = 'D:\v44_r022_rowgen_20261017'
$action = New-ScheduledTaskAction -Execute $taskPython -WorkingDirectory $taskRoot -Argument '-X utf8 -u -m v44_recovery_r032.operations --watchdog --algorithm v44_recovery_r029.operations'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Trigger $trigger -Description 'Fix fixed-M1 A2 CC4 day; resume May02 B3 from completed tight M1 with new A2 then M2. Retain next-date P1 improvement and all exact checks.' -Force | Select-Object TaskName,State
Start-ScheduledTask -TaskName $taskName
