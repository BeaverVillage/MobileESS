from pathlib import Path
import sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from dayahead.v40b.reuse import validate_case_files,build_matrix,write_matrix

def main():
    from dayahead.v39e.campaign_adapter import freeze_path
    from dayahead.v39d.actual import validate_actual_fixed_replay
    probe=read(ROOT/'V40B_CURRENT_LOADER_PROBE.json')
    snapshot=read(ROOT/'V40B_PRELAUNCH_SNAPSHOT.json')
    certificates={};audits={case:[] for case in ('B0','B1','B2')}
    for row in probe['rows']:
        day,case=row['day'],row['case'];cp=Path(row['checkpoint'])
        try:
            if not row['accepted'] or row['differences']:raise ValueError('CURRENT_LOADER_REJECTED')
            case_root=Path(row['result']['root']);payload=validate_case_files(day,case,cp,case_root)
            frozen=read(freeze_path(REPO,day,case))
            assert validate_actual_fixed_replay(frozen,frozen['DA_decision_SHA256'])['status']=='PASS'
            certificate={'status':'PASS','day':day,'case':case,'CURRENT_LOADER_ACCEPTS_OLD_RESULT':'YES',
               'historical_checkpoint':str(cp),'historical_checkpoint_SHA':sha(cp),'historical_case_root':str(case_root),
               'files':payload['files'],'current_execution_fingerprint':payload['execution_fingerprint'],
               'DA_file_SHA':sha(freeze_path(REPO,day,case)),'DA_decision_SHA':frozen['DA_decision_SHA256'],
               'Fresh_schedule_SHA':row['result']['Fresh']['schedule_sha256'],'current_loader_probe_SHA':sha(ROOT/'V40B_CURRENT_LOADER_PROBE.json'),
               'terminal_authority_binding':'COMPLETE_ACCEPTED_DA_FREEZE_AND_CURRENT_V39K_MANIFEST','old_result_modified':False}
            write(ROOT/'reuse_certificates'/f'{day}_{case}.json',certificate);certificates[f'{day}:{case}']=certificate
            audits[case].append(certificate);print(day,case,'CERTIFIED',flush=True)
        except Exception as e:
            audits[case].append({'day':day,'case':case,'status':'FAIL','error':repr(e)})
            print(day,case,'REJECT',repr(e),flush=True)
    regressions=[]
    for day in ('2025-04-01','2025-05-01'):regressions+=read(ROOT/'regression'/day/'REGRESSION_RESULT.json')['rows']
    approved={}
    for case in ('B0','B1','B2'):
        numeric=all(r['status']=='PASS' for r in regressions if r['case']==case) and len([r for r in regressions if r['case']==case])==2
        structural=all(snapshot[k]['status']=='PASS' for k in ('old_source','current_source','current_authority'))
        approved[case]=numeric and structural
        write(ROOT/f'V40B_{case}_REUSE_AUDIT.json',{'status':'PASS' if approved[case] else 'FAIL','source_equivalence':'PASS' if structural else 'FAIL',
             'numerical_regression':'PASS' if numeric else 'FAIL','cases':audits[case]})
    write(ROOT/'V40B_NUMERICAL_REGRESSION.json',{'status':'PASS' if all(approved.values()) else 'FAIL','predeclared_plan_SHA':sha(ROOT/'V40B_NUMERICAL_REGRESSION_PLAN.json'),'rows':regressions})
    rows=build_matrix(certificates,approved);write_matrix(rows)
    write(ROOT/'V40B_REUSE_AUTHORIZATION.json',{'status':'PASS' if all(approved.values()) else 'FAIL','approved':approved,
        'OLD_B3_REUSE_APPROVED':False,'certificates':{key:str(ROOT/'reuse_certificates'/f'{key.replace(":","_")}.json') for key in certificates},
        'created_at_utc':now_utc(),'numerical_regression_SHA':sha(ROOT/'V40B_NUMERICAL_REGRESSION.json'),
        'reused_counts':{c:sum(r['case']==c and r['status']=='REUSE_CERTIFIED' for r in rows) for c in CASES}})

if __name__=='__main__':main()
