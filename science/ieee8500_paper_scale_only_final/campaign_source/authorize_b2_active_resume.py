"""Certify reuse of the previous 201 restricted candidate cache entries."""
from bootstrap import *
import ast
import hashlib

OLD=H/'diagnostic_attempts/B2_FULL_MIP_STALL_20260920/mess_runtime_before_tuning.py'
NEW=H/'mess_runtime.py'
FUNCTIONS=('four_thread_no_cutoff_candidate','coefficients','traffic')


def function_sha(path,name):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()


def nested_sha(path,name,inner):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    outer=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    node=next(n for n in outer.body if isinstance(n,ast.FunctionDef) and n.name==inner)
    return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()


def main():
    prior=read(H/'diagnostic_attempts/B2_FULL_MIP_STALL_20260920/SNAPSHOT.json')
    assert sha(OLD)==prior['source_sha256']
    assert prior['restricted_candidates_certified']==201
    checks={name:dict(old=function_sha(OLD,name),current=function_sha(NEW,name))
            for name in FUNCTIONS}
    checks['search.current_b0_seed']=dict(
        old=nested_sha(OLD,'search','current_b0_seed'),
        current=nested_sha(NEW,'search','current_b0_seed'))
    assert all(v['old']==v['current'] for v in checks.values())
    benchmark=read(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json')
    assert benchmark['status']=='BENCHMARK_COMPLETE' and benchmark['full_separation_closed']
    assert benchmark['iterations'][-1]['restricted']['mip_gap']<=.001
    assert benchmark['iterations'][-1]['separation']['new_rows']==0
    assert read(H/'B2_ACTIVE_SET_DIAGNOSTIC/INPUT_AUTHORITY.json')['pcc_input_sha256']==sha(H/'MAY01_B0_AIDC_POWER.npz')
    cache=list((H/'B2/candidate_cache').rglob('*'))
    cache=[p for p in cache if p.is_file()]
    assert len(cache)==201
    result=dict(status='PASS',prior_restricted_solver_source_sha256=sha(OLD),
        current_mess_runtime_sha256=sha(NEW),restricted_candidate_problem_unchanged=True,
        function_ast_sha256=checks,cache_file_count=len(cache),
        cache_filenames_sha256=hashlib.sha256('\n'.join(sorted(str(p.relative_to(H)) for p in cache)).encode()).hexdigest(),
        benchmark=record(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json'),
        prior_attempt=record(H/'diagnostic_attempts/B2_FULL_MIP_STALL_20260920/SNAPSHOT.json'),
        only_restricted_candidate_cache_reused=True,
        full_integrated_solution_reused=False,exact_AC_solution_reused=False)
    save(H/'B2_PERFORMANCE_RESUME_AUTHORITY.json',result)
    print('B2_RESTRICTED_CACHE_RESUME_PASS',len(cache))


if __name__=='__main__':main()
