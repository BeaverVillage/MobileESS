from pathlib import Path
OUT=Path(__file__).absolute().parent
p=OUT/'monitoring/monitor_v41r1_may_live.ps1'
s=p.read_text(encoding='utf-8-sig')
if 'function Get-CurrentActualMetric' not in s:
 function=r'''
function Get-CurrentActualMetric([string]$Date,[string]$Policy) {
    $campaign=Split-Path $Repo -Parent
    $base=if($Policy -eq 'B3_1R'){'replays_1round'}else{'replays'}
    $pol=if($Policy -like 'B3_*'){'B3'}else{$Policy}
    $af=Join-Path $campaign ($base+'\'+$Date+'\'+$pol)
    $cf=Join-Path $af 'COMPLETE.json';$pf=Join-Path $af 'PROGRESS.json'
    try {
        if(Test-Path -LiteralPath $cf){
            $r=Read-LiveJson $cf
            return [pscustomobject]@{rho=$r.new_Actual_rho;Vmax=$r.summary.Vmax_pu;text=('{0:N4}% 확정' -f (100*$r.new_Actual_rho));status=if($r.AC_PASS){'PASS'}else{'FAIL'};slots=96}
        }
        if(Test-Path -LiteralPath $pf){
            $r=Read-LiveJson $pf
            $txt=if($null -ne $r.exact_rho_so_far){'{0:N4}% 잠정 ({1}/96)' -f (100*$r.exact_rho_so_far),$r.slots_complete}else{'{0}/96 · 최대값 집계 대기' -f $r.slots_complete}
            return [pscustomobject]@{rho=$r.exact_rho_so_far;Vmax=$null;text=$txt;status='실행 중';slots=$r.slots_complete}
        }
    } catch {}
    return [pscustomobject]@{rho=$null;Vmax=$null;text='— 대기';status='대기';slots=0}
}
'''
 s=s.replace('function Get-B3MonitorPhase',function+'\nfunction Get-B3MonitorPhase',1)
 anchor="                $lines.Add(('  {0,-5} {1,-12} {2,11} {3,12}    {4,-8}  {5,-8}  {6}' -f $policy,$displayStatus,$p1,$p2,$fg,$ag,$voltageText))"
 replacement="                $mm=Get-CurrentActualMetric $chosen $policy; $ag=$mm.status; $voltageText=$mm.text; $fg='FROZEN'\n"+anchor
 assert s.count(anchor)==1;s=s.replace(anchor,replacement)
s=s.replace('Actual: Robust V2 · η=0.95 · P 고정 / Q-only','Actual: Q-first → 최소 P 보정 → 인과적 에너지 회복 · η=0.95')
s=s.replace('Actual Vmax / ρmax','Actual 최대선로부하율 (%)')
# Compact header: retain detailed policy results only in the lower table.
start=s.find("        $lines.Add(('  [{0}]")
if start >= 0:
 end=s.index("        $active=@($units | Where-Object",start)
 s=s[:start]+r'''
        $failState=if($fails -gt 0 -or $progress.status -match 'FAIL|ERROR|STOP'){'있음'}else{'없음'}
        $lines.Clear()
        $lines.Add(('  전체 진행률 {0:N1}% ({1}/155 완료)  |  FAIL: {2}' -f $percent,$done,$failState))
        $lines.Add('')
'''+s[end:]

p.write_text(s,encoding='utf-8-sig')
