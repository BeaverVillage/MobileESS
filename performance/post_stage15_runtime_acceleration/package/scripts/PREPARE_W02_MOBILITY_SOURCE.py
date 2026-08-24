#!/usr/bin/env python3
"""Run PR4's exact R12 mobility materializer on one frozen source chunk.

The frozen traffic numerical contract requires exact 576-origin contexts.
W02 has 2016 scored issues, so source preparation uses four causal 576-issue
contexts (2304 source issues total). Representative-week callers score 2016
issues; a pre-frozen full-month caller may explicitly score all 2304 issues.
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
 ap.add_argument("--candidate-id",default="W02_2025-01-13");ap.add_argument("--start-index",type=int,default=START)
 ap.add_argument("--scored-count",type=int,default=2016)
 ap.add_argument("--phase",choices=("traffic","full"),required=True)
 ap.add_argument("--base-work",default="/home/jaewon/mobile_ess_work")
 ap.add_argument("--cpu-workers",type=int,default=4)
 ap.add_argument("--stage2a-runtime-override")
 a=ap.parse_args()
 repo=Path(a.repo).resolve();out=Path(a.output_root).resolve()
 start=int(a.start_index);padded_end_excl=start+COUNT
 if not 1<=a.scored_count<=COUNT:raise RuntimeError("scored-count must be in [1,2304]")
 scored_end=start+a.scored_count-1
 mod=load(repo/"stage7/r12_representative_weeks/materialize_r12_common_mobility_cache.py")
 mod.required_issues=lambda _authority: np.arange(start,padded_end_excl,dtype=np.int64)
 # Main still requires an authority-root argument, but the monkeypatched selector
 # no longer reads representative-week burn-in ranges.
 sys.argv=[str(Path(__file__).name),
  "--authority-root",str(repo/"stage7/r12_representative_weeks"),
  "--output-root",str(out),"--base-work",str(Path(a.base_work).resolve()),
  "--batch-size","576","--phase",a.phase,"--cpu-workers",str(a.cpu_workers)]
 if a.stage2a_runtime_override:
  sys.argv.extend(["--stage2a-runtime-override",str(Path(a.stage2a_runtime_override).resolve())])
 rc=int(mod.main())
 if rc==0:
  rec={"status":"PASS","candidate_id":a.candidate_id,"phase":a.phase,"source_issue_first":start,"source_issue_last":padded_end_excl-1,
       "source_issue_count":COUNT,"scored_issue_first":start,"scored_issue_last":scored_end,
       "scored_issue_count":a.scored_count,"padding_issue_count":COUNT-a.scored_count,
       "padding_role":("NONE_ALL_SOURCE_ISSUES_SCORED" if a.scored_count==COUNT else "CAUSAL_SOURCE_CONTEXT_ONLY_NOT_SCORED_NOT_LOOKAHEAD"),
       "future_actual_used":False,"stage2a_runtime_override":a.stage2a_runtime_override}
  (out/f"REP_WEEK_MOBILITY_{a.phase.upper()}_AUTHORITY.json").write_text(json.dumps(rec,indent=2,sort_keys=True)+"\n")
  if a.candidate_id=="W02_2025-01-13":
   (out/f"A_B10_W02_MOBILITY_{a.phase.upper()}_AUTHORITY.json").write_text(json.dumps(rec,indent=2,sort_keys=True)+"\n")
 return rc
if __name__=="__main__":raise SystemExit(main())
