"""Opt-in observed production worker. Completed days are never restarted."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--day", required=True)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    original = repo / "dayahead/artifacts/v40b_v40a_may_launch/days" / a.day
    if (original / "DAY_CERTIFICATE.json").exists():
        raise RuntimeError("COMPLETED_DAY_NO_RESTART_USE_OFFLINE_BACKFILL")
    from dayahead.paper_analysis.live import capture
    from dayahead.tools.run_v40b_campaign import day_worker
    with capture(repo / "dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt/days" / a.day / "live_capture"):
        day_worker(a.day)


if __name__ == "__main__":
    main()
