"""Read-only extraction of completed production arrays. No scientific rerun."""
import csv, json, hashlib, re, zipfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

H=Path(r'D:\ChatGPT\Mobile ESS 2\IEEE8500_PAPER_SCALE_ONLY_20260920\full_production_paper_BG055200_AIDC240_MESS200')
DEST=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/결과 데이터')
OUT=DEST/'IEEE8500_FINAL_PAPER_HEATMAP_CSV_20260923'
POLICIES=['B0','B1','B2','B3']
sources={};checks=[];outputs={}
def source(p):
    p=Path(p);b=p.read_bytes();sources[str(p)]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};return b
def read(p):return json.loads(source(p))
def write(name,rows,fields=None):
    rows=list(rows);fields=fields or list(rows[0])
    with (OUT/name).open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    outputs[name]={'rows':len(rows),'columns':len(fields)}
    print(name,len(rows),flush=True)
def bus(s):return re.sub(r'(\.\d+)+$','',s).lower()
def stamp(t):return (datetime(2025,5,1)+timedelta(minutes=15*int(t))).isoformat(timespec='minutes')

def main():
    OUT.mkdir(exist_ok=False)
    report=read(H/'FINAL_CAMPAIGN_RESULT.json');review=read(H/'FINAL_REVIEW_20260923.json')
    assert report['status']=='PASS'
    ax=read(H/'AXES.json');axes=ax['line'];ratings=np.array(ax['line_rating_A'])
    group=defaultdict(list)
    for i,a in enumerate(axes):group[a.split('|')[0]].append(i)
    ids=list(group);idsort=sorted(ids)
    coord={}
    cp=H.parents[1]/'IEEE8500_scalability_20260910/source/Buscoords.dss'
    for line in source(cp).decode('utf-8-sig').splitlines():
        line=re.split(r'//|!',line)[0].strip();parts=[x.strip() for x in line.split(',')]
        if len(parts)==3:
            try:coord[parts[0].lower()]=(float(parts[1]),float(parts[2]))
            except ValueError:pass
    for line in source(H/'PCC_BusCoordinates.dss').decode('utf-8-sig').splitlines():
        m=re.search(r'Bus=(\S+)\s+x=(\S+)\s+y=(\S+)',line,re.I)
        if m:coord[bus(m[1])]=(float(m[2]),float(m[3]))
    topology={}
    for e in ids:
        js=group[e];term=defaultdict(set)
        for j in js:
            _,t,b,n=axes[j].split('|');term[t].add(bus(b))
        assert set(term)=={'t1','t2'} and all(len(x)==1 for x in term.values())
        fr=next(iter(term['t1']));to=next(iter(term['t2']));xy1=coord.get(fr,('',''));xy2=coord.get(to,('',''))
        topology[e]=dict(element_id=e,from_bus=fr,to_bus=to,x_from=xy1[0],y_from=xy1[1],x_to=xy2[0],y_to=xy2[1],coordinates_available=fr in coord and to in coord,rating_A=float(ratings[js[0]]),phase_terminal_axis_count=len(js))
        assert len(set(ratings[js]))==1
    arrays={};linewide={};extrema={};actual={};critical={};ts=[]
    for p in POLICIES:
        root=H/'Actual'/p if p=='B0' else H/'Actual'/p/p
        actual[p]=read(root/'COMPLETE.json');assert actual[p]['AC_feasible'] and actual[p]['independent_replay_PASS']
        verify=read(root/'CONTINUOUS_VERIFICATION.json');assert verify['status']=='PASS' and all(v==0 for v in verify['max_errors'].values())
        fp=root/'CONTINUOUS_VERIFICATION/OPENDSS_PHASE_ARRAYS.npz'
        source(fp)
        with np.load(fp,allow_pickle=False) as z:
            assert z['line_phase_axes'].tolist()==axes
            a=z['line_current_loading_pu'].copy()
        assert a.shape==(96,len(axes)) and np.all(np.isfinite(a))
        arrays[p]=a;extrema[p]=read(root/'CONTINUOUS_VERIFICATION/SLOT_EXTREMA.json')
        arr=np.column_stack([a[:,group[e]].max(axis=1) for e in ids])
        linewide[p]=arr;critical[p]=int(np.argmax(a.max(axis=1)))
        expected=actual[p]['summary']['max_phase_line_loading_pu']
        assert abs(a.max()-expected)<1e-12 and abs(arr.max()-expected)<1e-12
        checks.append(dict(policy=p,array_max=float(a.max()),authority_max=expected,abs_error=abs(float(a.max())-expected),critical_slot=critical[p],critical_time=stamp(critical[p]),axes_exact_match=True))
        for t in range(96):
            j=int(a[t].argmax());assert abs(a[t,j]-extrema[p][t]['max_phase_line_loading_pu'])<1e-12
            ts.append(dict(policy=p,slot_0based=t,interval_1based=t+1,timestamp=stamp(t),rho_actual_pu=float(a[t,j]),rho_actual_percent=float(a[t,j]*100),critical_line_phase_axis=axes[j],Vmin_pu=extrema[p][t]['Vmin_pu'],Vmax_pu=extrema[p][t]['Vmax_pu']))
        write(f'HEATMAP_ACTUAL_{p}_LINE_BY_TIME_PU.csv',[dict(element_id=e,**{f'{t//4:02d}:{t%4*15:02d}':float(arr[t,ids.index(e)]) for t in range(96)}) for e in idsort])
    paper=[]
    for p in POLICIES:
        r=dict(next(r for r in review['results'] if r['policy']==p));r['DA_critical_slot_0based']=r.pop('critical_slot');r['DA_critical_line_phase']=r.pop('critical_line');r['Actual_critical_slot_0based']=critical[p];r['Actual_critical_timestamp']=stamp(critical[p]);r['Actual_critical_line_phase']=axes[int(arrays[p][critical[p]].argmax())]
        r['Actual_rho_percent']=r['Actual_rho']*100;r['Actual_Q_intervention_slots']=actual[p]['Q_intervention_slots']
        r['date']='2025-05-01';r['BG_scale']=.552;r['AIDC_absolute_scale']=2.4;r['MESS_scale']=2.0
        paper.append(r)
    fields=list(dict.fromkeys(k for r in paper for k in r));write('01_PAPER_POLICY_SUMMARY.csv',paper,fields)
    reduction=[]
    for scope,values in report['reductions'].items():
        for pair,v in values.items():
            left,right=pair.split('_minus_');base=next(r for r in paper if r['policy']==left)[scope]
            reduction.append(dict(scope=scope,comparison=pair,reduction_pu=v,reduction_percentage_points=v*100,relative_reduction_percent=v/base*100))
    write('02_PAPER_REDUCTIONS.csv',reduction)
    write('03_ACTUAL_SYSTEM_RHO_96SLOT.csv',ts)
    write('04_LINE_TOPOLOGY_COORDINATES.csv',[topology[e] for e in idsort])
    write('05_ACTUAL_DAILY_MAX_BY_LINE.csv',[dict(element_id=e,**{p+'_daily_max_pu':float(linewide[p][:,ids.index(e)].max()) for p in POLICIES}) for e in idsort])
    def snapshots(common):
        rows=[]
        for p in POLICIES:
            t=critical['B0'] if common else critical[p]
            for e in idsort:
                j=max(group[e],key=lambda j:arrays[p][t,j]);v=float(arrays[p][t,j])
                rows.append(dict(policy=p,slot_0based=t,interval_1based=t+1,timestamp=stamp(t),**topology[e],loading_pu=v,loading_percent=v*100,critical_phase_axis=axes[j],current_A=v*float(ratings[j]),evaluation_scope='REALIZED_OPERATION_AC'))
        return rows
    write('06_HEATMAP_COMMON_B0_CRITICAL_TIME.csv',snapshots(True))
    write('07_HEATMAP_EACH_POLICY_OWN_CRITICAL_TIME.csv',snapshots(False))
    write('08_HEATMAP_B3_OWN_CRITICAL_PHASE_DETAIL.csv',[dict(policy='B3',slot_0based=critical['B3'],timestamp=stamp(critical['B3']),**topology[a.split('|')[0]],source_axis=a,source_axis_index=j,terminal=a.split('|')[1],terminal_bus=a.split('|')[2],node=a.split('|')[3],loading_pu=float(arrays['B3'][critical['B3'],j]),current_A=float(arrays['B3'][critical['B3'],j]*ratings[j]),evaluation_scope='REALIZED_OPERATION_AC') for j,a in enumerate(axes)])
    delta=linewide['B0']-linewide['B3']
    write('09_HEATMAP_B0_MINUS_B3_LINE_BY_TIME_PU.csv',[dict(element_id=e,**{f'{t//4:02d}:{t%4*15:02d}':float(delta[t,ids.index(e)]) for t in range(96)}) for e in idsort])
    write('10_EXPORT_VALIDATION.csv',checks)
    # Reopen all numeric heatmap matrices and verify exported precision/order.
    for p in POLICIES:
        with (OUT/f'HEATMAP_ACTUAL_{p}_LINE_BY_TIME_PU.csv').open(encoding='utf-8-sig') as f:rs=list(csv.DictReader(f))
        assert [r['element_id'] for r in rs]==idsort
        recovered=np.array([[float(v) for k,v in r.items() if k!='element_id'] for r in rs]).T
        assert np.array_equal(recovered,linewide[p][:,[ids.index(e) for e in idsort]])
    missing=[e for e in ids if not topology[e]['coordinates_available']]
    assert not missing,('Missing coordinate records',missing[:20])
    manifest=dict(status='PASS',campaign=str(H),date='2025-05-01',scope='REALIZED_OPERATION_AC',line_metric='max over recorded phase/terminal abs(I)/frozen normal rating per line',slots=96,slot_minutes=15,line_count=len(ids),line_phase_terminal_axis_count=len(axes),coordinate_missing_count=len(missing),time_basis='simulation local wall clock; no timezone conversion or invented UTC offset',sources=sources,outputs=outputs,checks=checks,certifications=review['certifications'],scientific_reruns=0)
    for name in outputs:
        b=(OUT/name).read_bytes();outputs[name].update(sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'README_사용법.md').write_text('''# IEEE8500 최종 논문·히트맵 CSV

최종 production: 2025-05-01, BG 0.552 / AIDC absolute 2.40 / MESS 2.00. Paper PCC 유지.
모든 히트맵은 최종 **Actual**의 독립 96-slot 검증 배열에서 추출했습니다. 재최적화·재시뮬레이션은 하지 않았습니다.

## 사용할 파일

- `01_PAPER_POLICY_SUMMARY.csv`: 논문 표 교체. Planning / DA exact / Fresh / Actual을 각각 사용하세요. `Vmin`, `Vmax`는 DA, `Actual_Vmin`, `Actual_Vmax`는 Actual입니다.
- `02_PAPER_REDUCTIONS.csv`: DA와 Actual별 정책 간 감소량. pu, %p, 상대 감소율(%)을 구분했습니다.
- `03_ACTUAL_SYSTEM_RHO_96SLOT.csv`: 정책별 최대선로부하율 시간 곡선.
- `HEATMAP_ACTUAL_B0_LINE_BY_TIME_PU.csv` 등 4개: 행=선로, 열=00:00~23:45, 값=부하율 pu. 네 정책의 선로 순서가 같습니다.
- `06_HEATMAP_COMMON_B0_CRITICAL_TIME.csv`: **같은 시각에서 정책을 비교하는 공간 히트맵 권장 파일**. B0의 Actual 일일 최대 시각을 모든 정책에 공통 적용.
- `07_HEATMAP_EACH_POLICY_OWN_CRITICAL_TIME.csv`: 각 정책 자체의 최대 시각. 캡션에 서로 다른 시각일 수 있음을 표시하세요.
- `08_HEATMAP_B3_OWN_CRITICAL_PHASE_DETAIL.csv`: B3 자체 최대 시각의 모든 선로 phase/terminal 세부값.
- `09_HEATMAP_B0_MINUS_B3_LINE_BY_TIME_PU.csv`: B0−B3 부하율 차이. 양수는 감소, 음수는 해당 선로의 증가입니다.
- `04_LINE_TOPOLOGY_COORDINATES.csv`: 공간 히트맵 선분 좌표. 원본 feeder와 paper PCC 좌표를 사용하며 위경도로 변환하지 않았습니다.
- `05_ACTUAL_DAILY_MAX_BY_LINE.csv`: 선로별 하루 최댓값. 서로 다른 시각의 값을 모았으므로 특정 시각 스냅샷으로 표시하지 마세요.
- `10_EXPORT_VALIDATION.csv`, `MANIFEST.json`: 최종 authority와 최대값 대조 및 SHA-256 출처.

## 단위·시각·해석

- 0.930493 pu = 93.0493%. pu 차이 ×100 = percentage points (%p).
- 선로값은 같은 시간대의 phase/terminal 중 최대 |I|/정격입니다. 선로 전체 평균이 아닙니다.
- slot_0based=0~95, interval_1based=1~96. 시각은 15분 simulation local clock이며 임의 UTC offset을 붙이지 않았습니다.
- 네 정책의 색상 범위는 동일하게 사용하세요. 절대 부하율은 0~1 pu, 차이 히트맵은 0 중심의 대칭 범위를 권장합니다.
- CSV는 UTF-8 BOM, 숫자 정밀도는 원본 double 값을 유지했습니다.
- 기존 논문/히트맵 CSV와 raw 결과는 덮어쓰지 않았습니다. 이 폴더의 자료만 새 case에 사용하세요.
- B2의 runtime_seconds=308.252...는 마지막 복구 단계 시간입니다. 전체 B2 계산시간으로 인용하지 마세요. 별도 calendar 시간에는 중단·수정·대기가 포함됩니다.
- Actual B0−B3 차이는 약 1.357%p입니다. 처음 목표로 삼은 5~10%p 감소를 달성한 결과는 아닙니다.
''',encoding='utf-8')
    shutil.copy2(__file__,OUT/Path(__file__).name)
    archive=OUT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in OUT.iterdir():z.write(p,arcname=OUT.name+'/'+p.name)
    print(json.dumps(dict(status='PASS',folder=str(OUT),zip=str(archive),csv_count=len(outputs),lines=len(ids),checks=checks),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
