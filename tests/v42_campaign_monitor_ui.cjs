// DOM unit harness, without a browser or access to a live UI.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.style={}; this.dataset={}; this.attrs={}; this.hidden=false; this.textContent=''; this.classList={toggle:()=>{}}; }
  replaceChildren(...children) { this.children=children; }
  append(...children) { this.children.push(...children); }
  setAttribute(k,v) { this.attrs[k]=v; }
  addEventListener(k,callback) { this[k]=callback; }
}
const elements = new Map();
const document = {
  getElementById(id) { if(!elements.has(id))elements.set(id,new Element());return elements.get(id); },
  createElement(tag) { return new Element(tag); },
  createTextNode(text) { return {textContent:text}; },
  addEventListener() {}, hidden:false
};
const worker={arm:'B1',day:'2025-05-01',PID:123,worker_slot:1,phase:'A_ORIGINAL_NATIVE_CONSTRUCTION',worker_alive:true,heartbeat_recent:true,wall_seconds:900,remaining_seconds:4500,Native_Runtime_seconds:0,Native_calls:0,report_delayed:true,solver_report_age_seconds:735,heartbeat_age_seconds:1,resource:{CPU_percent:95,RSS:2**30},progress:{phase:'A_ORIGINAL_NATIVE_CONSTRUCTION'},target_gap:.005,build:{complete:false,confirmed_steps:1,total_steps:5,percent:20,current:'계통·물리 도메인 준비',steps:[{label:'날짜 입력',state:'done'},{label:'계통 준비',state:'active'}],counters:{'전체 작업':1499},jobs:1499,classes:117}};
const state={status:'실행 중',state:'RUNNING',workers:[worker],completed:0,campaign_percent:0,B1:{completed:0},B2:{completed:0},totals:{PASS:0,TIMEOUT:0,FAIL:0,pending:61},date_tables:{B1:[],B2:[]},run_id:'test',runtime_root:'D:/fake',last_error:null};
const context=vm.createContext({document,window:{innerWidth:1120,addEventListener(){}},Date,JSON,Math,Number,Array,String,AbortController,console,setTimeout:()=>0,clearTimeout(){},setInterval(){},fetch:async()=>({ok:true,json:async()=>state})});
const html=fs.readFileSync('v42_campaign_monitor/index.html','utf8');
vm.runInContext(html.split('<script>')[1].split('</script>')[0],context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('objective').textContent,'모델 생성 중');
  assert.equal(elements.get('stage-bar').style.width,'20%');
  assert.match(elements.get('elapsed').textContent,/15분/);
  assert.match(elements.get('report-note').textContent,/내부 처리율은 아직 보고되지/);
  assert.equal(elements.get('report-note').hidden,false);
  // Select each independent B2 worker; objective and loading follow the selection.
  state.workers=[1,2,3].map(slot=>({...worker,arm:'B2',day:`2025-05-0${slot}`,worker_slot:slot,phase:'M_ADAPTIVE_U1',build:{...worker.build,complete:true},UB:1+slot/10,independent_Global_LB:1.0,Certified_Gap:.02,Planning_max_line_loading:1+slot/10,Fresh_AC_max_line_loading:null}));
  context.testState=state;
  vm.runInContext("snapshot=testState; selected='B2/2025-05-02'; render()",context);
  assert.equal(elements.get('objective').textContent,'1.2');
  assert.equal(elements.get('loading').textContent,'120%');
  assert.match(elements.get('loading-note').textContent,/Planning 값/);
  assert.equal(elements.get('worker-tabs').children.length,3);
  assert.equal(elements.get('stage-track').hidden,true);
  assert.equal(elements.get('worker-tabs').children[1].attrs['aria-pressed'],'true');
  // A transient fetch failure preserves the last values and alerts the user.
  context.fetch=async()=>{throw Error('offline');};
  await vm.runInContext('refresh()',context);
  assert.equal(elements.get('objective').textContent,'1.2');
  assert.equal(elements.get('status-text').textContent,'화면 연결 지연');
  assert.match(elements.get('report-note').textContent,/다시 연결 중/);
  context.fetch=async()=>({ok:true,json:async()=>state});
  await vm.runInContext('refresh()',context);
  assert.equal(elements.get('status-text').textContent,'계산 중');
  console.log('UI DOM regression PASS: build progress, live clock, B2 selection, connection loss/recovery');
})().catch(error=>{console.error(error);process.exitCode=1;});
