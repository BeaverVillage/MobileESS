import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {Workbook} from '@oai/artifact-tool';
const root=path.resolve(import.meta.dirname,'..');
const preview=process.argv.includes('--preview');
const base=preview?path.join(root,'_work','preview'):root;
await fs.mkdir(base,{recursive:true});
const input=JSON.parse(await fs.readFile(path.join(root,'_work',preview?'tables_preview.json':'tables.json'),'utf8'));
const wb=Workbook.create();
const outputs=[];
const encode=v=>{const s=String(v);return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};
for(const [name,t] of Object.entries(input.tables).sort()){
 const sh=wb.worksheets.add(name.slice(0,31));
 const data=[t.headers,...t.rows];
 const range=sh.getRangeByIndexes(0,0,data.length,t.headers.length);
 range.values=data;
 // Public CSV export is not exposed in this runtime. Serialize the authored public range.values.
 const readback=range.values;
 if(JSON.stringify(readback)!==JSON.stringify(data))throw new Error('Artifact authoring changed a raw cell: '+name);
 const csv='\ufeff'+readback.map(r=>r.map(encode).join(',')).join('\r\n')+'\r\n';
 await fs.writeFile(path.join(base,name),csv,'utf8');
 outputs.push({filename:name,row_count:t.rows.length,sha256:crypto.createHash('sha256').update(csv).digest('hex'),source_files:t.source_files,description:t.description,status:'EXTRACTED_RAW_WITH_EXPLICIT_NA'});
}
await fs.writeFile(path.join(root,'_work',preview?'CSV_PREVIEW_VERIFICATION.json':'CSV_AUTHORING_VERIFICATION.json'),JSON.stringify({status:'PASS',method:'Artifact Tool worksheet range.values authoring and exact public-range readback before UTF-8 BOM CSV serialization',files:outputs},null,2));
console.log(JSON.stringify({status:'PASS',files:outputs.map(x=>({name:x.filename,rows:x.row_count}))}));
