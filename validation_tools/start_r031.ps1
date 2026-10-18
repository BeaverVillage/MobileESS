$ErrorActionPreference = 'Stop'
$taskName = 'MobileESS_V44_Campaign004_Recovery_R031'
$taskPython = 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$taskRoot = 'D:\v44_r022_rowgen_20261017'
$action = New-ScheduledTaskAction -Execute $taskPython -WorkingDirectory $taskRoot -Argument '-X utf8 -u -m v44_recovery_r031.operations --handover --algorithm v44_recovery_r029.operations'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Trigger $trigger -Description 'Finish running May03 B1, then apply bounded repeat-class P1 improvement to B3 A2 May03 onward. Retain r030 M1 voltage and all exact checks.' -Force | Select-Object TaskName, State
Disable-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R030' | Select-Object TaskName, State
Start-ScheduledTask -TaskName $taskName
