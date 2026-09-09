/**
 * Stateless CORS relay for wsp.kbtu.kz — deploy to Cloudflare Workers (free tier).
 *
 * WSP sends no Access-Control-* headers, so browser JS cannot call it directly.
 * This relay adds them. It is deliberately STATELESS: it stores nothing, logs no
 * request bodies, and holds no sessions. The browser owns the cookie jar and
 * replays it through X-WSP-Cookie, so credentials only ever transit this worker —
 * they are never at rest on it.
 *
 *   Browser  --X-WSP-Cookie-->  Worker  --Cookie-->  wsp.kbtu.kz
 *            <-X-WSP-Set-Cookie-       <-Set-Cookie-
 *
 * Deploy:  npx wrangler deploy
 */

const UPSTREAM = 'https://wsp.kbtu.kz';

// Only these paths are relayable — keeps the worker from becoming an open proxy.
// The trailing slash is significant: the browser-details handshake posts to
// "/StudentSchedule/?v-<ts>", so a bare trailing slash must be allowed too.
const ALLOWED = /^\/(StudentSchedule|JournalView)(\/(UIDL|HEARTBEAT))?\/?$/;

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin || '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-WSP-Cookie',
    'Access-Control-Expose-Headers': 'X-WSP-Set-Cookie',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin');
    const allowed = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
    if (allowed.length && origin && !allowed.includes(origin)) {
      return new Response('origin not allowed', { status: 403 });
    }

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    const url = new URL(request.url);
    if (!ALLOWED.test(url.pathname)) {
      return new Response('path not relayable', { status: 404, headers: corsHeaders(origin) });
    }

    // Rebuild the upstream URL, preserving the ?v-<ts> / ?v-uiId= query Vaadin needs.
    const upstream = new URL(UPSTREAM + url.pathname + url.search);

    const headers = new Headers();
    const ct = request.headers.get('Content-Type');
    if (ct) headers.set('Content-Type', ct);
    // Pose as a normal desktop browser; WSP is picky about junk clients.
    headers.set('User-Agent', request.headers.get('X-WSP-UA') ||
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    // The browser cannot set cross-origin cookies, so it hands us the jar explicitly.
    const jar = request.headers.get('X-WSP-Cookie');
    if (jar) headers.set('Cookie', jar);

    let upstreamResp;
    try {
      upstreamResp = await fetch(upstream.toString(), {
        method: request.method,
        headers,
        body: request.method === 'POST' ? await request.arrayBuffer() : undefined,
        redirect: 'manual',
      });
    } catch (err) {
      // NOTE: wsp.kbtu.kz serves an incomplete cert chain (missing the Sectigo
      // DV R36 intermediate). Cloudflare's edge tolerates it; stricter runtimes
      // (bare Node/undici) do not. See PROTOCOL.md.
      return new Response(JSON.stringify({ error: 'upstream fetch failed', detail: String(err) }),
        { status: 502, headers: { ...corsHeaders(origin), 'Content-Type': 'application/json' } });
    }

    const out = new Headers(corsHeaders(origin));
    const upstreamCT = upstreamResp.headers.get('Content-Type');
    if (upstreamCT) out.set('Content-Type', upstreamCT);

    // Hand every Set-Cookie back for the client to store. BOTH JSESSIONID and the
    // sticky `route` cookie are required — WSP is load-balanced and the session
    // lives on exactly one node.
    const setCookies = upstreamResp.headers.getSetCookie?.() ?? [];
    if (setCookies.length) {
      out.set('X-WSP-Set-Cookie', setCookies.map(c => c.split(';')[0]).join('; '));
    }

    return new Response(upstreamResp.body, { status: upstreamResp.status, headers: out });
  },
};
