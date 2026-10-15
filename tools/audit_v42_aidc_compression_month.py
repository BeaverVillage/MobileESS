"""Serial 31-day Native0 audit. Failures retain their log and continue dates."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.table_v_dates import require_day

PRIORITY=('2025-05-01','2025-05-10','2025-05-12','2025-05-25','2025-05-31')
DAYS=PRIORITY+tuple(f'2025-05-{n:02d}' for n in range(1,32) if f'2025-05-{n:02d}' not in PRIORITY)


def save(path,value):
    with path.open('w',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def tabulate(output,results):
    rows=[row for result in results for row in result.get('rows',[])]
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with (output/'AIDC_MAY31_COMPRESSION_NATIVE0.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        for row in sorted(rows,key=lambda r:(r['day'],r['arm'],r['stage'])):
            writer.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    return rows


def main(output,days=DAYS):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('MONTH_NATIVE0_EVIDENCE_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True);started=perf_counter();results=[]
    for day in days:
        require_day(day);folder=output/day;log=output/(day+'.log')
        print('MONTH_NATIVE0_DATE_BEGIN',day,flush=True)
        save(output/'PROGRESS.json',dict(current_day=day,finished_dates=len(results),total_dates=len(days),
            Worker=1,Threads=1,Native_calls=0,Heavy_approved=False))
        with log.open('x',encoding='utf8') as stream:
            completed=subprocess.run([sys.executable,'-u',str(ROOT/'tools/audit_v42_aidc_compression.py'),
                '--day',day,'--output',str(folder),'--matrix'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        result_path=folder/'RESULT.json'
        if completed.returncode or not result_path.is_file():
            tail=log.read_text(encoding='utf8')[-6000:]
            result=dict(day=day,status='FAILED_NATIVE0',returncode=completed.returncode,log=file_record(log),
                Native_calls=0,error=tail,rows=[dict(day=day,arm=arm,stage=stage,status='BLOCKED_NATIVE0_FAILURE',
                    Native_calls=0,blockers=[tail[-1500:]],compression_launchable=False)
                    for arm,stage in [('B1','A1'),('B3','A1'),('B3','A2')]])
            save(output/(day+'_FAILED.json'),result)
        else:
            result=json.loads(result_path.read_text(encoding='utf8'));result['result_record']=file_record(result_path)
        results.append(result);rows=tabulate(output,results)
        save(output/'MONTH_RESULTS.json',dict(results=results,Native_calls=0,Worker=1,Threads=1,
            complete_dates=len(results),expected_dates=len(days),rows=len(rows),
            matrix_PASS=sum(r['status']=='PASS_NATIVE0_MATRIX' for r in rows),
            A2_pending_M1=sum(r['status']=='BLOCKED_CURRENT_M1_REQUIRED' for r in rows),
            failures=[r['day'] for r in results if r.get('status')=='FAILED_NATIVE0'],
            wall_seconds=perf_counter()-started,Heavy_launch_authorized=False))
        print('MONTH_NATIVE0_DATE_END',day,'matrix_PASS',sum(r['status']=='PASS_NATIVE0_MATRIX' for r in rows),flush=True)
    save(output/'COMPLETE.json',dict(complete_dates=len(results),Native_calls=0,wall_seconds=perf_counter()-started,
        May02_May31_Heavy_executed=False,May31_launch_approved=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.output)
