"""Tiny no-model checks of reusable physical cache and all-stage support."""
from dataclasses import asdict, replace
import json

import pytest

from test_v42_a_stage_fast_active import fixture
from v42_job_capability import Option
from v42_a_stage_domain_v2.active import ActivePolicy, prepare_fast_active
from v42_a_stage_domain_v2.census import write
from v42_a_stage_domain_v2.fast_census import (save_physical_cache, load_physical_cache,
                                             required_supports, verify_partition)


def test_representative_only_cache_roundtrip_byte_identity_and_class_mapping(tmp_path):
    data=fixture(2)
    _,domains,ledger=prepare_fast_active(data,policy=ActivePolicy(0,0))
    frozen=tmp_path/"DATA.pkl";frozen.write_bytes(b"EXPLICIT_TINY_FROZEN_IDENTITY")
    receipt=save_physical_cache("2025-05-17",data,domains,frozen,tmp_path)
    restored=load_physical_cache("2025-05-17",data,frozen,tmp_path)
    assert receipt["representatives"]==1 and receipt["jobs"]==2
    assert restored["j0"] is restored["j1"]
    assert restored["j0"].sha==domains["j0"].sha
    assert tuple(restored["j0"])==tuple(domains["j0"])
    assert verify_partition(ledger)["PASS"]
    frozen.write_bytes(b"CHANGED")
    with pytest.raises(ValueError,match="CACHE_IDENTITY_DRIFT"):
        load_physical_cache("2025-05-17",data,frozen,tmp_path)


def test_cache_byte_corruption_and_exact_class_drift_rejected(tmp_path):
    data=fixture();_,domains,_=prepare_fast_active(data,policy=ActivePolicy(0,0))
    frozen=tmp_path/"DATA.pkl";frozen.write_bytes(b"TINY")
    save_physical_cache("2025-05-19",data,domains,frozen,tmp_path)
    changed=list(data);changed[7]=dict(classes={"other":["j0"]})
    with pytest.raises(ValueError,match="CLASS_MEMBERSHIP_DRIFT"):
        load_physical_cache("2025-05-19",tuple(changed),frozen,tmp_path)
    path=tmp_path/"2025-05-19/PHYSICAL_DOMAIN_CACHE.pkl.gz"
    with path.open("ab") as handle:handle.write(b"CORRUPTION")
    with pytest.raises(ValueError,match="CACHE_BYTE_DRIFT"):
        load_physical_cache("2025-05-19",data,frozen,tmp_path)


def test_every_validated_stage_option_is_mandatory_without_importing_bounds(tmp_path):
    data=fixture();folder=tmp_path/"MAY10"
    for component,start in (("rho",0),("migration_count",1),("shift_magnitude",2)):
        option=Option(start,"A",(("A",start,start+4),))
        payload=dict(PASS=True,selected_jobs={"j0":asdict(option)},
            physical=dict(PASS=True,all_original_rows=dict(PASS=True)),
            historical_bound_DO_NOT_IMPORT=999,objective_lock_DO_NOT_IMPORT=123)
        write(folder/component/"INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json",payload)
    supports=required_supports("2025-05-10",data,tmp_path,tmp_path)
    assert {value.name for value in supports}=={"VERIFIED_rho","VERIFIED_migration_count","VERIFIED_shift_magnitude"}
    _,_,ledger=prepare_fast_active(data,policy=ActivePolicy(0,0),required_support=supports)
    assert {(0,"A"),(1,"A"),(2,"A")}<=ledger["stay_pools"]["c"].active
    assert all(not hasattr(value,"bound") and not hasattr(value,"lock") for value in supports)


def test_two_static_dates_restore_mutable_native_routing_without_building_model(tmp_path,monkeypatch):
    from v42_a_stage_domain_v2 import fast_census,fast_backend
    from v42_a_stage_domain_v2.domain import physical_domain
    from v42_a_stage_domain_v2.active import grid_priority_hash
    import v42_pr134_b1.native as native
    import v42_may01.prepare as original
    import v42_boundary.model as boundary
    import v42_exact.validation as validation
    data=fixture();domain=physical_domain(data[1]["j0"],data[2]["j0"],data[3])
    frozen=tmp_path/"frozen";frozen.mkdir();(frozen/"DATA.pkl").write_bytes(b"TINY_STATIC_IDENTITY")
    census=tmp_path/"census";production=tmp_path/"production";output=tmp_path/"output"
    output.mkdir();write(output/"ACTIVE_DOMAIN_POLICY.json",dict(same_site_radius=0,extra_stay_per_class=0,migration_extra_seeds=0))
    monkeypatch.setattr(fast_census,"CENSUS",census);monkeypatch.setattr(fast_census,"PRODUCTION",production)
    monkeypatch.setattr(fast_census,"load_frozen",lambda day:(data,frozen))
    monkeypatch.setattr(fast_census,"required_supports",lambda day,value:())
    ranking=dict(PASS=True,score_sha256=grid_priority_hash({}),ranking_only=True)
    monkeypatch.setattr(fast_backend,"frozen_grid_priority",lambda coefficients,resources:({},ranking))
    saved=(original.native_coefficients,boundary.planning_grid,validation.check)
    calls=[]
    def fake_bind(bundle,inputs,folder):
        calls.append(bundle["day"] if "day" in bundle else str(inputs))
        original.native_coefficients=lambda certificate:()
        boundary.planning_grid=lambda *args:None
        validation.check=lambda *args:None
        return None,None,()
    monkeypatch.setattr(native,"bind",fake_bind)
    for day in ("2025-05-10","2025-05-12"):
        write(production/"inputs"/day/"NATIVE_INPUT.json",data[0])
        write(census/("MAY"+day[-2:]+"_STATIC_DOMAIN_CENSUS.json"),dict(hard_valid_STAY_starts=len(domain.stays),
            candidate_counts_by_class=[dict(class_id="c",physical_domain_sha256=domain.sha,
                old_S0=dict(stay_options=4),new_hard_physical=dict(stay_options=len(domain.stays),
                    total_physical_path_multiplicity=domain.count))]))
        result,_,_=fast_census.produce_day(day,output,tmp_path/"static")
        assert result["native_model_builds"]==0 and result["optimize_calls"]==0
        assert (original.native_coefficients,boundary.planning_grid,validation.check)==saved
    assert len(calls)==2
