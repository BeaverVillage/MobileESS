from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import pytest
from tests.dayahead.test_v41r1_migration import job
from tests.dayahead.test_v40g_joint import Wan
from dayahead.v40g.domain import options,deviation
from dayahead.v41r1.migration_factor import compile,selected


@pytest.mark.parametrize('start,duration',[(96,44),(24,6),(115,10)])
def test_all_explicit_to_compressed_and_all_compressed_to_explicit(start,duration):
    ctx,row=job(start,duration)
    sites=('AIDC01','AIDC02','AIDC03')
    cap=SimpleNamespace(aidc_ids=sites,site_capacity={s:2 for s in sites},
        eligible_racks=lambda s,g:(SimpleNamespace(rack_pool_id=s+'_LP01'),))
    opts=options(row,cap,Wan(),{});costs=[deviation(row,o) for o in opts]
    model=gp.Model();model.Params.OutputFlag=0;load=defaultdict(gp.LinExpr);wan=defaultdict(gp.LinExpr)
    f=compile(model,row,opts,costs,7,load,wan);represented=set()
    # The reverse enumeration covers every allowed compressed route/arrival
    # product plus every stay. Constraints disallow every other combination.
    reverse=list(f['stay'])
    for source,destination in f['routes']:
        for dest,restart in f['arrivals']:
            if dest==destination:
                from dayahead.v40g.domain import Option
                reverse.append(Option(dest,start,restart+f['remaining'],f['checkpoint'],restart-2,restart-1,source))
    assert set(reverse)==set(opts) and len(reverse)==len(opts)
    for desired in reverse:
        for opt,v in f['stay'].items():v.LB=v.UB=int(opt==desired)
        for pair,v in f['routes'].items():v.LB=v.UB=int(desired.migrated and pair==(desired.initial_site,desired.site))
        for pair,v in f['arrivals'].items():v.LB=v.UB=int(desired.migrated and pair==(desired.site,desired.transfer_end+1))
        model.optimize();assert model.Status==GRB.OPTIMAL
        out=selected(f,row);represented.add(out);assert out==desired
        assert f['migration'].getValue()==int(out.migrated)
        assert f['deviation'].getValue()==costs[opts.index(out)]
        assert f['tie'].getValue()==8*(opts.index(out)+1)
        for t in range(96):
            for site in sites:
                expected=sum(row['requested_GPU'] for s,a,b in out.segments(row) if s==site and a<=t+24<b)
                assert load[t,site].getValue()==expected
            assert wan[t+24].getValue()==int(out.migrated and out.transfer_start<=t+24<out.transfer_end)
    assert represented==set(opts);model.dispose()


@pytest.mark.parametrize('cross_midnight,equal',[(False,False),(True,False),(True,True)])
def test_full_five_priority_optimum_decisions_and_occupancy_equal(tmp_path,cross_midnight,equal):
    from tests.dayahead.test_v41_scalar_interface import fixture
    from dayahead.v41.reserve import bind
    from dayahead.paper_analysis.storage import write_json,sha
    from dayahead.v41r1.migration import attach
    from dayahead.v40g.optimizer import solve
    ctx,row,snapshot=fixture();start=96;duration=40 if cross_midnight else 18
    row.update(start_slot=start,end_slot=start+duration,safe_duration_slots=duration,safe_duration_seconds=duration*900.)
    row=attach([row])[0]
    c=ctx.coefficients[0];cs=[]
    for t in range(96):
        w=np.array([.1,.1 if equal else .4,0.]) if t<75 else np.array([.1 if equal else .4,.1,0.])
        cs.append(replace(c,slot=t,current_matrix=np.column_stack([w/10,w/10]),flow_p_matrix=np.array([w,w])))
    ctx.coefficients=tuple(cs);ctx.wan=Wan();ctx.elapsed={}
    snapshot['PENDING_JOB_Q90_SECONDS']={'one':duration*900.};snapshot['PENDING_JOB_DURATION_SLOTS']={'one':duration}
    path=tmp_path/'ML.json';write_json(path,snapshot);bind(ctx,path,sha(path))
    pcc=np.zeros((96,2));pcc[72:min(96,72+duration),0]=1
    explicit=solve([row],pcc,ctx,tmp_path/'explicit',factorize=False)
    compressed=solve([row],pcc,ctx,tmp_path/'compressed',factorize=True)
    np.testing.assert_allclose(explicit['OBJECTIVE_VECTOR'],compressed['OBJECTIVE_VECTOR'],rtol=0,atol=1e-9)
    assert explicit['jobs']==compressed['jobs']
    assert np.array_equal(explicit['GPU'],compressed['GPU']) and np.array_equal(explicit['PCC'],compressed['PCC'])
    assert explicit['secondary_migration_optimum']==compressed['secondary_migration_optimum']
    assert explicit['quaternary_tie_optimum']==compressed['quaternary_tie_optimum']
    if not equal:assert compressed['secondary_migration_optimum']==1
