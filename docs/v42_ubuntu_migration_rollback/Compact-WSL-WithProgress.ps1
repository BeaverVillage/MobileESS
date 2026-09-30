param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
trap {
    $failureDirectory = Split-Path -Parent $ConfigPath
    [pscustomobject]@{PASS=$false;stage='guard or launch';error=$_.Exception.Message;method='DiskPart';percentage_not_fabricated=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $failureDirectory 'WSL_VHD_COMPACTION_RECEIPT.json') -Encoding UTF8
    exit 1
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$configuration = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$outputDirectory = Split-Path -Parent $ConfigPath
$progressPath = Join-Path $outputDirectory 'COMPACTION_PROGRESS.json'
$receiptPath = Join-Path $outputDirectory 'WSL_VHD_COMPACTION_RECEIPT.json'
$stdoutPath = Join-Path $outputDirectory 'DISKPART_COMPACTION.log'
$registry = @(Get-ChildItem -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' | ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath } | Where-Object { $_.DistributionName -eq 'Ubuntu-MobileESS-D' })
if ($registry.Count -ne 1) { throw 'Exact distro registry entry required' }
$registryBase = $registry[0].BasePath
if ($registryBase.StartsWith('\\?\')) { $registryBase = $registryBase.Substring(4) }
$verifiedVhd = [IO.Path]::GetFullPath((Join-Path $registryBase 'ext4.vhdx'))
if ($verifiedVhd -ne [IO.Path]::GetFullPath($configuration.verified_vhd_path)) { throw 'VHD path differs from verified distro registry' }
if ($verifiedVhd -ne 'D:\WSL\Ubuntu-MobileESS-D\ext4.vhdx') { throw 'Unexpected VHD target' }
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator rights are required by DiskPart' }
$running = ((wsl.exe --list --running --quiet | Out-String) -replace "`0",'').Trim()
if ($running) { throw 'WSL must be fully shut down before compaction' }
$exclusive = [IO.File]::Open($verifiedVhd,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
$exclusive.Dispose()
$beforeLength = (Get-Item -LiteralPath $verifiedVhd).Length
$diskpartScript = Join-Path $outputDirectory 'COMPACT_VERIFIED_VHD.diskpart.txt'
@("select vdisk file=`"$verifiedVhd`"",'detail vdisk','compact vdisk','exit') | Set-Content -LiteralPath $diskpartScript -Encoding ASCII
$form = New-Object Windows.Forms.Form
$form.Text = 'WSL 압축 — 실제 진행률'
$form.Size = New-Object Drawing.Size(620,265)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.MaximizeBox = $false
$title = New-Object Windows.Forms.Label
$title.Location = New-Object Drawing.Point(24,20)
$title.Size = New-Object Drawing.Size(565,30)
$title.Font = New-Object Drawing.Font('Segoe UI',14)
$title.Text = 'Ubuntu-MobileESS-D 압축'
$percent = New-Object Windows.Forms.Label
$percent.Location = New-Object Drawing.Point(24,58)
$percent.Size = New-Object Drawing.Size(565,48)
$percent.Font = New-Object Drawing.Font('Segoe UI',25,[Drawing.FontStyle]::Bold)
$percent.Text = '진행률을 기다리는 중'
$bar = New-Object Windows.Forms.ProgressBar
$bar.Location = New-Object Drawing.Point(24,117)
$bar.Size = New-Object Drawing.Size(550,25)
$bar.Style = 'Marquee'
$details = New-Object Windows.Forms.Label
$details.Location = New-Object Drawing.Point(24,154)
$details.Size = New-Object Drawing.Size(565,50)
$details.Font = New-Object Drawing.Font('Segoe UI',10)
$details.Text = 'DiskPart가 제공하는 실제 퍼센트를 표시합니다.'
$form.Controls.AddRange(@($title,$percent,$bar,$details))
$process = New-Object Diagnostics.Process
$process.StartInfo.FileName = Join-Path $env:SystemRoot 'System32\diskpart.exe'
$process.StartInfo.Arguments = '/s "' + $diskpartScript + '"'
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.CreateNoWindow = $true
$process.StartInfo.RedirectStandardOutput = $true
$process.StartInfo.RedirectStandardError = $true
$process.StartInfo.StandardOutputEncoding = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
$process.StartInfo.StandardErrorEncoding = $process.StartInfo.StandardOutputEncoding
$script:buffer = New-Object byte[] 4096
$script:characters = New-Object char[] 8192
$script:decoder = $null
$script:output = New-Object Text.StringBuilder
$script:lastPercentage = $null
$script:finished = $false
$script:started = Get-Date
$script:percentEvents = New-Object Collections.Generic.List[object]
$script:readTask = $null
$script:errorTask = $null
$script:eof = $false
function Save-Progress([string]$status) {
    [pscustomobject]@{status=$status;percentage=$script:lastPercentage;actual_percentage_source='DiskPart stdout';elapsed_seconds=((Get-Date)-$script:started).TotalSeconds;verified_vhd_path=$verifiedVhd;pid=$process.Id;updated=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $progressPath -Encoding UTF8
}
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 100
$timer.Add_Tick({
    try {
        if ($script:readTask -and $script:readTask.IsCompleted) {
            $count = $script:readTask.Result
            if ($count -gt 0) {
                if (-not $script:decoder) {
                    $encoding = $process.StartInfo.StandardOutputEncoding
                    if (($count -ge 2 -and $script:buffer[0] -eq 255 -and $script:buffer[1] -eq 254) -or ($count -ge 4 -and $script:buffer[1] -eq 0 -and $script:buffer[3] -eq 0)) { $encoding = [Text.Encoding]::Unicode }
                    if ($count -ge 3 -and $script:buffer[0] -eq 239 -and $script:buffer[1] -eq 187 -and $script:buffer[2] -eq 191) { $encoding = [Text.Encoding]::UTF8 }
                    $script:decoder = $encoding.GetDecoder()
                }
                $characterCount = $script:decoder.GetChars($script:buffer,0,$count,$script:characters,0,$false)
                $chunk = [string]::new($script:characters,0,$characterCount).Replace([string][char]0,'')
                [void]$script:output.Append($chunk)
                [IO.File]::AppendAllText($stdoutPath,$chunk,[Text.Encoding]::UTF8)
                $matches = [regex]::Matches($script:output.ToString(),'(?i)(\d{1,3})\s*(?:퍼센트|percent|%)')
                if ($matches.Count -gt 0) {
                    $match = $matches[$matches.Count-1]
                    $value = [int]$match.Groups[1].Value
                    if ($value -ge 0 -and $value -le 100 -and $value -ne $script:lastPercentage) {
                        $script:lastPercentage = $value
                        $bar.Style = 'Continuous';$bar.Value = $value;$percent.Text = "$value%"
                        $script:percentEvents.Add([pscustomobject]@{percentage=$value;elapsed_seconds=((Get-Date)-$script:started).TotalSeconds})
                        Save-Progress 'COMPACTING'
                    }
                }
                $script:readTask = $process.StandardOutput.BaseStream.ReadAsync($script:buffer,0,$script:buffer.Length)
            } else { $script:eof = $true;$script:readTask = $null }
        }
        $elapsed = (Get-Date)-$script:started
        $details.Text = ('경과 {0:mm\:ss} · 실제 DiskPart 진행률' -f $elapsed)
        if ($process.HasExited -and $script:eof) {
            $timer.Stop();$stderr = $script:errorTask.Result
            if ($stderr) { [IO.File]::AppendAllText($stdoutPath,$stderr,[Text.Encoding]::UTF8) }
            $allText = $script:output.ToString() + $stderr
            $success = $process.ExitCode -eq 0 -and $script:lastPercentage -eq 100 -and $allText -notmatch '(?i)error|오류|실패|failed'
            $afterLength = (Get-Item -LiteralPath $verifiedVhd).Length
            $script:finished = $true
            [pscustomobject]@{PASS=$success;method='DiskPart compact vdisk, detached verified dynamic VHD';verified_vhd_path=$verifiedVhd;WSL_stopped_verified=$true;registry_match_verified=$true;exit_code=$process.ExitCode;actual_final_percentage=$script:lastPercentage;percentage_events=$script:percentEvents;wall_seconds=$elapsed.TotalSeconds;VHDX_file_length_before=$beforeLength;VHDX_file_length_after=$afterLength;VHDX_file_length_recovered=$beforeLength-$afterLength;log='DISKPART_COMPACTION.log';preexisting_distro_deleted=$false;official_conditions='https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact-vdisk'} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
            Save-Progress $(if ($success) {'COMPLETE'} else {'FAILED'})
            if ($success) { $percent.Text = '100% · 완료';$details.Text = ('VHDX 파일 길이 감소: {0:N2} GiB' -f (($beforeLength-$afterLength)/1GB)) }
            else { $percent.Text = '로그 확인 필요';$details.Text = '압축 상태를 기록했습니다. 자동으로 다른 디스크를 조작하지 않습니다.' }
            $closeTimer = New-Object Windows.Forms.Timer;$closeTimer.Interval=5000
            $closeTimer.Add_Tick({$closeTimer.Stop();$form.Close()}.GetNewClosure());$closeTimer.Start();$script:closeTimer=$closeTimer
        }
    } catch {
        $timer.Stop();$script:finished=$true
        [pscustomobject]@{PASS=$false;error=$_.Exception.Message;verified_vhd_path=$verifiedVhd;actual_percentage=$script:lastPercentage;method='DiskPart'} | ConvertTo-Json | Set-Content -LiteralPath $receiptPath -Encoding UTF8
        Save-Progress 'FAILED';$percent.Text='오류';$details.Text=$_.Exception.Message
    }
})
$form.Add_FormClosing({param($sender,$eventArgs) if (-not $script:finished) {$eventArgs.Cancel=$true}})
$form.Add_Shown({
    [void]$process.Start();$script:readTask=$process.StandardOutput.BaseStream.ReadAsync($script:buffer,0,$script:buffer.Length);$script:errorTask=$process.StandardError.ReadToEndAsync();Save-Progress 'COMPACTING';$timer.Start()
})
[void]$form.ShowDialog()
