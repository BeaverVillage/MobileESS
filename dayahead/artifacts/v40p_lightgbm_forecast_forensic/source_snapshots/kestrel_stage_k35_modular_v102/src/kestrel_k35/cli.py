from __future__ import annotations

import argparse
from pathlib import Path

from kestrel_k35.config import load_config
from kestrel_k35.context import PipelineContext
from kestrel_k35.logging_utils import configure_logging
from kestrel_k35.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--package-root", required=True)
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    package_root = Path(args.package_root).resolve()

    ctx = PipelineContext.create(
        load_config(config_path),
        package_root,
        config_path,
    )
    logger = configure_logging(ctx.log_dir / "execution.log")
    run_pipeline(ctx, logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
