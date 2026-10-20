$ErrorActionPreference = 'Stop'
$taskName = 'MobileESS_V44_Campaign004_Recovery_R030'
$taskPython = 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$taskRoot = 'D:\v44_r022_rowgen_20261017'
$action = New-ScheduledTaskAction -Execute $taskPython -WorkingDirectory $taskRoot -Argument '-X utf8 -u -m v44_recovery_r030.operations --watchdog --algorithm v44_recovery_r029.operations'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Trigger $trigger -Description 'B3 M1 voltage 0.955..1.045 pu all future dates; new May02 M1 A2 M2; sealed r029 P1 and Actual improvements.' -Force | Select-Object TaskName, State
Start-ScheduledTask -TaskName $taskName
