"""Meaningful Native0 regressions for source routes, fixed Q and bound scope."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import gzip
import json

import numpy as np
import pytest

from v42_integration.mess_scaling import (STAGES, TWO_ORDER, build_scale_case,
    fixed_injections, beam_paths, audit_original_sites, load_routes,
    validate_pilot_inputs,validate_response_coefficients,validate_scale_identity,validate_grid_authority,constructor_summary)
from v42_integration.m_engine import file_record
from v42_integration.unified_contract import load_contracts, require_global_bound


@pytest.fixture
def source(tmp_path):
    sites = ["IDC%02d" % i for i in range(1,13)]+["STA%02d" % i for i in range(1,13)]
    rows = []
    for s in sites:
        for d in sites:
            for depart in (0,24,48,72,94):
                rows.append(dict(origin_service_id=s,destination_service_id=d,departure_slot_15=depart,
                    travel_slots_15min=0 if s==d else 1,connection_ready_slots_15min=0 if s==d else 2,
                    energy_safe_kwh=0. if s==d else 10.,traffic_forecast_sha="a"*64,
                    road_origin_node="TN_"+s,road_destination_node="TN_"+d,
                    route_link_ids=[] if s==d else ["R_"+s+"_TRANSIT", "R_TRANSIT_"+d]))
    p=tmp_path/"ROUTE_TABLE.json.gz"
    p.write_bytes(gzip.compress(json.dumps(dict(service_ids=sites,routes=rows)).encode()))
    battery=dict(minimum=440.,maximum=1080.,initial=760.,terminal=760.,p_limit=300.,pcs_kva=400.,
                 eta_charge=.95,eta_discharge=.95,dt_hours=.25)
    initial=dict(MESS01="STA01",MESS02="STA12",MESS03="STA08",MESS04="STA06")
    bundle=dict(route_table=file_record(p),battery=battery,initial_MESS_sites=initial,traffic_forecast_sha="a"*64)
    stay=dict(initial_sites=initial,moves=[],time_axis=list(range(96)),dt_seconds=900,
        connection_site={u:[s]*96 for u,s in initial.items()},
        routes={u:[sites.index(s)*96+t for t in range(96)] for u,s in initial.items()},
        P_kW={u:[0.]*96 for u in initial},Q_kvar={u:[-10. if u=="MESS02" else 20. if u=="MESS04" else 0.]*96 for u in initial},
        SOC_kWh={u:[760.]*97 for u in initial},Mode={u:[0.]*96 for u in initial})
    return bundle,stay,sites


def build(source, stage="S1"):
    bundle,stay,_=source
    return build_scale_case(bundle,stage,stay,bindings=load_contracts()["bindings"])


def test_source_only_full96_and_four_physical_vehicles(source):
    scale=build(source)
    assert scale.sites == TWO_ORDER[:5]
    assert scale.active == ("MESS01","MESS03")
    assert scale.inactive == ("MESS02","MESS04")
    assert scale.manifest["slots"] == 96 and scale.manifest["physical_units"] == 4
    assert scale.manifest["new_direct_road_arcs"] == 0
    assert all(r.source in scale.sites and r.destination in scale.sites for r in scale.routes)
    assert all(row["route_link_ids"] for _,_,row in scale.route_records)
    assert scale.manifest["inactive_current_source_physical_replay"]["PASS"]


def test_inactive_nonzero_q_outside_optimized_sites_is_retained_once(source):
    scale=build(source)
    p,q=fixed_injections(scale,source[2])
    assert "STA06" not in scale.sites
    assert np.array_equal(q["STA12"],np.full(96,-10.))
    assert np.array_equal(q["STA06"],np.full(96,20.))
    assert np.array_equal(q["STA01"],np.zeros(96))
    assert sum(np.sum(v) for v in p.values()) == 0
    assert sum(np.sum(v) for v in q.values()) == 960


def test_deterministic_nested_stages_and_reduced_sha_not_original(source):
    stages={s:build(source,s) for s in STAGES}
    assert all(len(c.active)==STAGES[s][0] and len(c.sites)==STAGES[s][1] for s,c in stages.items())
    assert set(stages["S1"].sites)<set(stages["S2"].sites)<set(stages["S3"].sites)<set(stages["S4"].sites)
    assert all(c.case_sha!=c.bindings["case_sha"] for c in stages.values())
    assert len({c.case_sha for c in stages.values()})==7
    assert build(source).case_sha==stages["S1"].case_sha


def test_route_and_stay_corruption_are_rejected(source,tmp_path):
    bundle,stay,_=source
    corrupt=deepcopy(stay);corrupt["Q_kvar"]["MESS02"][0]=1000.
    with pytest.raises(ValueError,match="PHYSICAL_REPLAY"):
        build_scale_case(bundle,"S1",corrupt,bindings=load_contracts()["bindings"])
    corrupt=deepcopy(stay);corrupt["connection_site"]["MESS04"][0]="IDC01"
    with pytest.raises(ValueError,match="LOCATION"):
        build_scale_case(bundle,"S1",corrupt,bindings=load_contracts()["bindings"])
    path=Path(bundle["route_table"]["path"]);path.write_bytes(path.read_bytes()+b"drift")
    with pytest.raises(ValueError,match="BYTE_DRIFT"):
        load_routes(bundle)


def test_shared_physical_and_forecast_contract_drift_rejected(source):
    binding=dict(load_contracts()["bindings"]);binding["physical_sha"]="0"*64
    with pytest.raises(ValueError,match="SHARED_ANCHOR_DRIFT"):
        build_scale_case(source[0],"S1",source[1],bindings=binding)
    bundle=deepcopy(source[0]);bundle["traffic_forecast_sha"]="b"*64
    with pytest.raises(ValueError,match="FORECAST_SHA_DRIFT"):
        build_scale_case(bundle,"S1",source[1],bindings=load_contracts()["bindings"])


def test_beam_stay_move_corridors_original_path_grammar(source):
    scale=build(source)
    pools,audit=beam_paths(scale,width=16)
    assert audit["Native_optimize_calls"]==0 and audit["score_is_not_bound_or_hard_feasibility"]
    from v42_native.mess_domain import build_domain
    graph=build_domain(scale.sites,scale.initial,scale.routes,scale.battery,96)
    for u,paths in pools.items():
        corridors=set(); depths=set()
        for path in paths:
            site,tick=scale.initial[u],0;moves=[]
            for k in path:
                a=graph.arcs[k]
                assert a[:2]==(site,tick)
                site,tick=a[2:4]
                if a[-1] is not None:moves.append(a)
            assert tick==96
            depths.add(len(moves))
            if moves:corridors.add(moves[0][2])
        assert 0 in depths and any(d>0 for d in depths)
        assert len(corridors)>=2


def test_restricted_bound_cannot_be_original_or_reduced_global():
    case="c"*64
    with pytest.raises(ValueError,match="RESTRICTED_BOUND"):
        require_global_bound(dict(case_sha=case,value=.4,scope="RESTRICTED_ROUTE_POOL"),case)
    assert require_global_bound(dict(case_sha=case,value=.4,scope="REDUCED_CASE_GLOBAL"),case)==.4
    with pytest.raises(ValueError,match="RESTRICTED_BOUND"):
        require_global_bound(dict(case_sha=case,value=.4,scope="REDUCED_CASE_GLOBAL"),case,original_case=True)


def test_original24_audit_source_mapping_and_signed_vector(source,tmp_path):
    bundle,_,sites=source
    p=tmp_path/"mapping.csv"
    text="service_node_id,electrical_host_bus,asset_type,mess_transformer_kva,host_source_distance\n"
    text+="".join(f"{s},BUS_{i},{'IDC' if s.startswith('IDC') else 'STA'},750,{i}\n" for i,s in enumerate(sites))
    p.write_text(text,encoding="utf8")
    certificate=tmp_path/"certificate.json"
    certificate.write_text(json.dumps(dict(input_identity=dict(identity=dict(inputs=dict(service_PCC_mapping=file_record(p)))))),encoding="utf8")
    names=tuple(f"mess_{v}_kw[{s}]" if v=="p" else f"mess_q_kvar[{s}]" for s in sites for v in ("p","q"))
    c=SimpleNamespace(control_names=names,current_matrix=np.arange(len(names)*2,dtype=float).reshape(len(names),2)-50,
                      coefficient_sha256="d"*64)
    audit=audit_original_sites(bundle,electrical_certificate=file_record(certificate),mapping=p,coefficients=[c]*96)
    assert audit["site_count"]==24 and audit["source_generated_sites"] is False
    assert sum(r["AIDC_coexists"] for r in audit["rows"])==12
    assert audit["rows"][0]["sensitivity"]["signed_min"]<0
    assert audit["rows"][-1]["sensitivity"]["signed_max"]>0


def test_mutated_aidc_power_cannot_retain_old_anchor_string(source):
    from v42_integration.a_engine import digest
    anchor=dict(FULL_feasible=True,selected_jobs={},AIDC_P_by_site={"AIDC01":[1.]*96},
        AIDC_Q_by_site={"AIDC01":[.3]*96},CC4_service={},CC4_carryout={},anonymous_resource_envelope={})
    fields=("selected_jobs","AIDC_P_by_site","AIDC_Q_by_site","CC4_service","CC4_carryout","anonymous_resource_envelope")
    anchor["aidc_anchor"]=digest({k:anchor[k] for k in fields})
    anchor["AIDC_P_by_site"]["AIDC01"][0]=1000.
    with pytest.raises(ValueError,match="A_FULL_FIXED_ANCHOR_DRIFT"):
        validate_pilot_inputs(build(source),anchor,[],None)


def test_manifest_and_fixed_schedule_mutations_rejected(source):
    scale=build(source);validate_scale_identity(scale)
    scale.manifest["charging_sites"][0]="STA11"
    with pytest.raises(ValueError,match="MANIFEST_CONTENT_DRIFT"):
        validate_scale_identity(scale)
    scale=build(source);scale.stay_plan["Q_kvar"]["MESS02"][0]=0.
    with pytest.raises(ValueError,match="MUTABLE_STATE_DRIFT"):
        validate_scale_identity(scale)


def test_response_descriptors_arrays_and_bytes_revalidated(tmp_path):
    from v42_integration.production_case import FIELDS
    path=tmp_path/"response.npz"
    packet={k:np.zeros((96,1)) for k in FIELDS}
    packet.update(control_names=np.array(["mess_p_kw[IDC01]"]),branch_names=np.array(["line.a"]),
        anchor_control=np.zeros((96,1)),transformer_ratings=np.array([np.nan]),rating_a=np.array([1.]))
    np.savez(path,**packet);receipt=file_record(path);binding={"response_sha":receipt["sha256"]}
    coefficients=[]
    for tick in range(96):
        coefficients.append(SimpleNamespace(**{k:packet[k][tick].copy() for k in FIELDS},slot=tick,
            control_names=tuple(packet["control_names"]),branch_names=tuple(packet["branch_names"]),
            anchor=packet["anchor_control"][tick].copy(),transformer_ratings=(None,),current_denominators_A=np.array([1.]),
            coefficient_sha256=receipt["sha256"]))
    assert validate_response_coefficients(coefficients,receipt,binding)["PASS"]
    coefficients[0].current_matrix[0]=100.
    with pytest.raises(ValueError,match="ARRAY_CONTENT_DRIFT"):
        validate_response_coefficients(coefficients,receipt,binding)
    with pytest.raises(ValueError,match="RESPONSE_SHA_DRIFT"):
        validate_response_coefficients(coefficients,receipt,{"response_sha":"a"*64})


def test_transformer_current_disable_rejected_before_source_or_native_read():
    authority=SimpleNamespace(frozen=True,require_all_transformer_currents=False)
    with pytest.raises(ValueError,match="ALL_ORIGINAL_TRANSFORMER_CURRENT_ROWS"):
        validate_grid_authority(authority,bundle=None,electrical_certificate=None,
            thermal_receipt=None,coefficients=None)


def test_constructor_receipt_whitelist_serializes_without_self_reference():
    receipt=dict(model_build_seconds=1.,model_size_before_solve={"binary":2},
        route_move_arcs=3,physical_prescreen={"PASS":True,"state_sha":"a"*64})
    receipt["original_native_constructor_receipt"]=receipt
    summary=constructor_summary(receipt)
    assert json.loads(json.dumps(summary))["route_move_arcs"]==3
    assert "original_native_constructor_receipt" not in summary


def test_stage_anchor_changes_require_supervisor_and_new_case_sha(source):
    from v42_integration.mess_scaling import require_stage_bindings
    shared=load_contracts()["bindings"]
    stage=dict(shared,aidc_anchor="1"*64,mess_anchor="2"*64)
    with pytest.raises(ValueError,match="SHARED_ANCHOR_DRIFT"):
        require_stage_bindings(stage)
    assert require_stage_bindings(stage,stage)==stage
    a=build_scale_case(source[0],"S1",source[1],bindings=stage,expected_stage_bindings=stage,planning_stage="M2")
    assert a.case_sha!=build(source).case_sha
    bad=dict(stage,physical_sha="3"*64)
    with pytest.raises(ValueError,match="COMMON_SOURCE_CONTRACT_DRIFT"):
        require_stage_bindings(bad,bad)


def test_outward_support_encloses_exact_fraction_box_vertices():
    from fractions import Fraction
    from itertools import product
    from v42_integration.mess_scaling import affine_support_upper
    W=np.array([[1e-13,-.1,1.],[-.2,1e13,-1.],[0.,0.,0.]])
    lo=np.array([-600.,-800.,0.]);hi=np.array([600.,800.,1.])
    bound=affine_support_upper(W,lo,hi)
    for i,row in enumerate(W):
        exact=max(sum(Fraction(float(a))*Fraction(float(x)) for a,x in zip(row,vertex))
                  for vertex in product(*zip(lo,hi)))
        assert Fraction(float(bound[i]))>=exact


def test_full_stay_handoff_complete_grid_alias_and_content_sha(source,tmp_path):
    from v42_integration.mess_scaling import full_stay_handoff
    from v42_integration.coordinator import _full_m
    bundle,stay,sites=source
    stay=dict(stay,SOC=stay["SOC_kWh"],P_by_site={s:[0.]*96 for s in sites},
        Q_by_site={s:[0.]*96 for s in sites})
    path=tmp_path/"stay.json";path.write_text(json.dumps(stay),encoding="utf8")
    plan=full_stay_handoff(path)
    assert plan["Q_by_site"]["STA06"]==[20.]*96
    assert plan["Q_by_site"]["STA12"]==[-10.]*96
    assert _full_m(dict(FULL_validated=True,mess=plan))==plan


def test_captured_a_cannot_pair_with_another_valid_input_mess_anchor():
    from v42_integration.mess_scaling import validate_captured_a_input_mess
    bindings=load_contracts()["bindings"]
    expected=dict(bindings,aidc_anchor="1"*64,mess_anchor="2"*64)
    captured=dict(expected,aidc_anchor="0"*64)
    case=SimpleNamespace(unified_bindings=captured,grid=SimpleNamespace(fixed_mess={"plan_sha":"2"*64}))
    assert validate_captured_a_input_mess(case,{"plan_sha":"2"*64},expected)["PASS"]
    with pytest.raises(ValueError,match="COMMON_BINDINGS_DRIFT:mess_anchor"):
        validate_captured_a_input_mess(case,{"plan_sha":"3"*64},dict(expected,mess_anchor="3"*64))
    case.grid.fixed_mess={"plan_sha":"4"*64}
    with pytest.raises(ValueError,match="CAPTURED_INPUT_MESS_ANCHOR_DRIFT"):
        validate_captured_a_input_mess(case,{"plan_sha":"2"*64},expected)


def test_exact_native_compression_senses_constants_and_no_epsilon_deletion():
    from scipy import sparse
    from v42_integration.mess_scaling import compress_native_grid_rows,verify_native_grid_compression
    A=sparse.csr_matrix([[1.,0.],[1.,0.],[1.,0.],[1.,0.],[1.,0.],
                        [0.,0.],[0.,0.],[0.,1e-15],[0.,0.]])
    rhs=np.array([.5,.5,.7,-.5,-.7,0.,-1.,0.,0.])
    sense=np.array(["<","<","<",">",">","<","<","<","="])
    lo=np.array([-1.,-1.]);hi=np.array([1.,1.])
    proof=compress_native_grid_rows(A,rhs,sense,lo,hi)
    assert proof["reason"].tolist()==[0,1,2,0,2,4,0,0,0]
    assert proof["certificate"]["coefficient_epsilon_deletions"]==0
    assert verify_native_grid_compression(A,rhs,sense,lo,hi,proof)["PASS"]


def test_compression_keeps_unbounded_max_endpoint_and_uses_finite_min_for_negative_rho():
    from scipy import sparse
    from v42_integration.mess_scaling import compress_native_grid_rows
    A=sparse.csr_matrix([[0.,1.],[0.,-1.],[1.,-1.]])
    lo=np.array([-1.,0.]);hi=np.array([1.,np.inf])
    proof=compress_native_grid_rows(A,[10.,1.,2.],["<"]*3,lo,hi)
    assert proof["reason"].tolist()==[0,3,3]
    assert np.isinf(proof["support"][0])


def test_compression_same_integer_and_continuous_box_feasible_region_exact_fraction():
    from scipy import sparse
    from fractions import Fraction
    from itertools import product
    from v42_integration.mess_scaling import compress_native_grid_rows
    dense=np.array([[1.,-.25],[1.,-.25],[1.,-.25],[-1.,.5],[-1.,.5],
                    [.1,.2],[0.,-1.],[0.,0.],[1.,0.]])
    rhs=np.array([.75,1.,.75,1.,1.2,10.,1.,0.,1.])
    sense=np.array(["<"]*8+[">"])
    proof=compress_native_grid_rows(sparse.csr_matrix(dense),rhs,sense,[-1.,0.],[1.,1.])
    def feasible(ids,point):
        for i in ids:
            value=sum(Fraction(float(a))*Fraction(float(x)) for a,x in zip(dense[i],point))
            bound=Fraction(float(rhs[i]))
            if sense[i]=="<" and value>bound or sense[i]==">" and value<bound:return False
        return True
    for point in product((-1.,0.,1.),(0.,.25,.5,.75,1.)):
        assert feasible(range(len(rhs)),point)==feasible(proof["keep"],point)
    assert proof["certificate"]["variables_or_bounds_changed"] is False


def test_compression_certificate_rejects_original_rhs_bounds_or_proof_mutation():
    from scipy import sparse
    from v42_integration.mess_scaling import compress_native_grid_rows,verify_native_grid_compression
    A=sparse.csr_matrix([[1.,0.],[1.,0.],[0.,-.5]])
    rhs=np.array([.2,.4,1.]);sense=np.array(["<"]*3)
    lo=np.array([-1.,0.]);hi=np.array([1.,1.])
    proof=compress_native_grid_rows(A,rhs,sense,lo,hi)
    corrupt=deepcopy(proof);corrupt["representative"][1]=2
    with pytest.raises(ValueError,match="REMOVAL_WITNESS_DRIFT"):
        verify_native_grid_compression(A,rhs,sense,lo,hi,corrupt)
    with pytest.raises(ValueError,match="CERTIFICATE_DRIFT"):
        verify_native_grid_compression(A,rhs,sense,lo,np.array([2.,1.]),proof)
    with pytest.raises(ValueError,match="CERTIFICATE_DRIFT"):
        verify_native_grid_compression(A,rhs+1e-12,sense,lo,hi,proof)


def test_compression_rejects_noncanonical_duplicate_column_dyadic_terms():
    from scipy import sparse
    from v42_integration.mess_scaling import compress_native_grid_rows
    A=sparse.csr_matrix((np.array([1.,2.**-54]),np.array([0,0]),np.array([0,2])),shape=(1,1))
    assert not A.has_canonical_format
    with pytest.raises(ValueError,match="CANONICAL_NATIVE_CSR_REQUIRED"):
        compress_native_grid_rows(A,[1.],["<"],[0.],[1.])


def test_vectorized_support_is_bit_identical_to_scalar_tiny_ulp_inf_zero_and_overflow():
    from scipy import sparse
    from v42_integration.mess_scaling import compress_native_grid_rows
    W=np.array([[1.,2.**-53,-.1,0.],[-1.,-2.**-53,.1,0.],
        [1e-300,-1e-300,0.,0.],[1e308,1e308,-1e308,0.],
        [0.,0.,0.,1.],[0.,0.,0.,-1.],[0.,0.,0.,0.],
        [.2,-.3,1e-15,0.],[.2,-.3,1e-15,0.]])
    A=sparse.csr_matrix(W)
    # Explicit signed zero is stored and skipped exactly; it must not round a sum.
    A=sparse.hstack([A,sparse.csr_matrix((np.array([-0.]),np.array([0]),np.array([0,1]+[1]*8)),shape=(9,1))],format="csr")
    rhs=np.array([1.,-1.,0.,1e308,1.,1.,0.,np.nextafter(.8,np.inf),.8])
    senses=np.array(["<",">","<","<","<","<","=","<","<"])
    lower=np.array([-1.,-1.,-1.,0.,-np.inf]);upper=np.array([1.,1.,1.,np.inf,np.inf])
    with np.errstate(over="ignore",invalid="ignore"):
        scalar=compress_native_grid_rows(A,rhs,senses,lower,upper,support_backend="SCALAR_REFERENCE")
        vector=compress_native_grid_rows(A,rhs,senses,lower,upper,support_backend="VECTORIZED_EXACT")
    for key in ("support","keep","reason","representative"):
        assert scalar[key].dtype==vector[key].dtype
        assert scalar[key].tobytes()==vector[key].tobytes()
    assert scalar["certificate"]==vector["certificate"]


def test_vectorized_scalar_proof_identity_random_sparse_native_row_order_and_guards():
    from scipy import sparse
    from v42_integration.mess_scaling import compress_native_grid_rows
    rng=np.random.default_rng(42)
    dense=rng.normal(size=(40,11));dense[rng.uniform(size=dense.shape)<.35]=0.
    dense[1]=dense[0];dense[3]=dense[2]
    A=sparse.csr_matrix(dense);rhs=rng.normal(size=40)
    sense=np.array(["<",">","="]*13+["<"])
    lo=np.full(11,-800.);hi=np.full(11,600.)
    scalar=compress_native_grid_rows(A,rhs,sense,lo,hi,support_backend="SCALAR_REFERENCE")
    vector=compress_native_grid_rows(A,rhs,sense,lo,hi)
    assert scalar["certificate"]==vector["certificate"]
    for key in ("support","keep","reason","representative"):
        assert scalar[key].tobytes()==vector[key].tobytes()
    for bad in (np.nan,np.inf):
        corrupt=A.copy();corrupt.data[0]=bad
        with pytest.raises(ValueError,match="NATIVE_MATRIX_OR_DOMAIN_DRIFT"):
            compress_native_grid_rows(corrupt,rhs,sense,lo,hi)
    lo[0]=np.nan
    with pytest.raises(ValueError,match="NATIVE_MATRIX_OR_DOMAIN_DRIFT"):
        compress_native_grid_rows(A,rhs,sense,lo,hi)



def test_compression_benchmark_requires_original_s1_two_equal_budgeted_native_caps(source,tmp_path):
    from v42_integration.mess_scaling import run_original_pilot
    budget=SimpleNamespace(solve=lambda *args,**kwargs:None,remaining=lambda:39.)
    kwargs=dict(coefficients=[],grid_authority=None,aidc_anchor={},all_sites=[],coefficient_source={},
        physical_bundle={},electrical_certificate={},thermal_receipt={},budget=budget,output=tmp_path,
        seconds=20.,compare_exact_compression=True)
    with pytest.raises(RuntimeError,match="TWO_EQUAL_CAPS_BUDGET_REQUIRED"):
        run_original_pilot(build(source),**kwargs)
    kwargs["budget"]=SimpleNamespace(solve=lambda *args,**kwargs:None,remaining=lambda:60.)
    with pytest.raises(ValueError,match="BENCHMARK_S1_ORIGINAL"):
        run_original_pilot(build(source),**dict(kwargs,native0=True))
    with pytest.raises(ValueError,match="BENCHMARK_S1_ORIGINAL"):
        run_original_pilot(build(source,"S2"),**kwargs)
    with pytest.raises(ValueError,match="BENCHMARK_S1_ORIGINAL"):
        run_original_pilot(build(source),**dict(kwargs,grid_compression="EXACT_NATIVE_BLOCK"))


@pytest.mark.parametrize("second_bound,final_lb",[(.2,.2),(.32,None)])
def test_benchmark_mock_only_identical_starts_fresh_bounds_and_original_best_preserved(monkeypatch,tmp_path,second_bound,final_lb):
    """No native model: verifies the pair's solver-state/ledger transport policy."""
    from scipy import sparse
    from v42_integration import mess_scaling as m, m_engine
    from v42_common_mess import model as common_model
    from v42_native import solver
    A=sparse.csr_matrix([[1.]])
    d=dict(names=np.array(["rho_max"]),rhs=np.array([1.]),sense=np.array(["<"]),lower=np.array([0.]),
        upper=np.array([1.]),types=np.array(["C"]),objective=np.array([1.]),constant=np.array(0.),row_names=np.array(["fake_native0"]))
    case=SimpleNamespace(A=A,d=d,original_A=A,original_d=d,case_sha="a"*64,output=tmp_path)
    scale=SimpleNamespace(stage="S1",case_sha="a"*64,bindings=load_contracts()["bindings"])
    state=[]
    class Model:
        Params=SimpleNamespace()
        Runtime=20.;Work=1.;Status=9;NodeCount=1;SolCount=1;ObjBound=.1;NumStart=1
        def getVars(self):return [0]
        def reset(self,clearall):state.append(("reset",clearall))
        def setAttr(self,name,variables,value):
            if name=="Start":self.start=value.copy();state.append(("start",value.copy()))
        def update(self):pass
        def getAttr(self,name):return np.array(self.start) if name=="Start" else np.array([.3 if self.ObjBound==.1 else .35])
    model=Model()
    class Budget:
        stage_context={"case_sha":"a"*64}
        def remaining(self):return 100.
        def solve(self,model,label,cap,callback):
            state.append(("solve",label,cap,self.stage_context.copy()))
            model.ObjBound=.1 if label.endswith("ORIGINAL") else second_bound
            return dict(solver="FAKE_NATIVE0_NO_OPTIMIZE",label=label,Native_Runtime=20.)
    class Bank:
        def __init__(self,case):self.best=None;self.best_moving=None
        def offer(self,point,cert):
            if self.best is None or cert["Global_UB"]<self.best[1]["Global_UB"]:self.best=(point.copy(),cert)
        def fields(self):return dict(BEST_GLOBAL_UB=None if self.best is None else self.best[1]["Global_UB"],BEST_MOVING_FEASIBLE_UB=None)
        def save(self,*args):pass
    class Sampler:
        def phase(self,name):pass
        def receipt(self):return {"scope":"MOCK_ONLY_NO_NATIVE_MODEL"}
    def strict(case,path):
        with np.load(path) as z:ub=float(z["point"][0])
        return dict(PASS=True,Global_UB=ub)
    monkeypatch.setattr(m_engine,"IncumbentBank",Bank)
    monkeypatch.setattr(m_engine,"strict_full",strict)
    monkeypatch.setattr(m_engine,"PathGraph",lambda case:SimpleNamespace(moving=lambda point:False))
    monkeypatch.setattr(m,"full_vehicle_replay",lambda *args:({"PASS":True},{"fake_native0_plan":True}))
    monkeypatch.setattr(common_model,"memory_observation",lambda:{"RAM_available":16*1024**3})
    monkeypatch.setattr(solver,"assert_milp",lambda model:{"linear_constraints":1,"nonzeros":1})
    monkeypatch.setattr("v42_integrated.matrix.arrays",lambda model:(A,d))
    def compression(*args,output,**kwargs):
        output.mkdir(parents=True,exist_ok=True)
        (output/"FULL96_COMPRESSION_CERTIFICATE.json").write_text('{"mock_only":true}')
        return SimpleNamespace(A=A,d=d,original_A=A,original_d=d)
    monkeypatch.setattr(m,"compress_existing_native_grid_model",compression)
    result=m._same_model_compression_benchmark(model,case,scale,[],None,Budget(),np.array([.4]),
        {"PASS":True},tmp_path,20.,Sampler(),0.)
    starts=[entry[1] for entry in state if entry[0]=="start"]
    calls=[entry for entry in state if entry[0]=="solve"]
    assert starts==[[.4],[.4]] and [entry[1] for entry in state if entry[0]=="reset"]==[1,1]
    assert len(calls)==2 and calls[0][1].endswith("ORIGINAL") and calls[1][1].endswith("COMPRESSED")
    assert [entry[2] for entry in calls]==[20.,20.]
    assert result["BEST_GLOBAL_UB"]==.3 and result["BEST_FULL_point_variant"]=="ORIGINAL"
    assert result["Global_LB"]==final_lb and result["variants"][0]["Global_LB"]==.1
    assert result["variants"][1]["BEST_GLOBAL_UB"]==.35
    assert result["first_solver_incumbent_given_to_second_solver"] is False
    assert all(row["actual_Start_readback"]["PASS"] for row in result["variants"])
    if final_lb is None:assert result["bound_rejection"]=="SECOND_SOLVER_BOUND_EXCEEDS_BEST_SAME_CASE_FULL_UB"
