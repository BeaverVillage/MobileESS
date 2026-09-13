from pathlib import Path
import json, hashlib, csv, datetime
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
V41=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,obj):
    with (HERE/name).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)
def rec(p):
    p=Path(p);s=p.stat();return dict(path=str(p.resolve()),sha256=sha(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns)
def main():
    save('DATE_SELECTION_PREREGISTRATION.json',dict(rule='argmax over 31 May 2025 B0 DAYAHEAD Fresh daily maximum phase-line current / line NormAmps; exact ties earliest ISO date',allowed_case='B0',allowed_namespace='DAYAHEAD',B1_B2_B3_result_reads_allowed=False,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    protected=[]
    for folder in ('IEEE8500_scalability_20260910','IEEE8500_pcc_overlay_20260911'):
        protected.extend(rec(p) for p in sorted((ROOT/folder).rglob('*')) if p.is_file())
    save('IMMUTABLE_AUTHORITIES_BEFORE.json',protected)
    idx=json.loads((ROOT/'v41r4_csv_reaudit_20260909/archive_member_index.json').read_text())
    idx={k.split('/',1)[1]:v for k,v in idx.items()}
    rows=[]; refs=[]
    for n in range(1,32):
        day=f'2025-05-{n:02d}';base=f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}/B0/dayahead/fresh'
        s=V41/base/'OPENDSS_SUMMARY.json';a=V41/base/'OPENDSS_PHASE_ARRAYS.npz'
        for p in (s,a):
            r=rec(p);expected=idx[p.relative_to(V41).as_posix()]
            assert r['sha256']==expected['sha256'] and r['bytes']==expected['bytes']
            refs.append(r)
        summary=json.loads(s.read_text())
        assert (summary['day'],summary['case'],summary['namespace'],summary['convergence_count'])==(day,'B0','DAYAHEAD',96)
        # Deliberately do not access voltage, loss, transformer or any non-B0 result arrays.
        with np.load(a,allow_pickle=False) as z:
            mask=z['branch_kinds']=='line';values=z['phase_current_loading_pu'][:,mask]
            names=z['branch_names'][mask];phases=z['branch_phases'][mask]
            assert values.shape[0]==96 and np.isfinite(values).all()
            t,k=np.unravel_index(values.argmax(),values.shape);rho=float(values[t,k])
            assert abs(rho-summary['rho_max_AC'])<1e-12
            rows.append(dict(day=day,daily_max_phase_line_loading_pu=rho,slot=int(t),line=str(names[k]),phase=str(phases[k]),namespace='DAYAHEAD',case='B0',convergence_count=96,archive_hash_verified=True))
    chosen=sorted(rows,key=lambda r:(-r['daily_max_phase_line_loading_pu'],r['day']))[0]
    with (HERE/'MAY_B0_FRESH_DAILY_LINE_MAXIMA.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    save('DATE_SELECTION_SOURCES.json',refs)
    save('SELECTED_DATE_FREEZE.json',dict(status='FROZEN',selected=chosen,rule_sha256=sha(HERE/'DATE_SELECTION_PREREGISTRATION.json'),daily_table_sha256=sha(HERE/'MAY_B0_FRESH_DAILY_LINE_MAXIMA.csv'),sources_sha256=sha(HERE/'DATE_SELECTION_SOURCES.json'),B1_B2_B3_results_read=False,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print(json.dumps(chosen));print('Protected files:',len(protected))
if __name__=='__main__':main()
