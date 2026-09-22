// Checks the counting logic against an in-memory KV, with no Cloudflare
// account needed:  node worker/worker.test.mjs
import worker from '/home/user/skoleplan-bergen/worker/worker.js';
const mk = () => { const m = new Map(); return { m, kv: {
  get: async k => m.get(k) ?? null, put: async (k,v) => void m.set(k,v),
  list: async ({prefix}) => ({ keys:[...m.keys()].filter(k=>k.startsWith(prefix)).map(name=>({name})) }) }}; };
globalThis.fetch = async () => new Response('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', {status:200});
const req = (p, ip) => new Request('https://x.workers.dev'+p, {headers:{'CF-Connecting-IP':ip,'User-Agent':'CalendarAgent'}});

// properly await the background counting work
async function hit(env, path, ip) {
  const pending = [];
  const ctx = { waitUntil: p => pending.push(p) };
  const r = await worker.fetch(req(path, ip), env, ctx);
  await Promise.all(pending);
  return r;
}
const statsOf = async (env, qs='') =>
  (await worker.fetch(new Request('https://x.workers.dev/stats'+qs), env, {waitUntil:()=>{}})).json();

let {kv} = mk(); let env = { COUNTS: kv };            // no SALT at all
await hit(env, '/ics/a-8e.ics', '1.1.1.1');
await hit(env, '/ics/a-8e.ics', '1.1.1.1');
console.log('no SALT set, 2 fetches 1 client ->', (await statsOf(env)).classes['a-8e'], '(expect 1)');

({kv} = mk()); env = { COUNTS: kv, SALT:'s', STATS_TOKEN:'sekret' };
await hit(env, '/ics/a-8e.ics', '2.2.2.2');
for (const [label, qs] of [['no token',''],['wrong','?token=x'],['right','?token=sekret']]) {
  const r = await worker.fetch(new Request('https://x.workers.dev/stats'+qs), env, {waitUntil:()=>{}});
  console.log(`  /stats ${label.padEnd(8)} -> ${r.status}`);
}
console.log('with right token, classes     ->', JSON.stringify((await statsOf(env,'?token=sekret')).classes));

// the salt must actually change the dedupe key
const A = mk(), B = mk();
await hit({COUNTS:A.kv, SALT:'one'}, '/ics/a-8e.ics', '3.3.3.3');
await hit({COUNTS:B.kv, SALT:'two'}, '/ics/a-8e.ics', '3.3.3.3');
const ka = [...A.m.keys()].find(k=>k.startsWith('seen:'));
const kb = [...B.m.keys()].find(k=>k.startsWith('seen:'));
console.log('salt is used (keys differ)    ->', Boolean(ka && kb && ka !== kb));
console.log('  one:', ka?.slice(0,42)); console.log('  two:', kb?.slice(0,42));
