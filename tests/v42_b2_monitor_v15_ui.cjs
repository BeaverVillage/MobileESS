// Offline DOM source test. No browser or browser permission workaround.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.children=[];this.style={};this.attrs={};this.open=false;}
 replaceChildren(...x){this.children=x;}append(...x){this.children.push(...x);}
 setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,f){this[k]=f;}
}
const html=fs.readFileSync('v42_b2_monitor_v15/index.html','utf8'),elements=new Map();
const ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(x=>x[1]));
const document={getElementById(id){assert(ids.has(id),'missing HTML id '+id);if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
 createElement(){return new Element();},addEventListener(){}};
const state=JSON.parse(fs.readFileSync('tmp/b2_monitor_view_v15.json','utf8'));
const c=vm.createContext({document,Date,JSON,Math,Number,Array,String,Set,AbortController,console,
 setTimeout:()=>0,clearTimeout(){},setInterval(){},fetch:async()=>({ok:true,json:async()=>state})});
vm.runInContext(html.split('<script>')[1].split('</script>')[0],c);
const text=e=>[e.textContent,...(e.children||[]).map(text)].filter(x=>x!==undefined).join(' ');
(async()=>{
 await new Promise(r=>setImmediate(r));
 assert.equal(elements.get('workers').children.length,3);
 assert.equal(elements.get('actual-rows').children.length,31);
 const first=elements.get('actual-rows').children[0].children;
 assert.equal(first[1].textContent,(state.actual_comparison.rows[0].B1.percent).toFixed(2)+'%');
 assert.equal(first[3].textContent,'—');assert.equal(first[5].textContent,'—');
 assert(!ids.has('gate')&&!ids.has('validation-rows'),'completed FULL validation panel is removed');
 assert(!html.includes('fingerprints_identical'),'scientific proof is not displayed in the monitoring UI');
 assert.match(elements.get('campaign-title').textContent,/B2 실행 중/);
 const detail=elements.get('workers').children[0].children.at(-1);detail.open=true;detail.toggle();
 vm.runInContext('render()',c);
 assert.equal(elements.get('workers').children[0].children.at(-1).open,true,'expanded details survive auto-refresh');
 vm.runInContext("snapshot.actual_comparison.rows[0].B2={available:true,percent:62};snapshot.actual_comparison.rows[0].difference_pp=-5;snapshot.actual_comparison.rows[0].B2_status='PASS';render();",c);
 assert.equal(elements.get('actual-rows').children[0].children[3].textContent,'62.00%');
 assert.equal(elements.get('actual-rows').children[0].children[5].textContent,'-5.00 %p');
 const card=elements.get('workers').children[0];assert.match(text(card),/독립 인증 Global Gap/);assert.match(text(card),/Native 사용/);
 vm.runInContext('failed=true;clock()',c);assert.equal(elements.get('connection-alert').hidden,false);
 assert.equal(elements.get('connection').textContent,'연결 지연');
 vm.runInContext('failed=false;snapshot.B2_validation_detail.PASS=false;snapshot.worker_slots.forEach(w=>{w.display_waiting=true;w.worker_alive=false;});snapshot.workers=[];render();',c);
 assert.match(elements.get('campaign-title').textContent,/시작 준비/);
 assert.match(text(elements.get('workers')),/검증 통과 후 자동 시작/);
 console.log('PASS: three workers, 31 date comparisons, absent pending values, %p differences, persistent details, stale connection and validation waiting.');
})().catch(e=>{console.error(e);process.exitCode=1;});
