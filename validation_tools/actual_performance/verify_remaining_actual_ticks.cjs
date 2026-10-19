const vm=require('node:vm');
const assert=require('node:assert/strict');
(async()=>{
  const url='http://127.0.0.1:8795/';
  const html=await (await fetch(url)).text();
  const status=await (await fetch(url+'api/status')).json();
  const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
  for(const body of scripts)new vm.Script(body);
  const source=scripts.find(s=>s.includes('function renderActualTicks('));
  assert(source);assert.equal(status.actual_tick_details.rows.length,8);
  function element(tag){return {tag,children:[],append(...rows){this.children.push(...rows)},replaceChildren(...rows){this.children=rows}}}
  const elements=new Map();
  const document={getElementById(id){if(!elements.has(id))elements.set(id,element('div'));return elements.get(id)},createElement:element};
  const renderer=source.slice(source.indexOf('function renderActualTicks('),source.indexOf('async function refresh(){'));
  const context={document};vm.createContext(context);vm.runInContext(renderer,context);
  context.renderActualTicks(status.actual_tick_details);
  assert.equal(elements.get('actual-ticks-card').hidden,false);
  const rows=elements.get('actual-ticks-body').children;assert.equal(rows.length,8);
  assert.equal(rows[0].children[0].textContent,'05/04 B1');
  assert.match(rows[0].children[1].textContent,/\d+회/);
  assert.equal(rows[7].children[0].textContent,'05/07 B3');
  assert.equal(rows[7].children[1].textContent,'0회');
  console.log(JSON.stringify({PASS:true,rendered_rows:rows.length,summary:elements.get('actual-ticks-summary').textContent,first:rows[0].children.map(c=>c.textContent),last:rows[7].children.map(c=>c.textContent)}));
})().catch(error=>{console.error(error);process.exitCode=1});
