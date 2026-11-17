// Replays the panel's /mesh/get traffic over rosbridge and reports throughput.
// usage: node mesh_replay.cjs <ws_node_modules_dir> <meshes_dir> <concurrency> [timeout_s]
const path = require('path');
const fs = require('fs');
const WebSocket = require(path.join(process.argv[2], 'ws'));
const dir = process.argv[3];
const CONC = Number(process.argv[4] || 8);
const TIMEOUT = Number(process.argv[5] || 60) * 1000;
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.dae')).map((f) => 'file://' + path.join(dir, f));
const ws = new WebSocket(process.env.WS_URL || 'ws://127.0.0.1:9090');
const pending = new Map();
let n = 0, ok = 0, fail = 0, timeouts = 0, bytes = 0;
const lat = [];
const t0 = Date.now();
const SLOW = Number(process.env.SLOWMS || 0);
ws.on('message', (m) => {
  const s = m.toString();
  const j = JSON.parse(s);
  if (SLOW && j.op === 'publish') { const e = Date.now() + SLOW; while (Date.now() < e); }
  if (j.op !== 'service_response') return;
  const p = pending.get(j.id);
  if (!p) return;
  pending.delete(j.id);
  clearTimeout(p.timer);
  const dt = Date.now() - p.t;
  lat.push(dt);
  bytes += s.length;
  if (j.result && j.values && j.values.success) ok++; else fail++;
  p.done();
});
function call(file) {
  return new Promise((resolve) => {
    const id = 'mesh:' + ++n;
    const t = Date.now();
    const timer = setTimeout(() => { pending.delete(id); timeouts++; resolve(); }, TIMEOUT);
    pending.set(id, { t, timer, done: resolve });
    ws.send(JSON.stringify({ op: 'call_service', id, service: '/mesh/get', args: { path: file }, timeout: 10 }));
  });
}
ws.on('open', async () => {
  for (const topic of (process.env.SUBS || '').split(',').filter(Boolean)) {
    ws.send(JSON.stringify({ op: 'subscribe', topic }));
  }
  if (process.env.SUBS) await new Promise((r) => setTimeout(r, 2000));
  await call(files[0]);
  const queue = files.slice(1);
  const worker = async () => { while (queue.length) await call(queue.shift()); };
  await Promise.all(Array.from({ length: CONC }, worker));
  lat.sort((a, b) => a - b);
  const q = (p) => lat[Math.min(lat.length - 1, Math.floor(lat.length * p))];
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`RESULT conc=${CONC} total=${files.length} ok=${ok} fail=${fail} timeouts=${timeouts} secs=${secs} MB=${(bytes / 1e6).toFixed(1)} p50=${q(0.5)}ms p95=${q(0.95)}ms max=${lat[lat.length - 1]}ms`);
  ws.close();
  process.exit(0);
});
setTimeout(() => { console.log(`RESULT DEADLINE ok=${ok} fail=${fail} timeouts=${timeouts}`); process.exit(3); }, 120000);
ws.on('error', (e) => { console.log('WSERR', e.message); process.exit(2); });
