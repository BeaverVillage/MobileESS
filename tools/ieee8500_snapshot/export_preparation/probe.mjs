import {Workbook} from '@oai/artifact-tool';
const w=Workbook.create();
console.log(await w.help('*',{search:'csv|CSV',include:'index,notes,examples',maxChars:8000}));
