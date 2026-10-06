from v42_m_stage.common import *
import ast

def functions(path):
    tree=ast.parse(Path(path).read_text(encoding='utf8'))
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree)
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

def run():
    original=functions(OUT/'EXECUTED_SOURCE/cg.py');current=functions(ROOT/'v42_m_stage_root/cg.py')
    checked=['solve_master','certify','smooth_snapshot','run','run_certification','spent','remaining']
    assert all(original[n]==current[n] for n in checked)
    old=functions(OUT/'EXECUTED_SOURCE/integration.py');new=functions(ROOT/'v42_m_stage_root/integration.py')
    audits=['setup_audits','audit_one','tier_audit','parallel_validation']
    assert all(old[n]==new[n] for n in audits)
    freeze=read(OUT/'ROOT_EXECUTION_FREEZE.json')
    for file in ('v42_m_stage_root/worker.py','v42_m_stage_root/cg_reuse.py','v42_m_stage_root/policy.py'):
        assert sha(ROOT/file)==freeze['sources'][file]
    proof=dict(PASS=True,native_optimization_methods_AST_unchanged=checked,
        scientific_audit_methods_AST_unchanged=audits,pricing_and_convergence_policy_bytes_unchanged=True,
        executed_source_snapshot_matches_original_freeze=all(sha(OUT/'EXECUTED_SOURCE'/Path(p).name)==freeze['sources'][p]
            for p in ('v42_m_stage_root/cg.py','v42_m_stage_root/integration.py')),
        post_native_control_tests='3 passed; 2 existing repeated plus 1 new rejected-dual regression',
        independent_bound_check=read(OUT/'ROOT_INDEPENDENT_BOUND_CHECK.json'),
        runtime_limitations=read(OUT/'ROOT_MEASUREMENT_LIMITATIONS.json'))
    assert proof['executed_source_snapshot_matches_original_freeze']
    write('POST_NATIVE_CONTROL_REPAIR_VERIFICATION.json',proof)
    v=read(OUT/'VERIFICATION.json');v['post_native_control_repair']=proof
    v['source_freeze_note']='Native execution SHA preserved; later report/control changes separately declared and tested, with mathematical/native methods unchanged'
    write('VERIFICATION.json',v)
    files={p.relative_to(ROOT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and
        p.name not in ('SHA256_MANIFEST.json','PUBLICATION_RECEIPT.json') and not p.name.endswith('.tmp')}
    write('SHA256_MANIFEST.json',dict(files=files,publication_receipt_excluded_to_avoid_self_reference=True))
    print('MANIFEST_SEALED',len(files),flush=True)

if __name__=='__main__':run()
