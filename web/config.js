/**
 * Where to reach the relay.
 *
 * Empty string = same origin, which is the normal case: the Cloudflare Worker
 * serves this app *and* relays to wsp.kbtu.kz, so requests just go to /Student...
 *
 * Override when serving the frontend from somewhere else (e.g. a local
 * `python3 -m http.server`) with ?relay=https://wsp-relay.kbtu.workers.dev
 */
const params = new URLSearchParams(location.search);
if (params.get('relay')) localStorage.setItem('relayUrl', params.get('relay'));
export const RELAY_URL = localStorage.getItem('relayUrl') || '';
