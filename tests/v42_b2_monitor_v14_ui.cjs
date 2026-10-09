// Offline DOM unit test of source rendering; no browser or live UI access.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{constructor(){this.children=[];this.style={};this.dataset={};this.attrs={};this.classList={toggle(){}};}replaceChildren(...x){this.children=x;}append(...x){this.children.push(...x);}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,f){this[k]=f;}}
const html=fs.readFileSync('v42_b2_monitor_v14/index.html','utf8'),elements=new Map();
const ids=new Set([...html.matchAll(/id="([^"]+)"/g)].map(x=>x[1]));
const document={getElementById(id){assert(ids.has(id),'missing HTML id '+id);if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();},createTextNode(text){return {textContent:text};},addEventListener(){}};
const state=JSON.parse(fs.readFileSync('tmp/b2_monitor_view_v14.json','utf8'));
const c=vm.createContext({document,window:{innerWidth:1120,addEventListener(){}},Date,JSON,Math,Number,Array,String,AbortController,console,setTimeout:()=>0,clearTimeout(){},setInterval(){},fetch:async()=>({ok:true,json:async()=>state})});
vm.runInContext(html.split('<script>')[1].split('</script>')[0],c);
(async()=>{await new Promise(r=>setImmediate(r));
assert.equal(elements.get('validation-rows').children.length,4);
assert.match(elements.get('validation-current').textContent,/2025-05-01/);
assert.match(elements.get('validation-current').textContent,/가속 모델/);
assert.equal(elements.get('worker-tabs').children.length,3);
assert.equal(elements.get('worker-tabs').hidden,false);
assert.match(elements.get('current-day').textContent,/B2/);
assert.match(elements.get('validation-proof').textContent,/original_matrix/);
elements.get('worker-tabs').children[1].click();
assert.match(elements.get('current-day').textContent,/2025-05-02/);
assert.equal(elements.get('report-note').hidden,true);
console.log('PASS: actual snapshot renders B2 validation details, four model rows, three selectable slots, and correct waiting state.');
})().catch(e=>{console.error(e);process.exitCode=1;});
