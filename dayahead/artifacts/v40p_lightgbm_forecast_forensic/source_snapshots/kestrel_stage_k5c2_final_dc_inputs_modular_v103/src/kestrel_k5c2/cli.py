from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .config import load_config
from .context import Context
from .pipeline import run


def main():
    ap = argparse.ArgumentParser(description="Stage K5-C2 final AI data-center optimization inputs")
    ap.add_argument("--config", required=True)
    ap.add_argument("--project-root", default="")
    ap.add_argument("--processed-root", default="")
    ap.add_argument("--raw-root", default="")
    args = ap.parse_args()
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    if args.project_root:
        cfg["paths"]["project_root"] = args.project_root
    if args.processed_root:
        cfg["paths"]["processed_root"] = args.processed_root
    if args.raw_root:
        cfg["paths"]["raw_root"] = args.raw_root
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(cfg["paths"]["result_parent"]) / f"stage_k5c2_{stamp}"
    ctx = Context(cfg, config_path, config_path.parent.parent, run_dir, run_dir / "outputs", run_dir / "predictions", run_dir / "scenarios", run_dir / "reports", run_dir / "logs")
    review = run(ctx)
    print(f"RESULT_DIR={run_dir}")
    print(f"REVIEW_ZIP={review}")


if __name__ == "__main__":
    main()
