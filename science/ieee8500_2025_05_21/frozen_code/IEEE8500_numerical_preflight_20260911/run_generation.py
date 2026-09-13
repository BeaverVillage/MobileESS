import time
from concurrent.futures import ProcessPoolExecutor
from electrical_engine import *
def main():
    baseline();start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as p:
        rows=[]
        for r in p.map(generate_slot,range(96)):
            rows.append(r)
            if len(rows)%8==0:print('COEFFICIENT_SLOTS',len(rows),'/96',flush=True)
    save(H/'COEFFICIENT_GENERATION.json',dict(status='GENERATED_PENDING_VALIDATION',wall_seconds=time.perf_counter()-start,workers=4,slots=rows,total_signed_solves=11520,old_coefficients_reused=False,controls=60,AIDC_independent_Q_variables=0))
if __name__=='__main__':main()
