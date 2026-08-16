#!/usr/bin/env python3
"""Run PR4's exact R12 mobility materializer on W02 evaluation contexts.

The frozen traffic numerical contract requires exact 576-origin contexts.
W02 has 2016 scored issues, so source preparation uses four causal 576-issue
contexts (2304 source issues total). Only issues 3456..5471 are scored/read by
the controller. The extra 288 issue artifacts are unscored source-cache padding,
never optimizer lookahead.
"""
from __future__ import annotations
import argparse,importlib.util,json,sys
from pathlib import Path
import numpy as np

START=3456
PADDED_END_EXCL=5760
COUNT=2304
PR4="06a94bccc0a232ae7ea09cbc7b00962162c10f4d"

def load(path:Path):
 spec=importlib.util.spec_from_file_location("a_b10_r12_mobility",path)
 if spec is None or spec.loader is None:raise RuntimeError(path)
 m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--repo",required=True);ap.add_argument("--output-root",required=True)
 ap.add_argument("--phase",choices=("traffic","full"),required=True)
 ap.add_argument("--base-work",default="/home/jaewon/mobile_ess_work")
 ap.add_argument("--cpu-workers",type=int,default=4)
 a=ap.parse_args()
 repo=Path(a.repo).resolve();out=Path(a.output_root).resolve()
 mod=load(repo/"stage7/r12_representative_weeks/materialize_r12_common_mobility_cache.py")
 mod.required_issues=lambda _authority: np.arange(START,PADDED_END_EXCL,dtype=np.int64)
 # Main still requires an authority-root argument, but the monkeypatched selector
 # no longer reads representative-week burn-in ranges.
 sys.argv=[str(Path(__file__).name),
  "--authority-root",str(repo/"stage7/r12_representative_weeks"),
  "--output-root",str(out),"--base-work",str(Path(a.base_work).resolve()),
  "--batch-size","576","--phase",a.phase,"--cpu-workers",str(a.cpu_workers)]
 rc=int(mod.main())
 if rc==0:
  rec={"status":"PASS","phase":a.phase,"source_issue_first":START,"source_issue_last":PADDED_END_EXCL-1,
       "source_issue_count":COUNT,"scored_issue_first":3456,"scored_issue_last":5471,
       "scored_issue_count":2016,"padding_issue_count":288,
       "padding_role":"CAUSAL_SOURCE_CONTEXT_ONLY_NOT_SCORED_NOT_LOOKAHEAD",
       "future_actual_used":False}
  (out/f"A_B10_W02_MOBILITY_{a.phase.upper()}_AUTHORITY.json").write_text(json.dumps(rec,indent=2,sort_keys=True)+"\n")
 return rc
if __name__=="__main__":raise SystemExit(main())
