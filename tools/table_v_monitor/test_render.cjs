const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.classList={remove(){}}}
 set textContent(v){this.value=String(v);this.children=[]}
 get textContent(){return this.value||''}
 append(...v){this.children.push(...v)}
 replaceChildren(...v){this.value='';this.children=v}
}
(async()=>{
 const html=fs.readFileSync(__dirname+'/index.html','utf8');
 const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/refresh\(\);\s*$/,'');
 const ids=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element('div')]));
 const state=await (await fetch((process.env.MONITOR_URL||'http://127.0.0.1:8794')+'/api/state')).json();
 const context=vm.createContext({document:{getElementById(id){assert(ids.has(id),'Unknown element '+id);return ids.get(id)},createElement:tag=>new Element(tag)},state,Date,JSON,Number,setTimeout(){}});
 vm.runInContext(script+'\nrender(state);',context);
 assert.equal(ids.get('active-title').textContent,'B1 · AIDC 유연성');
 assert(ids.get('phase').textContent.length>0);
 assert.equal(ids.get('arms').children.length,4);
 assert.equal(ids.get('results').children.length,4);
 assert.equal(ids.get('lb').textContent,'미확정');
 assert.equal(JSON.parse(ids.get('detail').textContent).archived_native_seconds_excluded,state.archived_native_seconds);
 assert(ids.get('detail').textContent.includes('current_release_recertified'));
 console.log('Render integration PASS: live phase, 4 arms, 4 result rows, pending certified bounds, historical B0, archived Native separation');
})().catch(e=>{console.error(e);process.exitCode=1});
