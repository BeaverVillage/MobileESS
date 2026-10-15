"""Native0 month audit rejects cross-date reuse and accidental heavy work."""
from copy import deepcopy

import pytest

from tools.audit_v42_table_v_month import ARMS, DAYS, native0_guard, validate_context, validate_month_rows, validate_dispatch


def month_rows():
    return [dict(day=day, arm=arm, initial_state_sha="initial:" + day,
        typed_input_sha="input:" + day, public_D0_epoch_seconds=index * 86400,
        source_identity=dict(case_sha="case:" + day))
        for index, day in enumerate(DAYS) for arm in ARMS]


def test_all_124_dates_and_arm_bindings_are_required():
    rows = month_rows()
    assert validate_month_rows(rows)
    with pytest.raises(ValueError, match="EXACTLY_ONE_BINDING"):
        validate_month_rows(rows[:-1])
    with pytest.raises(ValueError, match="EXACTLY_ONE_BINDING"):
        validate_month_rows(rows + rows[:1])


def test_one_arm_cannot_borrow_another_date_initial_state():
    rows = month_rows()
    next(r for r in rows if r["day"] == "2025-05-12" and r["arm"] == "B3")["initial_state_sha"] = "initial:2025-05-01"
    with pytest.raises(ValueError, match="SHARE_CURRENT_DATE_CASE_AND_INITIAL"):
        validate_month_rows(rows)


@pytest.mark.parametrize("field", ["initial_state_sha", "typed_input_sha", "public_D0_epoch_seconds"])
def test_four_consistent_arms_still_cannot_clone_may01_into_may12(field):
    rows = month_rows()
    may01 = next(r for r in rows if r["day"] == "2025-05-01")
    for row in rows:
        if row["day"] == "2025-05-12":
            row[field] = may01[field]
    with pytest.raises(ValueError, match="MUST_NOT_CLONE"):
        validate_month_rows(rows)


def context_fixture():
    day = "2025-05-02"
    begin = 90000.
    return dict(day=day, manifest=dict(day=day, source_sha="source", initial_record={"path": "initial"},
        identity={"initial_state_sha": "initial", "case_sha": "case"},
        source_native_record={"path": f"D:/archive/raw/{day}/NATIVE_INPUT_TEMPLATE_B1.json"},
        time_axis=dict(evaluation_begin_seconds=begin, evaluation_end_seconds=begin + 86400,
            native_slot_zero_seconds=begin - 21600, slots=96, native_model_slots=[24, 120]),
        forecast_receipt=dict(target_day=day, day_begin_seconds=begin,
            forecast_source_available_seconds=begin, actual_future_UIDs_used=False, forecast_receipt_sha="forecast")),
        state=dict(day=day, begin_epoch_seconds=begin, common_initial_state_sha="initial",
            running=[], pending=[dict(uid="observed", submit_seconds=begin)]),
        input_audit=dict(a_input_sha="typed"), data=({}, {}, {}, None, {}, {}, {}, {}))


def test_same_day_public_context_rejects_future_job_or_other_day_native(monkeypatch):
    from v42_integration import d0_a_planning
    monkeypatch.setattr(d0_a_planning, "input_fingerprint", lambda _: "typed")
    context = context_fixture()
    assert validate_context(context, "2025-05-02", flex=False)["slots"] == 96
    changed = deepcopy(context)
    changed["state"]["pending"][0]["submit_seconds"] += 1
    with pytest.raises(ValueError, match="FUTURE_UNKNOWN_UID"):
        validate_context(changed, "2025-05-02", flex=False)
    changed = deepcopy(context)
    changed["manifest"]["source_native_record"]["path"] = "D:/archive/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json"
    with pytest.raises(ValueError, match="INDEPENDENT_SAME_DAY"):
        validate_context(changed, "2025-05-02", flex=False)


def test_native0_guard_rejects_model_construction_and_restores_class():
    import gurobipy as gp
    original = gp.Model.__init__
    with native0_guard() as (calls, _):
        with pytest.raises(RuntimeError, match="FORBIDDEN:model_builds"):
            gp.Model()
    assert gp.Model.__init__ is original and calls["model_builds"] == 1


def test_dispatch_rejects_placeholder_target_or_missing_b3_k48():
    check = dict(day="2025-05-12", source_sha="source", source_identity={"case_sha": "case"},
        initial_state_sha="initial", typed_input_sha="input")
    dispatch = dict(check, arm="B3", input_sha="input",
        stages=["A1", "M1", "K48_M1", "A2", "M2", "K48_M2", "ACTUAL96", "FRESH_AC96"],
        executors={"ARM": "tests.placeholder:run"})
    with pytest.raises(ValueError, match="REAL_EXECUTOR_TARGETS"):
        validate_dispatch(dispatch, check, "B3")
    dispatch["stages"].remove("K48_M2")
    with pytest.raises(ValueError, match="STAGE_SEQUENCE"):
        validate_dispatch(dispatch, check, "B3")


def test_source_receipt_hashing_is_allowed_but_future_bundle_json_parsing_is_blocked(tmp_path):
    from v42_integration.release_initial_states import read, record
    bundle = tmp_path / "ACTUAL_INPUT_BUNDLE.json"
    bundle.write_text('{"future_UID": "must_not_enter_planning"}')
    with native0_guard() as (calls, io):
        assert record(bundle)["bytes"] > 0
        with pytest.raises(RuntimeError, match="FORBIDDEN:private_future_reads"):
            read(bundle)
    assert calls["private_future_reads"] == 1
    assert str(bundle).replace("\\", "/") in io["provenance_actual_bundle_byte_paths"]
