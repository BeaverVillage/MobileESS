"""Capture the requested full regression suite without diagnostic benchmarks."""
from .common import *
import re

def run():
    started=time.perf_counter()
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (OUT/'TEST_OUTPUT.txt').open('wb') as f:
        result=subprocess.run([os.sys.executable,'-m','pytest','-q'],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
    text=(OUT/'TEST_OUTPUT.txt').read_text(encoding='utf8',errors='replace')
    summary=next((x.strip() for x in reversed(text.splitlines()) if re.search(r'\d+ (passed|failed|error)',x)),'NO_SUMMARY')
    dump('PYTEST_RECEIPT.json',dict(command='python -m pytest -q',exit_code=result.returncode,summary=summary,seconds=time.perf_counter()-started,
        output_sha256=sha(OUT/'TEST_OUTPUT.txt'),benchmark_optimize_calls=0,
        unmet_experimental_check='Auxiliary terminal objective equality NOT_EVALUATED_USER_STOP; tested explicit unmeasured gate, algebraic identity and existing-point mappings.'))
    print(summary,flush=True)
    if result.returncode:raise SystemExit(result.returncode)

if __name__=='__main__':run()
