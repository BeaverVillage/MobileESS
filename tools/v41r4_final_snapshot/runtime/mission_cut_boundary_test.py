"""Exercise the restoration limit and early exit without an electrical solve."""
from contextlib import nullcontext
from types import SimpleNamespace as NS
from pathlib import Path
from unittest.mock import patch
import tempfile,numpy as np
import mission_ac_cut_restore as cut
from fast_prepare import ROOT,record
from dayahead.paper_analysis.storage import write_json

def scenario(pass_at):
    count=dict(fresh=0,solve=0)
    trajectory=NS(slots=[]);context=NS(electrical=NS(voltage=None),coefficients=[NS(control_names=[])],v41_electrical_certificate={})
    one=NS(slot=0,actual_value=1.,hard_limit=2.,margin=0.,coefficients=[],anchor_controls=[],relation='<=',
        violation_type=NS(value='fixture'),payload=lambda:{'test_cut':True})
    def fresh(**kwargs):
        k=count['fresh'];count['fresh']+=1
        return NS(summary=dict(physical_violation=k!=pass_at))
    def adapted(original,replacements,extra):
        def solve(power,current,ctx):
            count['solve']+=1
            extra['add_grid'](None,ctx.coefficients,[],1.)
            return dict(status='PASS',trajectory=current,solver={'fixture':True})
        return solve
    replacement=dict(digest=lambda x:'unchanged',_discrete_signature=lambda x:'fixed',
        make_frozen=lambda *a:NS(source_schedule_sha256='frozen'),run_fresh_opendss=fresh,
        corrected_mapping=nullcontext,extract_ac_violations=lambda x:['violation'],
        local_fresh_ac_restoration_cuts=lambda **kw:([one],{}),control_matrix=lambda *a:np.zeros((1,0)),
        add_grid=lambda *a:(None,{}),_add_restoration_cuts=lambda m,n,v,c:(list(c),0),
        _add_restoration_recourse_trust_region=lambda *a,**kw:0,adapted=adapted,
        validate_physics=lambda x:dict(status='PASS'),controls_from_trajectory=lambda *a:np.zeros((1,0)))
    with patch.multiple(cut,**replacement):
        try:
            _,result=cut.restore('TEST','B3',[],{'pcc':np.zeros((1,0))},trajectory,context,Path(tempfile.mkdtemp(prefix='cut-boundary-')))
            status=result['status']
        except RuntimeError as e:
            assert str(e)=='INHERITED_AC_RESTORATION_FAILED_CLOSED';status='FAIL_CLOSED'
    return dict(status=status,**count)

if __name__=='__main__':
    assert cut.K_MAX==10
    exhausted=scenario(None);assert exhausted==dict(status='FAIL_CLOSED',fresh=11,solve=10)
    immediate=scenario(0);assert immediate==dict(status='PASS',fresh=1,solve=0)
    first=scenario(1);assert first==dict(status='PASS',fresh=2,solve=1)
    last=scenario(10);assert last==dict(status='PASS',fresh=11,solve=10)
    write_json(ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4/audit/mission/AC_CUT_BOUNDARY_TEST.json',
        dict(status='PASS',helper=record(Path(cut.__file__)),mocked_control_flow_only=True,
            exhausted=exhausted,already_feasible=immediate,first_correction=first,last_allowed_correction=last))
    print('CAP10_FAIL_CLOSED_AND_EARLY_EXIT_PASS')
