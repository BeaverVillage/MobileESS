"""Raw footer census: no runtime/status columns or April row payload decoded."""
import zipfile
import pyarrow.parquet as pq
from .contracts import ARCHIVE
from .firewall import ReadFirewall, member_allowed, write

def main():
    fw=ReadFirewall('raw_footer_census',[ARCHIVE]).install()
    try:
        rows=[]
        with zipfile.ZipFile(ARCHIVE) as z:
            for name in sorted(z.namelist()):
                if not member_allowed(name,shadow=True):continue
                with fw.open_member(z,name,shadow=True,metadata_only=True) as stream:
                    p=pq.ParquetFile(stream)
                    bounds=[]
                    index=p.schema_arrow.names.index('submit_time')
                    for group in range(p.num_row_groups):
                        stat=p.metadata.row_group(group).column(index).statistics
                        if stat and stat.has_min_max:bounds.append([str(stat.min),str(stat.max)])
                    rows.append({'member':name,'row_count':p.metadata.num_rows,'row_groups':p.num_row_groups,
                                 'submit_time_footer_bounds':bounds,'schema':str(p.schema_arrow)})
        write('V40J_RAW_RUNTIME_FOOTER_CENSUS.json',{'members':rows,'rows':sum(r['row_count'] for r in rows),
          'runtime_or_status_columns_read':False,'April_row_payload_read':False,
          'ZIP_compressed_bytes_note':'Parquet footer seeks may decompress ZIP bytes internally, but no row value arrays are materialized; metadata-only opens are separately logged.'})
        print('RAW_FOOTER_CENSUS',len(rows),sum(r['row_count'] for r in rows))
    finally:fw.close()

if __name__=='__main__':main()
