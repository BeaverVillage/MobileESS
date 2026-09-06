from __future__ import annotations
import argparse
from pathlib import Path
from .config import load_config
from .context import PipelineContext
from .pipeline import run_pipeline
from .utils import setup_logger

def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',required=True); p.add_argument('--package-root',required=True); a=p.parse_args()
    cp=Path(a.config).resolve(); root=Path(a.package_root).resolve(); ctx=PipelineContext.create(load_config(cp),root,cp); logger=setup_logger(ctx.log_dir/'execution.log')
    logger.info('Run tag: %s',ctx.run_tag); run_pipeline(ctx,logger)
if __name__=='__main__': main()
