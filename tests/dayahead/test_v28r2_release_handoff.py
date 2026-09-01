import json
from pathlib import Path

from tools.final_campaign.run_v28r2_april import REQUIRED_LAUNCH_GATES, verify_launch_gates


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_final_release_flags_authorize_only_april_local_preflight():
    flags = verify_launch_gates(OUT / "V28R2_IMPLEMENTATION_READY_FLAGS.json")
    assert all(flags[name] is True for name in REQUIRED_LAUNCH_GATES)
    assert flags["V28_BLOCK_001_STATUS"] == "RESOLVED"
    assert flags["APRIL_MONITOR_READY"] is True
    assert flags["APRIL_AUDITOR_READY"] is True
    assert flags["LOCAL_APRIL_HANDOFF_READY"] is True
    assert flags["APRIL_FULL_MONTH_PREFLIGHT_PASS"] is False
    assert flags["MAY_RUNNER_READY"] is False
    assert flags["MAY_FINAL_SCIENCE_COMPLETE"] is False
    assert flags["FINAL_GRID_SCIENCE_AUTHORIZED"] is False


def test_handoff_commands_are_exact_and_have_no_placeholders():
    text = (OUT / "V28R2_LOCAL_APRIL_EXECUTION_COMMANDS.md").read_text(encoding="utf-8")
    root = "/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend"
    assert text.count(f"cd '{root}'") == 5
    for script in (
        "prepare_2025_april_sources.sh", "run_2025_april_preflight.sh",
        "audit_2025_april_preflight.sh", "monitor_2025_april_preflight.sh",
    ):
        assert script in text
    assert "<" not in text and "PLACEHOLDER" not in text


def test_artifact_manifest_rehashes_every_listed_file():
    manifest = load("V28R2_ARTIFACT_SHA256.json")
    import hashlib
    for name, record in manifest["artifacts"].items():
        path = OUT / name
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
