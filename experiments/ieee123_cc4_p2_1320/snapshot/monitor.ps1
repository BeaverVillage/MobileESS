param([switch]$Once)
$runtime=$PSScriptRoot
$showDetails=$false
$selectedDay=1
$quit=$false
if(-not ('V41MonitorConsoleInput' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class V41MonitorConsoleInput {
    [StructLayout(LayoutKind.Explicit, CharSet=CharSet.Unicode, Size=20)]
    public struct InputRecord {
        [FieldOffset(0)] public ushort EventType;
        [FieldOffset(4)] public int KeyDown;
        [FieldOffset(10)] public ushort VirtualKeyCode;
    }
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int n);
    [DllImport("kernel32.dll")] static extern bool GetConsoleMode(IntPtr h, out uint mode);
    [DllImport("kernel32.dll")] static extern bool SetConsoleMode(IntPtr h, uint mode);
    [DllImport("kernel32.dll", EntryPoint="PeekConsoleInputW")]
    static extern bool PeekConsoleInput(IntPtr h, [Out] InputRecord[] records, uint length, out uint count);
    [DllImport("kernel32.dll")] static extern bool FlushConsoleInputBuffer(IntPtr h);
    static IntPtr input;
    static uint originalMode;
    static bool configured;
    public static int HotkeysHandled;
    public static bool Configure() {
        input=GetStdHandle(-10);
        if(!GetConsoleMode(input,out originalMode)) return false;
        // ENABLE_EXTENDED_FLAGS is required to disable this window's QuickEdit.
        configured=SetConsoleMode(input,(originalMode | 0x80u) & ~0x40u);
        return configured;
    }
    public static int PollHotkey() {
        var records=new InputRecord[128];uint count;
        if(!PeekConsoleInput(input,records,(uint)records.Length,out count) || count==0) return 0;
        // This dashboard accepts only shortcuts, never a text-input line.
        // Both operations return immediately; no filtering read can block it.
        FlushConsoleInputBuffer(input);
        for(int i=0;i<count;i++) {
            if(records[i].EventType!=1 || records[i].KeyDown==0) continue;
            int key=records[i].VirtualKeyCode;
            if(key==0x44 || key==0x4f || key==0x51 || key==0x52 || key==37 || key==39) {
                HotkeysHandled++;return key;
            }
        }
        return 0;
    }
    public static void Restore() { if(configured) SetConsoleMode(input,originalMode); }
}
'@
}
$monitorInputConfigured=if(-not $Once){[V41MonitorConsoleInput]::Configure()}else{$false}
$refreshClock=[Diagnostics.Stopwatch]::StartNew()
$refreshSequence=0
function Read-LiveJson([string]$Path) {
    $reader=$null
    $share=[System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,$share)
    try {
        $reader=New-Object System.IO.StreamReader($stream);$text=$reader.ReadToEnd()
        try{return ($text | ConvertFrom-Json -ErrorAction Stop)}
        catch{return ($text | ConvertFrom-Json -AsHashtable -ErrorAction Stop)}
    }
    finally {if($reader){$reader.Dispose()}else{$stream.Dispose()}}
}
function Optional([string]$Path){if(Test-Path -LiteralPath $Path){try{return Read-LiveJson $Path}catch{}};return $null}
try {
$Host.UI.RawUI.WindowTitle='IEEE123 | CC4/P2 ABLATION 1320s | 4 workers x 4 threads'
do {
 $refreshSequence++;$refreshDeadline=$refreshClock.ElapsedMilliseconds+5000
 $lines=New-Object 'System.Collections.Generic.List[string]'
 $lines.Add(' IEEE123 MAY 2025 | B3 WITH CC4 vs WITHOUT CC4/P2 | 1-Round')
 $lines.Add(' Frozen WITH reused | NEW WITHOUT only | A1 > M1 > A2 > M2 > AC/Actual')
 $lines.Add(' Budget: P1 900 / P3 180 / P4 120 / P5 120 s | 4 days x 4 threads')
 $state=Optional (Join-Path $runtime 'CAMPAIGN_STATUS.json')
 if($state){
  $age=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-$state.updated_at
  $alive=$null -ne (Get-Process -Id $state.supervisor_pid -ErrorAction SilentlyContinue)
  $lines.Add((' {0} | completed {1}/31 | errors {2} | heartbeat {3:N0}s | PID {4} alive={5}' -f $state.status,@($state.completed).Count,@($state.errors).Count,$age,$state.supervisor_pid,$alive))
  $lines.Add((' CPU {0:N0}% | available RAM {1:N1} GiB | monitor independent of solver' -f $state.cpu_percent,$state.ram_available_gib))
  $lines.Add(' -----------------------------------------------------------------------------')
  foreach($prop in $state.active.PSObject.Properties){
   $day=$prop.Name;$r=$prop.Value;$case=Join-Path $runtime ('days\'+$day);$phase=$r.phase;$live=$null
   if($phase -eq 'A1'){$live=Optional (Join-Path $case ('runs\'+$day+'\B1\dayahead\A0\F_AND_O_LIVE.json'))}
   if($phase -eq 'B3'){
    $da=Join-Path $case ('runs\'+$day+'\B3\dayahead')
    if(Test-Path -LiteralPath (Join-Path $da 'FROZEN_JOINT_DECISION.json')){$phase='Fresh'}
    elseif(Test-Path -LiteralPath (Join-Path $da 'optimization\stages\MF_INPUT_CERTIFICATE.json')){$phase='M2'}
    elseif(Test-Path -LiteralPath (Join-Path $da 'optimization\stages\A1_INPUT.json')){$phase='A2';$live=Optional (Join-Path $da 'A1\F_AND_O_LIVE.json')}
    else{$phase='M1'}
   }
   $minutes=([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-$r.started_at)/60
   $lines.Add((' {0} | PID {1} | {2,-10} | elapsed {3:N1} min' -f $day,$r.pid,$phase,$minutes))
   if($live){$lines.Add(('   {0} | search {1:N0}/1320s | incumbent [{2}]' -f $live.stage,$live.search_loop_wall_seconds,(($live.incumbent | ForEach-Object {'{0:G7}' -f $_}) -join ', ')))}
   if($showDetails){$lines.Add('   '+$r.log_path);$tail=Get-Content -LiteralPath $r.log_path -Tail 2 -ErrorAction SilentlyContinue;foreach($t in $tail){$lines.Add('   '+$t.Substring(0,[Math]::Min(135,$t.Length)))}}
  }
  foreach($e in $state.errors){$lines.Add((' ERROR {0} {1} exit={2} | {3}' -f $e.day,$e.phase,$e.exit_code,$e.log))}
  foreach($h in $state.held_dates.PSObject.Properties){$lines.Add((' HOLD {0} | Actual boundary review pending; completed work preserved' -f $h.Name))}
  $lines.Add('')
  for($base=1;$base -le 31;$base+=8){
   $cells=@();for($d=$base;$d -lt [Math]::Min(32,$base+8);$d++){$date='2025-05-{0:D2}' -f $d;$mark='WAIT';if($date -in $state.completed){$mark='DONE'}elseif($state.active.PSObject.Properties.Name -contains $date){$mark='RUN'};if($date -in @($state.errors | ForEach-Object {$_.day})){$mark='FAIL'};if($state.held_dates.PSObject.Properties.Name -contains $date){$mark='HOLD'};$cells+=('{0:D2}:{1,-4}' -f $d,$mark)}
   $lines.Add(' '+($cells -join '  '))
  }
 }else{$lines.Add(' Waiting for supervisor / authority preflight...')}
 $chosen='2025-05-{0:D2}' -f $selectedDay;$paired=Optional (Join-Path $runtime ('days\'+$chosen+'\paired.json'))
 $lines.Add('');$lines.Add((' Selected {0} | [Left/Right] date | [D] details | [O] logs | [R] reports | [Q] close monitor' -f $chosen))
 if($paired){
  foreach($key in @('P1_planning_rho','DA_exact_AC_max_rho','Fresh_exact_AC_max_rho','Actual_max_rho','mean_reserve_shortfall_GPUh','migration_count','MESS_relocation_count','MESS_charge_kWh','MESS_discharge_kWh')){$lines.Add((' {0,-30} WITH {1,12:G7} WITHOUT {2,12:G7}' -f $key,$paired.WITH.$key,$paired.WITHOUT.$key))}
  $lines.Add((' Changed jobs {0} / migrations {1} / MESS routes {2} / P-Q intervals {3}' -f $paired.row.changed_jobs_count,$paired.row.changed_migrations_count,$paired.row.changed_MESS_route_count,$paired.row.changed_PQ_intervals))
 }else{$lines.Add(' Paired final results pending. Missing values are not shown as zero or PASS.')}
 $lines.Add((' {0} | refresh 5s | closing Codex or this window does not stop production' -f (Get-Date -Format 'HH:mm:ss')))
 if(-not $Once){Clear-Host};foreach($line in $lines){$color=if($line -match 'ERROR|FAIL|HOLD'){'Red'}elseif($line -match 'IEEE123|Selected|Budget'){'Cyan'}else{'Gray'};Write-Host $line -ForegroundColor $color}
 [IO.File]::WriteAllText((Join-Path $runtime 'MONITOR_LAST_FRAME.txt'),($lines -join [Environment]::NewLine))
 [IO.File]::WriteAllText((Join-Path $runtime 'MONITOR_HEARTBEAT.json'),(@{pid=$PID;sequence=$refreshSequence;updated_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()} | ConvertTo-Json))
 if(-not $Once){while($refreshClock.ElapsedMilliseconds -lt $refreshDeadline){
  $key=[V41MonitorConsoleInput]::PollHotkey()
  if($key -eq 0x44){$showDetails=-not $showDetails}elseif($key -eq 39){$selectedDay=1+($selectedDay%31)}elseif($key -eq 37){$selectedDay=1+(($selectedDay+29)%31)}elseif($key -eq 0x51){$quit=$true}
  elseif($key -eq 0x4f){$folder=Join-Path $runtime ('days\'+$chosen+'\logs');if(Test-Path $folder){Invoke-Item -LiteralPath $folder}}
  elseif($key -eq 0x52){$folder=Join-Path $runtime 'reports';if(Test-Path $folder){Invoke-Item -LiteralPath $folder}}
  if($key -ne 0){break};Start-Sleep -Milliseconds 100
 }}
}while(-not $Once -and -not $quit)
}finally{[V41MonitorConsoleInput]::Restore()}
