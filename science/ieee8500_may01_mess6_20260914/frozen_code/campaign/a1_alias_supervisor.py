"""Original continuous 14,400s supervisor, selecting only the alias-safe worker."""
import ast,traceback
import a1_supervisor as original
if __name__=='__main__':
    text=(original.H/'a1_supervisor.py').read_text(encoding='utf-8')
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='main')
    body=ast.get_source_segment(text,node)
    assert body.count("'a1_worker.py'")==1
    body=body.replace("'a1_worker.py'","'a1_alias_worker.py'")
    scope=dict(original.__dict__)
    exec(compile(body,str(original.H/'a1_supervisor.py')+'::alias_worker_only','exec'),scope)
    try:scope['main']()
    except BaseException as error:
        original.save('A1_SUPERVISOR_FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()))
        raise
