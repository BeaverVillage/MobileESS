// Offline integration check of the served HTML/refresh/renderer and live JSON.
// No browser, network mutations, solver or package dependencies are required.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2],'utf8'),live=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.style={};this.dataset={};this._text='';}
 set textContent(value){this._text=String(value??'');this.children=[];}
 get textContent(){return this._text+this.children.map(x=>x.textContent).join(' ');}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this._text='';this.children=nodes;}
 querySelectorAll(selector){const nodes=this.children.flatMap(x=>[x,...x.querySelectorAll('*')]);return selector==='details[open]'?nodes.filter(x=>x.tagName==='details'&&x.open):nodes;}
}
const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element('div')]));
const metrics=new Element('div'),calls=[],timers=[];
const context=vm.createContext({console,Date,Number,Math,Set,AbortController,
 document:{getElementById:id=>{assert(nodes.has(id),'Missing DOM id '+id);return nodes.get(id);},createElement:tag=>new Element(tag),querySelector:selector=>{assert.equal(selector,'.metrics');return metrics;},addEventListener:()=>{}},
 fetch:async url=>{calls.push(url);assert.equal(url,'/api/status');return {ok:true,json:async()=>live};},
 setInterval:(fn,ms)=>timers.push([fn,ms]),setTimeout,clearTimeout});
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];assert.equal(scripts.length,1);
vm.runInContext(scripts[0][1],context);
(async()=>{
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls.length,1);assert.equal(nodes.get('iteration2-days').children.length,31);
 assert.equal(nodes.get('iteration2-card').hidden,false);
 assert.equal(nodes.get('day').textContent,live.day);
 assert.equal(nodes.get('used').textContent,live.used_text);
 assert.equal(nodes.get('status').textContent,live.status);
 assert(!nodes.get('status').textContent.includes('수신 지연'));
 assert(!html.includes('r043')&&!html.includes('case-loading-card'));
 const data=structuredClone(live.iteration2_details),worker=data.workers.find(w=>w.alive);
 assert(worker,'Expected a current iteration2 worker in the live fixture');
 worker.stage='A3';delete worker.voltage;worker.phase_I={Phi:2e-8,zero_PASS:false,Native_seconds:123,solve:42};data.Native_total_estimated=true;
 context.fixture=data;vm.runInContext('renderIteration2(fixture)',context);
 assert.match(nodes.get('iteration2-phase').textContent,/2\.00000e-8/);
 assert.match(nodes.get('iteration2-phase').textContent,/zero 검증 대기/);
 assert.match(nodes.get('iteration2-phase').textContent,/123\.0 \/ 1500 s/);
 assert.match(nodes.get('iteration2-summary').textContent,/Native 합계 약 /);
 console.log('RENDERER_PASS: real served refresh, 31 rows, live Native/status, tiny positive Phi, old monitor absent');
})().catch(error=>{console.error(error);process.exitCode=1;});
