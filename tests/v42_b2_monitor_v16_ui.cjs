// Offline DOM test: meaningful absent values and certificate publication.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{constructor(){this.children=[];this.style={};this.open=false;}
replaceChildren(...x){this.children=x;}append(...x){this.children.push(...x);}addEventListener(k,f){this[k]=f;}}
const html=fs.readFileSync('v42_b2_monitor_v16/index.html','utf8'),ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(x=>x[1])),elements=new Map();
const document={getElementById(id){assert(ids.has(id));if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
createElement(){return new Element();},addEventListener(){}};
const state=JSON.parse(fs.readFileSync('tmp/b2_monitor_view_v16.json','utf8'));
const c=vm.createContext({document,Date,JSON,Math,Number,Array,String,Set,AbortController,console,
setTimeout:()=>0,clearTimeout(){},setInterval(){},fetch:async()=>({ok:true,json:async()=>state})});
const txt=e=>[e.textContent,...(e.children||[]).map(txt)].filter(x=>x!==undefined).join(' ');
vm.runInContext(html.split('<script>')[1].split('</script>')[0],c);
(async()=>{
await new Promise(r=>setImmediate(r));
assert.equal(elements.get('workers').children.length,3);assert.equal(elements.get('actual-rows').children.length,31);
const card=elements.get('workers').children[0];
assert.match(txt(card),/초기 정수해 탐색/);assert.match(txt(card),/인증 전/);
const visible=card.children.find(x=>x.className==='bounds');assert(visible,'UB and LB visible without expanding details');
assert.match(txt(visible),/검증된 UB/);assert.match(txt(visible),/독립 LB/);assert.match(txt(visible),/—/);
assert.match(txt(visible),/초기 해 검증 후 독립 하한 계산/);
assert(!ids.has('gate'));assert(!html.includes('fingerprints_identical'));
vm.runInContext("snapshot.worker_slots[0].UB=.8;snapshot.worker_slots[0].independent_Global_LB=.6;snapshot.worker_slots[0].global_gap_display={available:true,value:.25,reason:'현재 날짜 인증서 확인'};snapshot.worker_slots[0].bound_status={UB_reason:'현재 날짜 독립 인증서 확인',LB_reason:'현재 날짜 독립 인증서 확인'};render();",c);
const updated=elements.get('workers').children[0];assert.match(txt(updated),/25.00%/);assert.match(txt(updated),/0.800000/);assert.match(txt(updated),/0.600000/);
const detail=updated.children.at(-1);detail.open=true;detail.toggle();vm.runInContext('render()',c);
assert.equal(elements.get('workers').children[0].children.at(-1).open,true);
vm.runInContext('failed=true;clock()',c);assert.equal(elements.get('connection-alert').hidden,false);
console.log('PASS: visible UB/LB, exact missing-value reasons, initial seed phase, certified Gap updates, retained details and stale connection.');
})().catch(e=>{console.error(e);process.exitCode=1;});
