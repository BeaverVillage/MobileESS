#!/usr/bin/env python3
from pathlib import Path
import json,sys
p=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True);rc=int(sys.argv[2]);msg=sys.argv[3] if len(sys.argv)>3 else ""
if rc and not (p/"_FAILURE.json").exists():
 (p/"_FAILURE.json").write_text(json.dumps({"stage":"V2044R12B1D1B2_JOINTMASTER_BUILD7BR9_LOSSLESS_CACHE_INDEX","status":"FAILED_TECHNICAL_BUILD7B_WRAPPER","exit_code":rc,"wrapper_error":msg,"future_actual_used_for_optimizer":False},indent=2)+"\n")
