import json
from pathlib import Path

import numpy as np
import pytest

from dayahead.v28r2.formulation import _mess_authority
from dayahead.v28r2.mess_replay import replay_mess
from dayahead.v29.mess_availability import CONNECTION_DELAY_SLOTS, normalize_mess_record
from dayahead.v29.source_namespace import (
    SourceBinding, SourceNamespace, SourceNamespaceFirewall,
    materialize_traffic_mobility_namespaces,
)


REPO = Path(__file__).resolve().parents[2]


def _record():
    mode = ["CONNECTED"] * 96
    available = [True] * 96
    location = ["STA01"] * 96
    energy = [0.0] * 96
    mode[1] = "TRANSIT"
    available[1] = False
    location[1] = "TRANSIT_ROUTE_01"
    energy[1] = 2.5
    return {
        "mess_id": "MESS01", "mode": mode, "available": available,
        "location": location, "safe_travel_energy_kwh": energy,
        "initial_energy_kwh": 760.0,
    }


def test_connection_delay_is_exactly_one_slot_and_shared_by_da_actual_pi():
    normalized = normalize_mess_record(_record())
    assert CONNECTION_DELAY_SLOTS == 1
    assert normalized["mode"][2] == "CONNECTION_DELAY"
    assert normalized["available"][2] is False
    assert normalized["mode"][3] == "CONNECTED"
    assert normalized["available"][3] is True

    records = []
    for index in range(4):
        record = _record()
        record["mess_id"] = f"MESS{index + 1:02d}"
        record["location"] = [value.replace("STA01", f"STA{index + 1:02d}") for value in record["location"]]
        records.append(record)
    da = _mess_authority({"mess": records})
    assert all(value["connection_delay_slots"] == [2] for value in da.values())
    p = np.zeros((96, 4)); q = np.zeros((96, 4))
    p[2, :] = 10.0; p[3, :] = 10.0
    actual = replay_mess(p, q, records)
    assert np.all(actual.p_exec_kw[2] == 0.0)
    assert np.all(actual.p_exec_kw[3] == 10.0)


def test_actual_namespace_cannot_open_or_enter_prefreeze_hash(tmp_path: Path):
    common = tmp_path / "common.json"; common.write_text("{}\n", encoding="utf-8")
    forecast = tmp_path / "forecast.json"; forecast.write_text("{}\n", encoding="utf-8")
    actual = tmp_path / "actual.json"; actual.write_text("{}\n", encoding="utf-8")
    firewall = SourceNamespaceFirewall({
        "common": SourceBinding("common", common, SourceNamespace.COMMON_STATIC),
        "forecast": SourceBinding("forecast", forecast, SourceNamespace.DAYAHEAD_FORECAST),
        "actual": SourceBinding("actual", actual, SourceNamespace.ACTUAL_REALIZED),
    })
    before = firewall.prefreeze_source_sha256()
    actual.write_text('{"changed":true}\n', encoding="utf-8")
    assert firewall.prefreeze_source_sha256() == before
    assert firewall.actual_open_count == 0
    with pytest.raises(RuntimeError, match="BEFORE_SCHEDULE_FREEZE"):
        firewall.read_bytes("actual")
    schedule_sha = "a" * 64
    firewall.freeze_schedule(schedule_sha)
    with pytest.raises(RuntimeError, match="BEFORE_SCHEDULE_FREEZE"):
        firewall.read_bytes("actual", verified_schedule_sha256="b" * 64)
    assert firewall.read_bytes("actual", verified_schedule_sha256=schedule_sha)
    assert firewall.actual_open_count == 1


def test_combined_traffic_source_is_split_into_strict_namespaces(tmp_path: Path):
    combined = REPO / "cache/v28r2_campaign_sources/april_2025/days/2025-04-01/traffic_mobility.json"
    outputs = materialize_traffic_mobility_namespaces(combined, tmp_path)
    forecast = json.loads(outputs["traffic_forecast.json"].read_text(encoding="utf-8"))
    actual = json.loads(outputs["traffic_actual.json"].read_text(encoding="utf-8"))
    engineering = json.loads(outputs["engineering_mobility.json"].read_text(encoding="utf-8"))
    assert "actual_volume" not in forecast and "mess" not in forecast
    assert set(actual) == {"day", "actual_volume", "traffic_actual_namespace"}
    assert "actual_volume" not in engineering and "forecast_q50_volume" not in engineering
