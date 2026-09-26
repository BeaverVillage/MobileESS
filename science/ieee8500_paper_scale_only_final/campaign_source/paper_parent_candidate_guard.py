"""Bind the original v37 serial representative guard without changing solves."""
import ast,inspect,json,time,hashlib
from pathlib import Path
H=Path(__file__).absolute().parent

def original_guard(runner,solve_item):
    source=inspect.getsource(runner._beam_case)
    tree=ast.parse(source)
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='safe_parent_solve')
    code=ast.get_source_segment(source,node)
    ns=dict(runner.__dict__)
    ns['original']={'solve_item':solve_item}
    exec(compile(code,inspect.getsourcefile(runner)+'::safe_parent_solve','exec'),ns)
    return ns['safe_parent_solve'],hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()

def bind(runner,solve_item):
    guarded,ast_sha=original_guard(runner,solve_item)
    def observed(*args,**kwargs):
        result=guarded(*args,**kwargs)
        if result[3].get('fail_closed'):
            row=dict(unix=time.time(),case=str(args[0]),candidate_id=args[1].candidate_id,
                original_v37_guard_ast_sha256=ast_sha,signature=result[3]['signature'],
                action='ORIGINAL_UNCERTIFIED_FAIL_CLOSED',not_a_feasible_dispatch=True,
                candidate_retained_in_full_scan=True)
            with (H/'PAPER_PARENT_GUARD_EVENTS.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            print('PAPER_REPRESENTATIVE_FAIL_CLOSED',row['candidate_id'],row['signature'],flush=True)
        return result
    return observed
