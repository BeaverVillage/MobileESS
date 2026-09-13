import sys,time,json,traceback,os,tempfile
sys.dont_write_bytecode=True
from frozen_binding import HOME,context,save,read,ROOT
import gurobipy as gp
calls=[]
(HOME/'runtime_tmp').mkdir(exist_ok=True)
tempfile.tempdir=str(HOME/'runtime_tmp')
os.environ['TMP']=os.environ['TEMP']=tempfile.tempdir
def forbidden(*args,**kwargs):calls.append(time.time());raise RuntimeError('PRODUCTION_OPTIMIZATION_FORBIDDEN_DURING_BINDING_RECONSTRUCTION')
gp.Model.optimize=forbidden
gp.Model.computeIIS=forbidden
def guard(event,args):
    if event=='open' and len(args)>2:
        p,mode,flags=args
        if isinstance(p,(str,bytes)) and isinstance(flags,int) and flags& (1|2|64|512|1024):
            from pathlib import Path
            path=Path(os.fsdecode(p)).resolve()
            if not path.is_relative_to(HOME.resolve()):raise PermissionError('AUDIT_WRITE_OUTSIDE_NEW_WORKSPACE:'+str(path))
sys.addaudithook(guard)
try:
    print('READ_FROZEN_MAY21_INPUTS',flush=True);ctx=context()
    save('INPUT_BINDING.json',dict(files=ctx.input_sources,rows=ctx.candidate_rows))
    from structural_projection import compile_projection
    from dayahead.v41 import temporal_restore
    temporal_restore.BASE_COUNT=1325555;temporal_restore.RESTORED_COUNT=16392;temporal_restore.TOTAL_COUNT=1341947
    with temporal_restore.activate():
        print('BUILD_REFERENCE_NON_ELECTRICAL_PROJECTION',flush=True);a=compile_projection(ctx,'V41R4_REFERENCE')
        print('BUILD_IEEE8500_NON_ELECTRICAL_PROJECTION',flush=True);b=compile_projection(ctx,'IEEE8500_B1')
    same=a==b
    save('STRUCTURAL_DIFFERENTIAL.json',dict(status='PASS' if same else 'FAIL_CLOSE',reference=a,IEEE8500=b,all_fields_identical=same,optimization_calls=len(calls),Fresh_calls=0,scope='Original non-electrical joint-model projection; electrical constraints excluded explicitly.'))
    assert same
    print('STRUCTURAL_DIFFERENTIAL_PASS',json.dumps({k:a[k] for k in ['variable_count','linear_constraints','general_constraints','matrix_nonzeros','cohort_count']}),flush=True)
except BaseException as e:
    save('attempt_history/FAILURE_'+str(time.time_ns())+'.json',dict(status='FAIL_CLOSE',error=type(e).__name__,message=str(e),traceback=traceback.format_exc(),optimization_calls=len(calls)));raise
