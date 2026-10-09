"""Reproduce all LV diagnostics in a fresh directory, preserving frozen reports."""
from __future__ import annotations

import argparse
from pathlib import Path
from . import lv_sensitivity, lv_baseline_readback, verify_lv_sensitivity


def run(output):
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Reproduction requires a fresh or empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    lv_sensitivity.FOLDER=output
    verify_lv_sensitivity.FOLDER=output
    lv_sensitivity.run()
    lv_baseline_readback.run()
    print(verify_lv_sensitivity.verify()['status'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    run(parser.parse_args().output)
