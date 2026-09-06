from __future__ import annotations
import argparse
from pathlib import Path
from .config import load
from .pipeline import run

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); args=ap.parse_args(); cp=Path(args.config).resolve(); ctx=load(cp,cp.parent.parent); review=run(ctx); print(f"Review ZIP: {review}")
if __name__=="__main__": main()
