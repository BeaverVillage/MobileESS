"""Conclude the capped experiment from preserved independent receipts."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/v42_b2_root_lp_tightening'
OLD=.46498486997548166
UB=.6760534504652341


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def finish():
    ledger=read(OUT/'NATIVE_LEDGER.json')
    assert [r['kind'] for r in ledger['calls']]==['BASE','GRID','SOC']
    assert sum(r['TimeLimit'] for r in ledger['calls'])==720
    stages=[];valid=[];results=[]
    base=read(OUT/'base/INDEPENDENT_CERTIFICATE.json')
    assert base['PASS'] and base['solver_status']==2
    for kind in ('BASE','GRID','SOC'):
        p=OUT/kind.lower();cert=read(p/'INDEPENDENT_CERTIFICATE.json');result=read(p/'RESULT.json');results.append(result)
        zero=read(p/'INDEPENDENT_NATIVE0.json')
        assert zero['PASS'] and result['Native_optimize_calls']==1 and result['full_MILP_calls']==0
        success=cert['PASS'] and result['Status']==2
        if success:valid.append(cert['LP_lower_bound'])
        stages.append(dict(kind=kind,model_dimensions=zero['dimensions'],Native_status=result['Status'],
            Native_Runtime=result['Runtime'],optimize_wall_seconds=result['optimize_wall_seconds'],
            LP_ObjVal=result['ObjVal'] if success else None,LP_lower_bound=cert.get('LP_lower_bound') if success else None,
            certificate_PASS=success,certificate_sha256=sha(p/'INDEPENDENT_CERTIFICATE.json'),
            Delta_LP_objective=cert.get('Delta_LP_objective'),Delta_LP_lower_bound=cert.get('Delta_LP_lower_bound'),
            decision=('BASE_REFERENCE' if kind=='BASE' else 'REJECT_SOC_NONMATERIAL' if success and kind=='SOC'
                      else 'GRID_EFFECT_UNCERTIFIED_ADOPTION_DEFERRED'),
            original_integer_projection_preserved=zero['original_integer_projection_preserved']))
    assert read(OUT/'soc/INDEPENDENT_CERTIFICATE.json')['PASS']
    published=max([OLD]+valid)
    summary=dict(PASS=True,classification='ROOT_LP_SOC_NONMATERIAL_GRID_UNCERTIFIED',
        base_PR211='d12315a3757aec187c8da0685c28ef901466386a',Source18r='497609b46faa14ea7e32a9483a333ab32fd264ef',
        Global_LB=published,PR211_Global_LB=OLD,UB=UB,global_gap=(UB-published)/UB,
        Global_Gap_percent=100*(UB-published)/UB,Global_LB_improved=published>OLD,
        stages=stages,adopted_candidates=[],SOC_decision='REJECT_NONMATERIAL',
        GRID_decision='EFFECT_UNCERTIFIED_ADOPTION_DEFERRED',combined_candidate_decision='NO_COMBINED_EXPERIMENT_OR_ADOPTION',
        Native_calls=3,requested_Native_seconds=720,actual_Native_Runtime=sum(r['Runtime'] for r in results),
        optimize_wall_seconds=sum(r['optimize_wall_seconds'] for r in results),
        peak_process_RSS_bytes=max(r['peak_process_RSS_bytes'] for r in results),
        peak_private_commit_bytes=max(r['peak_private_commit_bytes'] for r in results),
        minimum_RAM_available=min(r['minimum_RAM_available'] for r in results),
        minimum_commit_available=min(r['minimum_commit_available'] for r in results),
        source_integer_binary_count=9322,LP_binary_count=0,additional_binary_count=0,
        full_MILP_calls=0,campaign_calls=0,IEEE8500_calls=0,B1_Native_launches_by_this_task=0,
        GRID_consumed_call_not_restarted=True,extra_Native_calls=0,production_integration=False,
        original_source_ledger_results_mutations_by_this_task=0,
        B2_priority_override_sha256=sha(OUT/'USER_PRIORITY_OVERRIDE.json'),
        numerical_OPTIMAL_is_exact_LP_optimum_claim=False,exact_weak_duality_certificates=['BASE','SOC'],
        legacy_GRID_guard_trigger_not_actual_collision_proof=True,
        scope='SOC preserved all original integer points and cut the validated BASE point, but did not improve the numerical LP optimum. Its tiny corrected dual-bound gain is certificate quality, not material formulation improvement. GRID has valid cuts but no completed candidate LP, so its effect remains unmeasured. No fourth call or automatic budget reset.')
    write(OUT/'FINAL_RESULT.json',summary)
    print(json.dumps(dict(PASS=True,classification=summary['classification'],Global_LB=published,
                         SOC_objective_delta=stages[2]['Delta_LP_objective'],Native_calls=3)))


if __name__=='__main__':finish()
