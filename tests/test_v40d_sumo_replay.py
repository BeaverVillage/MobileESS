import pandas as pd
import numpy as np
import pytest
from dayahead.v40d_actual.traffic_audit import independent_route
from dayahead.v40d_actual.mess_replay import traverse
from dayahead.v40d_actual.contracts import ReplayError


def test_independent_lookup_advances_at_actual_entry_not_departure_bucket():
    values=np.full((288,2),301.)
    values[1,1]=500.
    table=pd.DataFrame([{"reduced_link_id":edge,"slot5":t,"final_tt_sec":values[t,i]} for t in range(288) for i,edge in enumerate(["a","b"])]).set_index(["reduced_link_id","slot5"])
    actual=traverse(["a","b"],0,["a","b"],values,lambda *_:0.,connection_delay_seconds=600)
    elapsed,rows=independent_route(["a","b"],0,table,"2025-05-01")
    assert elapsed==actual["actual_eta_seconds"]==801.
    assert rows[1]["SUMO_lookup_slot5"]==1
    assert rows[1]["actual_entry_timestamp"]=="2025-05-01T00:05:01+10:00"


def test_half_open_five_minute_exact_boundary_has_no_interpolation():
    table=pd.DataFrame([{"reduced_link_id":"a","slot5":0,"final_tt_sec":300.},
        {"reduced_link_id":"b","slot5":1,"final_tt_sec":2.}]).set_index(["reduced_link_id","slot5"])
    elapsed,rows=independent_route(["a","b"],0,table,"2025-05-01")
    assert elapsed==302. and rows[1]["SUMO_lookup_timestamp"]=="2025-05-01T00:05:00+10:00"


def test_missing_realized_link_never_uses_free_flow_fallback():
    table=pd.DataFrame([{"reduced_link_id":"a","slot5":0,"final_tt_sec":300.}]).set_index(["reduced_link_id","slot5"])
    with pytest.raises(ReplayError,match="LOOKUP_MISSING"):
        independent_route(["missing"],0,table,"2025-05-01")


def test_DA_ETA_fields_are_not_in_actual_mobility_dataflow():
    import inspect
    from dayahead.v40d_actual.mobility_inputs import actual_mobility
    source=inspect.getsource(actual_mobility)
    assert all(token not in source for token in ("Q50_ETA_seconds","Safe_ETA_seconds","route_q50_eta_sec","route_safe_eta_sec"))
