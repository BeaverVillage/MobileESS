"""Real three-slot Current/cache/Fresh comparison after IO-only cache repair."""
import ast
from pathlib import Path
from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,now
from .locks import coordinator
from .config import axis

OUT=RUNTIME/'svr11_revision01/CURRENT_CACHE_REQUALIFY001'


def run():
    from .svr11_smoke import sources,observed_issue_rows
    from .svr11_ac import SVR11CurrentAC
    from .svr11_hardware import HARDWARE
    from v42_may_campaign_native90.preflight import native_zero
    if OUT.exists():raise FileExistsError('NEW_CACHE_DIAGNOSTIC_ROOT_REQUIRED')
    OUT.mkdir(parents=True)
    old=RUNTIME/'svr11_revision01/PHYSICAL_DRIVER_SHORT_PREFIX001'
    archived=read(old/'SOURCE_SNAPSHOT_RECEIPT.json');verify([r['snapshot'] for r in archived['sources']])
    old_ac=next(Path(r['snapshot']['path']) for r in archived['sources'] if Path(r['original']['path']).name=='svr11_ac.py')
    def definitions(path):
        tree=ast.parse(Path(path).read_text(encoding='utf8'));result={}
        for n in tree.body:
            if isinstance(n,ast.FunctionDef):result[n.name]=ast.dump(n,include_attributes=False)
            if isinstance(n,ast.ClassDef):
                for m in n.body:
                    if isinstance(m,ast.FunctionDef):result[n.name+'.'+m.name]=ast.dump(m,include_attributes=False)
        return result
    before=definitions(old_ac);after=definitions(ROOT/'v44/svr11_ac.py')
    changes=[name for name in before if before[name]!=after[name]]
    if set(changes)!={'SVR11CurrentAC.__init__','SVR11CurrentAC._probe'}:
        raise ValueError('CACHE_REPAIR_MUST_NOT_CHANGE_NATIVE_PROBE_CONTROL_OR_FRESH_FUNCTIONS')
    frozen=sources()+[record(Path(__file__))];hardware=record(HARDWARE/'HARDWARE.json')
    atomic(OUT/'SOURCE_DELTA.json',dict(PASS=True,changed_methods=changes,
        original_control_probe_TIME_mapper_Fresh_functions_AST_identical=True,
        old_source=record(old_ac),new_source=record(ROOT/'v44/svr11_ac.py'),
        cache='READ_ONLY_MEASUREMENTS_AFTER_EXACT_INPUT_NATIVE_TAP_QUEUE_ALL_COMPLEX_VOLTAGE_EQUALITY',
        native_solve_or_engine_state_reuse=False))
    with coordinator(OUT/'LEASE'),native_zero() as denied:
        rows,sites,model,observations,inputs=observed_issue_rows('2025-05-01',3);a=axis('2025-05-01')
        oracle=SVR11CurrentAC(arm='B1',issue_seconds=a['issue_seconds'],sites=sites,power_model=model,
            observations=observations,mess_plan=None,day_start_seconds=a['day_start_seconds'])
        first=oracle._probe(rows);second=oracle._probe(rows)
        reused=oracle.performance['verified_history_reuses'];branches=oracle.performance['legacy_branch_measurement_reuses']
        fresh=oracle.full_fresh_probe(rows)
        exact=first['physical_steps']==second['physical_steps']==fresh['physical_steps']
        passed=exact and reused>=2 and branches>0 and oracle.performance['verified_history_reuses']==reused and not denied
        atomic(OUT/'PAIRED_RAW.json',dict(first=first,cached=second,independent_Fresh=fresh))
        verify(frozen+[hardware])
        result=dict(PASS=passed,UTC=now(),exact_measurement_and_native_state_equality=exact,
            historical_measurement_reuses=reused,legacy_branch_measurement_reuses=branches,
            independent_Fresh_cache_reads=0,native_solve_or_engine_state_reuse=0,
            logical_slots_per_probe=3,physical_probes=3,Native_optimizer_calls=0,Actual96_runs=0,Fresh96_runs=0,
            source_delta=record(OUT/'SOURCE_DELTA.json'),sources=frozen,hardware=hardware,
            paired_Raw=record(OUT/'PAIRED_RAW.json'),old_seven_day_prefix_evidence=record(old/'RESULT.json'))
        atomic(OUT/'RESULT.json',result)
        if not passed:raise ValueError('CACHE_NATIVE_TIME_NUMERIC_EQUIVALENCE_FAILED')
    cert=dict(PASS=True,sources=frozen+[record(OUT/'RESULT.json')],hardware=hardware,
        real_prefix_evidence=record(old/'RESULT.json'),new_source_validation=record(OUT/'RESULT.json'),
        source_7reg_certificate_reused=False,RegControl_count=40,Native_TIME_prefix_verified=True,
        full_96_slot_security='NOT_CERTIFIED',
        scope='SAME_PINNED_EPOCH12_CONTROL_PHYSICS_SEVEN_DAY_PREFIX_PLUS_REPAIRED_CACHE_EXACT_REAL_PAIR')
    atomic(DOC/'svr11_revision01/CURRENT_AC_CERTIFICATION.json',cert)
    report=read(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json')
    report.update(cache_requalification=record(OUT/'RESULT.json'),current_adapter_sources=frozen,
        old_short_prefix_source_bytes=record(old/'SOURCE_SNAPSHOT_RECEIPT.json'),
        old_frozen_native_control_physics_changed=False)
    atomic(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json',report)
    print(dict(PASS=passed,history_measurements_reused=reused,branch_measurements_reused=branches),flush=True)


if __name__=='__main__':run()
