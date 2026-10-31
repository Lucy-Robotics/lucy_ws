const WebSocket = require(process.argv[2] + '/node_modules/ws');
const urdf = require('fs').readFileSync(0, 'utf8');
const meshes = [...new Set([...urdf.matchAll(/filename="([^"]+)"/g)].map(m => m[1]))];
const ws = new WebSocket('ws://127.0.0.1:9090');
let id = 0;
const pending = new Map();
ws.on('message', (m) => { const j = JSON.parse(m.toString()); const p = pending.get(j.id); if (p) { pending.delete(j.id); p(j); } });
const call = (service, args) => new Promise((res) => { const k = `c${id++}`; pending.set(k, res); ws.send(JSON.stringify({op: 'call_service', id: k, service, args, timeout: 10})); });
const pool = async (items, n, fn) => { const q = [...items]; await Promise.all(Array.from({length: n}, async () => { while (q.length) await fn(q.shift()); })); };
ws.on('open', async () => {
  const stats = (name, t) => { t.sort((a, b) => a - b); console.log(`${name}: n=${t.length} median=${t[t.length >> 1]}ms p90=${t[Math.floor(t.length * 0.9)]}ms max=${t[t.length - 1]}ms`); };
  let t = [];
  for (let i = 0; i < 10; i++) { const s = Date.now(); await call('/robot_state_publisher/get_parameters', {names: ['robot_description']}); t.push(Date.now() - s); }
  stats('get_parameters sequential', t);
  t = [];
  for (const path of meshes.slice(0, 20)) { const s = Date.now(); const r = await call('/mesh/get', {path}); t.push(Date.now() - s); if (!r.result) console.log('fail', JSON.stringify(r).slice(0, 200)); }
  stats('mesh/get sequential', t);
  const s0 = Date.now(); t = [];
  let lost = 0;
  await pool(meshes, 8, async (path) => { const s = Date.now(); const r = await call('/mesh/get', {path}); t.push(Date.now() - s); if (!r.result) { lost++; console.log('fail', Date.now() - s, JSON.stringify(r).slice(0, 200)); } });
  console.log(`failed calls: ${lost}`);
  stats(`mesh/get all ${meshes.length} at concurrency 8 (total ${Date.now() - s0}ms)`, t);
  process.exit(0);
});
setTimeout(() => { console.log('timeout'); process.exit(1); }, 600000);
