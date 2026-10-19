const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

(async () => {
  const base = 'http://127.0.0.1:8795';
  const html = await (await fetch(base)).text();
  const script = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
  const elements = new Map();
  const element = () => ({style: {}, textContent: '', replaceChildren() {}, append() {}});
  for (const [, id] of html.matchAll(/\bid="([^"]+)"/g)) elements.set(id, element());
  let disconnected = false;
  const context = vm.createContext({
    document: {getElementById: id => elements.get(id) || null, querySelector: () => element(),
      createElement: element, addEventListener() {}},
    fetch: (url, opts) => disconnected ? Promise.reject(Error('test connection loss')) : fetch(base + url, opts),
    AbortController, setTimeout, clearTimeout, setInterval() {}, Date, console,
  });
  vm.runInContext(script, context);
  // Wait for the initial asynchronous refresh, then exercise the same callback again.
  while (vm.runInContext('busy', context)) await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(elements.get('status').textContent, '캠페인 실행 중');
  assert.match(elements.get('detail').textContent, /전체 AC 검증 완료/);
  disconnected = true;
  await vm.runInContext('refresh()', context);
  assert.equal(elements.get('status').textContent, '상태 수신 지연');
  disconnected = false;
  await vm.runInContext('refresh()', context);
  assert.equal(elements.get('status').textContent, '캠페인 실행 중');
  assert.match(elements.get('detail').textContent, /전체 AC 검증 완료/);
  const results = {PASS: true, scenarios: ['live render', 'connection loss', 'automatic reconnect'],
    detail: elements.get('detail').textContent};
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
})().catch(error => {console.error(error); process.exitCode = 1;});
