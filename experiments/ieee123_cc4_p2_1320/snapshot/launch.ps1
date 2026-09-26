$ErrorActionPreference='Stop'
$ablationRoot=$PSScriptRoot
$ablationPrior=$null
if(Test-Path -LiteralPath (Join-Path $ablationRoot 'LAUNCH.json')){$ablationPrior=Get-Content -Raw -LiteralPath (Join-Path $ablationRoot 'LAUNCH.json') | ConvertFrom-Json}
if($ablationPrior -and (Get-Process -Id $ablationPrior.supervisor_pid -ErrorAction SilentlyContinue)){throw 'Supervisor already running'}
$ablationPython='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe'
@{git_executable=(Get-Command git -ErrorAction Stop).Source;python_executable=$ablationPython} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ablationRoot 'RUNTIME_EXECUTABLES.json') -Encoding UTF8
& $ablationPython -B (Join-Path $ablationRoot 'campaign.py') --pin
if($LASTEXITCODE -ne 0){throw 'Source pin failed'}
$ablationStartup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}
$ablationCommand='"'+$ablationPython+'" -B -u "'+(Join-Path $ablationRoot 'campaign.py')+'"'
$ablationCreated=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$ablationCommand;CurrentDirectory=$ablationRoot;ProcessStartupInformation=$ablationStartup}
if($ablationCreated.ReturnValue -ne 0){throw 'Detached supervisor launch failed'}
$ablationMonitorStartup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]1;CreateFlags=[uint32]16}
$ablationMonitorCommand='powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "'+(Join-Path $ablationRoot 'monitor.ps1')+'"'
if($ablationPrior -and (Get-Process -Id $ablationPrior.monitor_pid -ErrorAction SilentlyContinue)){$ablationMonitor=@{ReturnValue=0;ProcessId=$ablationPrior.monitor_pid}}else{$ablationMonitor=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$ablationMonitorCommand;CurrentDirectory=$ablationRoot;ProcessStartupInformation=$ablationMonitorStartup}}
if($ablationMonitor.ReturnValue -ne 0){throw 'Monitor launch failed'}
@{supervisor_pid=$ablationCreated.ProcessId;monitor_pid=$ablationMonitor.ProcessId;mechanism='WMI Win32_Process.Create; detached supervisor; separate visible monitor console';launched_at=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ablationRoot 'LAUNCH.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $ablationRoot 'LAUNCH.json')
