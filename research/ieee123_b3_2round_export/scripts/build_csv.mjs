import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import { Workbook } from '@oai/artifact-tool';
const base=path.dirname(fileURLToPath(import.meta.url));
if(process.argv.includes('--help-csv')) {
 const wb=Workbook.create();
 console.log(wb.help('csv',{include:'index,examples,notes',maxChars:3500}).ndjson);
} else {
 const input=JSON.parse(await fs.readFile(path.join(base,'EXTRACTED_TABLES.json'),'utf8'));
 const output=path.join(base,'deliverables','IEEE123_2ROUND_PAPER_CSV');
 await fs.mkdir(output,{recursive:true});
 const results=[];
 for (const [name,table] of Object.entries(input.tables)) {
  const wb=Workbook.create(); const sheet=wb.worksheets.add('Raw export');
  // Explicit text preserves full round-trip floating-point precision and IDs.
  // CSV has no workbook number formats or recalculating formula cells.
  const text=v=>v===null||v===undefined?'':typeof v==='boolean'?(v?'true':'false'):String(v);
  const matrix=[table.columns,...table.rows.map(r=>table.columns.map(c=>text(r[c])))];
  const range=sheet.getRangeByIndexes(0,0,matrix.length,table.columns.length);
  range.values=matrix;
  const captured=[];
  for(let start=0;start<matrix.length;start+=400)captured.push(...sheet.getRangeByIndexes(start,0,Math.min(400,matrix.length-start),table.columns.length).values);
  const timestampColumn=table.columns.indexOf('timestamp_AEST');
  if(timestampColumn>=0)for(let i=1;i<captured.length;i++) {
   if(!matrix[i][timestampColumn])continue;
   if(Date.parse(captured[i][timestampColumn])!==Date.parse(matrix[i][timestampColumn]))throw new Error('TIMESTAMP_INSTANT_DRIFT');
   // Artifact normalizes ISO timestamps to UTC; retain the requested AEST text.
   captured[i][timestampColumn]=matrix[i][timestampColumn];
  }
  if(JSON.stringify(captured)!==JSON.stringify(matrix)) {
   const row=matrix.findIndex((r,i)=>JSON.stringify(r)!==JSON.stringify(captured[i]));
   console.log(JSON.stringify({expected_rows:matrix.length,actual_rows:captured.length,row,expected:matrix[row],actual:captured[row]}));
   throw new Error('ARTIFACT_CELL_ROUNDTRIP_DRIFT:'+name);
  }
  const quote=v=>/[",\r\n]/.test(v)?'"'+v.replaceAll('"','""')+'"':v;
  const csv='\ufeff'+captured.map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
  const target=path.join(output,name+'.csv');
  try {const prior=await fs.readFile(target,'utf8');if(prior!==csv)throw new Error('EXISTING_EXPORT_DRIFT:'+name);}
  catch(e){if(e.code!=='ENOENT')throw e;await fs.writeFile(target,csv,{encoding:'utf8',flag:'wx'});}
  results.push({name:name+'.csv',rows:table.rows.length,columns:table.columns,artifact_cell_roundtrip:'PASS'});
  console.log('CSV_CREATED',name,table.rows.length,table.columns.length);
 }
 await fs.writeFile(path.join(base,'CSV_AUTHORING_CHECK.json'),JSON.stringify(results,null,2));
}
