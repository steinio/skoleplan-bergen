/**
 * Counts calendar subscriptions for Skoleplan Bergen.
 *
 * GitHub Pages gives no access logs, and a calendar client never runs the
 * page's JavaScript -- it just fetches the .ics every few hours, forever. So
 * page analytics cannot see subscribers at all. This Worker sits in front of
 * the calendar files, counts who fetched what, and serves the file from Pages.
 *
 * What it counts is *unique clients per class per day*, not raw requests: one
 * subscribed phone asking eight times a day should read as one subscriber.
 *
 * It stores no IP address. The de-duplication key is a SHA-256 of the client
 * address, the class and the date, with a daily-rotating salt, kept for 48
 * hours. That cannot be reversed to an address, and cannot be used to follow
 * anyone from one day to the next.
 */

const ORIGIN = "https://steinio.github.io/skoleplan-bergen";
const SEEN_TTL = 60 * 60 * 48; // seconds

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/stats" || url.pathname === "/stats.json") {
      return stats(env, url);
    }
    if (!url.pathname.startsWith("/ics/") || !url.pathname.endsWith(".ics")) {
      return Response.redirect(ORIGIN + "/", 302);
    }

    // Serve first; counting must never delay or break a subscription.
    const upstream = await fetch(ORIGIN + url.pathname, {
      cf: { cacheTtl: 300, cacheEverything: true },
    });
    if (upstream.ok && env.COUNTS) {
      ctx.waitUntil(count(env, request, url.pathname));
    }

    const response = new Response(upstream.body, upstream);
    response.headers.set("Content-Type", "text/calendar; charset=utf-8");
    response.headers.set("Cache-Control", "public, max-age=1800");
    response.headers.set("Access-Control-Allow-Origin", "*");
    return response;
  },
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

/** Class id from "/ics/gimle-oppveksttun-skole-8e-maned.ics". */
function classOf(pathname) {
  return pathname.slice("/ics/".length, -".ics".length);
}

async function digest(text) {
  const bytes = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function count(env, request, pathname) {
  const day = today();
  const klass = classOf(pathname);
  const address = request.headers.get("CF-Connecting-IP") || "";
  const agent = request.headers.get("User-Agent") || "";

  // Rotating salt: the same visitor hashes differently tomorrow, so the key
  // cannot link a person across days.
  const salt = (env.SALT || "skoleplan") + day;
  const who = await digest(salt + "|" + address + "|" + agent + "|" + klass);
  const seenKey = `seen:${day}:${klass}:${who.slice(0, 32)}`;

  if (await env.COUNTS.get(seenKey)) return; // already counted today
  await env.COUNTS.put(seenKey, "1", { expirationTtl: SEEN_TTL });

  for (const key of [`count:${day}:${klass}`, `total:${klass}`, `day:${day}`]) {
    const current = parseInt((await env.COUNTS.get(key)) || "0", 10);
    await env.COUNTS.put(key, String(current + 1));
  }
}

/** Aggregate numbers only -- nothing here identifies anyone. */
async function stats(env, url) {
  if (!env.COUNTS) {
    return json({ error: "no KV namespace bound" }, 500);
  }
  const wanted = url.searchParams.get("prefix") || "";
  const out = { generated: new Date().toISOString(), days: {}, classes: {} };

  const days = await env.COUNTS.list({ prefix: "day:" });
  for (const k of days.keys) {
    out.days[k.name.slice(4)] = parseInt((await env.COUNTS.get(k.name)) || "0", 10);
  }
  const totals = await env.COUNTS.list({ prefix: "total:" + wanted });
  for (const k of totals.keys) {
    out.classes[k.name.slice(6)] = parseInt((await env.COUNTS.get(k.name)) || "0", 10);
  }
  out.subscribed_classes = Object.keys(out.classes).length;
  return json(out);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body, null, 1), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=300",
    },
  });
}
