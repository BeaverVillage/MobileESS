"""After final Native completion, serialize Native0 audit and report generation."""
import subprocess
from tools.adaptive_perf_v3.bootstrap import *

def main():
    path=DOCS/'FINAL_STATE.json'
    while True:
        if path.exists():
            try:state=read(path)
            except (ValueError,OSError):time.sleep(2);continue
            assert state['PASS'],state.get('error');break
        time.sleep(2)
    for module in ('final_audit','legacy_candidates','final_report'):
        print(json.dumps(dict(start_post_native_step=module,time=r.timestamp())),flush=True)
        rc=subprocess.run([sys.executable,'-X','utf8','-m','tools.adaptive_perf_v3.'+module],cwd=DEVELOPMENT_ROOT).returncode
        assert rc==0,('POST_NATIVE_FAILED',module,rc)
    print(json.dumps(dict(PASS=True,Native=state['Native_used'],post_native_audit_and_report_complete=True)),flush=True)
if __name__=='__main__':main()
