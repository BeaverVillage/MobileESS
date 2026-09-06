"""Read only exposed V40J development evidence and raw April footer metadata."""
from io import BytesIO
import json
import pickle
import zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *

def pm(f):
    y=f.runtime_seconds.to_numpy(float);p=f.point.to_numpy(float);d=y-p
    return {'N':len(f),'target_Q50':float(np.median(y)),'prediction_Q50':float(np.median(p)),
      'underprediction':float((d>0).mean()),'mean_signed_error':float(d.mean()),'MAE':float(abs(d).mean()),'pinball50':float(abs(d).mean()/2)}

def main():
    assert git('rev-parse','HEAD').decode().strip()==START
    OUT.mkdir(parents=True,exist_ok=True)
    tracked=git('ls-files','-z').decode().split('\0')
    stat={n:[(ROOT/n).stat().st_size,(ROOT/n).stat().st_mtime_ns] for n in tracked if n and (ROOT/n).exists() and not n.startswith(('dayahead/v40k/','dayahead/artifacts/v40k_'))}
    jp={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for base in [J,ROOT/'dayahead/v40j'] for p in base.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    write('V40K_START_STATE.json',{'HEAD':START,'created_at':now(),'protected_tracked_metadata':stat,'V40J_file_sha256':jp,
      'initial_status':git('status','--porcelain').decode(),'prior_J_receipt_preserved':(J/'V40J_FINAL_COMMIT_RECEIPT.json').exists(),
      'authority_missing':72,'PF':.95,'Q_control':'NO','electrical_generation':'HOLD','B0_B1_B2_B3':'NO','FULL_MAY':'NO'},immutable=True)
    with Firewall('preflight',files=[ARCHIVE]):
        f=pq.read_table(BytesIO((J/'DEVELOPMENT_GPU_ROWS.parquet').read_bytes())).to_pandas()
        results={}
        for cid in ['C1_L1','C1_Q50','C2_MIXTURE']:
            v=pq.read_table(BytesIO((J/(cid+'_N100_R0_VALIDATION.parquet')).read_bytes())).to_pandas()
            print('PREDICTION_COLUMNS',list(v.columns),flush=True)
            results[cid]={'columns':list(v.columns)}
        write('V40K_FORENSIC_INPUT_SCHEMA.json',results)
        with zipfile.ZipFile(ARCHIVE) as z:
            with z.open(APRIL) as stream:
                p=pq.ParquetFile(stream);entries=[]
                for i in range(p.num_row_groups):
                    bounds={}
                    for col in ['submit_time','start_time','end_time']:
                        ix=p.schema_arrow.get_field_index(col);s=p.metadata.row_group(i).column(ix).statistics
                        bounds[col]={'min':str(s.min),'max':str(s.max),'null_count':s.null_count} if s and s.has_min_max else None
                    entries.append({'row_group':i,'rows':p.metadata.row_group(i).num_rows,'bounds':bounds})
        write('V40K_APRIL_FOOTER_AVAILABILITY.json',{'member':APRIL,'row_groups':entries,'schema':str(p.schema_arrow),
          'runtime_status_end_result_arrays_read':False,'only_footer_metadata':True})
        print('FOOTER_AVAILABILITY',json.dumps(entries),flush=True)
        write('V40K_HISTORY_DECISION.json',{'longer_raw_history_added':False,'decision':'Defer longer-history expansion to a later revision; retain immutable V40J normalized authority.',
          'GPU_rows':len(f),'submit_range':[str(f.submit_time.min()),str(f.submit_time.max())],
          'end_known_range':[str(f.end_time.min()),str(f.end_time.max())],
          'new_holdout_reason':'March08-21 labels were present in V40J normalized cache and exact C0 reproduction training. April01-07 has only footer exposure, so is the new point-selection period.'},immutable=True)
if __name__=='__main__':main()
