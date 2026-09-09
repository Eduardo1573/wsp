/**
 * Vaadin 7.7 UIDL client for wsp.kbtu.kz, ported from tools/vaadin.py.
 * See PROTOCOL.md for how every constant here was established.
 *
 * All traffic goes through the relay (proxy/worker.js) because WSP sends no
 * CORS headers. The browser owns the cookie jar and replays it via X-WSP-Cookie,
 * so the relay stays stateless.
 */

const LS_RPC = 'com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc';
const BTN_RPC = 'com.vaadin.shared.ui.button.ButtonServerRpc';
const LEGACY = 'v';

// MouseEventDetails is bean-serialized, NOT the comma-joined string form.
const CLICK_EVENT = {
  button: 'LEFT', clientX: 120, clientY: 240,
  altKey: false, ctrlKey: false, metaKey: false, shiftKey: false,
  type: 1, relativeX: 12, relativeY: 10,
};

/** Wrap a JS value as Vaadin's UidlValue [typeTag, value]. */
function uidlValue(v) {
  if (typeof v === 'boolean') return ['b', v];
  if (typeof v === 'number') return Number.isInteger(v) ? ['i', v] : ['d', v];
  if (typeof v === 'string') return ['s', v];
  if (v === null || v === undefined) return ['n', null];
  if (Array.isArray(v)) return ['a', v.map(uidlValue)];
  throw new TypeError(`cannot encode ${typeof v}`);
}

/** Vaadin guards UIDL responses with `for(;;);` against JSON hijacking. */
function stripPrefix(text) {
  const t = text.replace(/^\s+/, '');
  return t.startsWith('for(;;);') ? t.slice('for(;;);'.length) : t;
}

export class WspError extends Error {}

/** Walk nested legacy UIDL for {key, caption} option nodes. */
export function extractOptions(changes) {
  const found = [];
  const stack = [...(changes || [])];
  while (stack.length) {
    const n = stack.pop();
    if (Array.isArray(n)) stack.push(...n);
    else if (n && typeof n === 'object') {
      if ('key' in n && 'caption' in n) {
        found.push({ key: String(n.key), caption: n.caption });
      }
      stack.push(...Object.values(n));
    }
  }
  return found.sort((a, b) => (parseInt(a.key, 10) || 0) - (parseInt(b.key, 10) || 0));
}

/** Legacy selects report their current value via a selectedKeys/selected
 *  variable rather than on the option nodes. */
export function extractSelected(changes) {
  const keys = [];
  const stack = [...(changes || [])];
  while (stack.length) {
    const n = stack.pop();
    if (Array.isArray(n)) stack.push(...n);
    else if (n && typeof n === 'object') {
      for (const k of ['selectedKeys', 'selected', 'selectedKey']) {
        if (k in n) keys.push(...(Array.isArray(n[k]) ? n[k] : [n[k]]));
      }
      stack.push(...Object.values(n));
    }
  }
  return keys.filter((k) => k !== null && k !== undefined && k !== '').map(String);
}

export class WspSession {
  /** @param {string} relay base URL of the deployed worker, e.g. https://wsp-relay.you.workers.dev */
  constructor(relay, view = 'StudentSchedule') {
    this.relay = relay.replace(/\/$/, '');
    this.view = view;
    this.cookies = new Map();
    this.appId = null;
    this.cfg = {};
    this.uiId = null;
    this.csrf = null;
    this.syncId = 0;
    this.clientId = 0;
    this.lastChanges = [];
    this.state = {};
    this.types = {};
    this.hierarchy = {};
    this.typeNames = {};
    // Persisted per install, exactly as a browser's localStorage would.
    this.browserUuid = localStorage.getItem('secretBrowserUuid') || crypto.randomUUID();
    localStorage.setItem('secretBrowserUuid', this.browserUuid);
  }

  get cookieHeader() {
    return [...this.cookies].map(([k, v]) => `${k}=${v}`).join('; ');
  }

  _absorbCookies(resp) {
    const raw = resp.headers.get('X-WSP-Set-Cookie');
    if (!raw) return;
    for (const pair of raw.split(';')) {
      const [k, ...rest] = pair.trim().split('=');
      if (k && rest.length) this.cookies.set(k, rest.join('='));
    }
  }

  async _fetch(path, init = {}) {
    const headers = new Headers(init.headers || {});
    if (this.cookies.size) headers.set('X-WSP-Cookie', this.cookieHeader);
    const resp = await fetch(this.relay + path, { ...init, headers });
    this._absorbCookies(resp);
    if (!resp.ok) throw new WspError(`relay returned ${resp.status}`);
    return resp;
  }

  // ---- 1. bootstrap ----
  async bootstrap() {
    const resp = await this._fetch(`/${this.view}`);
    const html = await resp.text();
    const m = html.match(/vaadin\.initApplication\("([^"]+)",(\{.*?\})\);/s);
    if (!m) throw new WspError('no vaadin.initApplication() in bootstrap HTML');
    this.appId = m[1];
    this.cfg = JSON.parse(m[2]);
    return this.cfg;
  }

  // ---- 2. browser-details handshake ----
  async handshake() {
    if (!this.appId) await this.bootstrap();
    const ts = Date.now();
    const tzo = -new Date().getTimezoneOffset();
    const form = new URLSearchParams({
      'v-browserDetails': '1',
      theme: this.cfg.theme || 'r5',
      'v-appId': this.appId,
      'v-sh': String(screen.height), 'v-sw': String(screen.width),
      'v-cw': String(innerWidth), 'v-ch': String(innerHeight),
      'v-curdate': String(ts),
      'v-tzo': String(tzo), 'v-dstd': '0', 'v-rtzo': String(tzo), 'v-dston': 'false',
      'v-vw': String(innerWidth), 'v-vh': '0',
      'v-loc': `https://wsp.kbtu.kz/${this.view}`,
      'v-wn': `${this.appId}-0.${ts % 1e9}`,
    });
    const resp = await this._fetch(`/${this.view}/?v-${ts}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
      body: form.toString(),
    });
    const payload = JSON.parse(stripPrefix(await resp.text()));
    this.uiId = payload['v-uiId'];
    const uidl = JSON.parse(payload.uidl);
    this.csrf = uidl['Vaadin-Security-Key'];
    this._absorb(uidl);
    return uidl;
  }

  // ---- 3. RPC ----
  async rpc(calls, { raiseOnError = true } = {}) {
    const resp = await this._fetch(`/${this.view}/UIDL/?v-uiId=${this.uiId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=UTF-8' },
      body: JSON.stringify({
        csrfToken: this.csrf, rpc: calls,
        syncId: this.syncId, clientId: this.clientId,
      }),
    });
    const text = stripPrefix(await resp.text());
    let frames;
    try {
      frames = JSON.parse(text);
    } catch {
      throw new WspError('non-JSON response — session likely expired');
    }
    if (!Array.isArray(frames)) frames = [frames];
    this.lastChanges = frames.flatMap((f) => f.changes || []);
    frames.forEach((f) => this._absorb(f));
    const err = frames.at(-1)?.meta?.appError;
    if (err && raiseOnError) throw new WspError(err.caption || 'server error');
    return frames;
  }

  /** Required every cfg.heartbeatInterval seconds or the session dies. */
  heartbeat() {
    return this._fetch(`/${this.view}/HEARTBEAT/?v-uiId=${this.uiId}`, { method: 'POST' })
      .catch(() => null);
  }

  // ---- high-level ----
  /** The login form is not in the initial tree — the server renders it only
   *  after the client reports a device id. Resolve the LocalStorage connector by
   *  class rather than by pid, which shifts as the UI grows. */
  async announceBrowser() {
    const pid = this.findOne('com.r5.core.web.addon.LocalStorage');
    await this.rpc([[pid, LS_RPC, 'updateUuid', [this.browserUuid]]]);
    if (!this.find('com.vaadin.ui.PasswordField').length) {
      throw new WspError(
        'WSP did not render the login form. This usually means a stale session — '
        + 'try again, and if it persists reinstall the app from the home screen.'
      );
    }
  }

  /** Header flag buttons, resolved by their icon rather than pid. English
   *  captions are far easier to parse than the mixed KZ/RU defaults. */
  setLanguage(lang = 'en', { required = true } = {}) {
    const want = { kz: 'flags/kz.png', ru: 'flags/ru.png', en: 'flags/gb.png' }[lang];
    const pid = this.find('com.vaadin.ui.Button').find(
      (p) => (this.state[p]?.resources?.icon?.uRL || '').includes(want)
    );
    if (!pid) {
      if (required) throw new WspError(`no ${lang} language button found`);
      return Promise.resolve(null);
    }
    return this.click(pid);
  }

  click(pid) {
    return this.rpc([[String(pid), BTN_RPC, 'click', [CLICK_EVENT]]]);
  }

  /** Open a legacy select and read its options. Vaadin 7 selects are legacy
   *  components: items arrive in the UIDL `changes` array, not shared state. */
  async comboOptions(pid, filterText = '', page = 0) {
    await this.rpc([
      [String(pid), LEGACY, LEGACY, ['filter', uidlValue(filterText)]],
      [String(pid), LEGACY, LEGACY, ['page', uidlValue(page)]],
    ], { raiseOnError: false });
    return { options: extractOptions(this.lastChanges), raw: this.lastChanges };
  }

  /** Set a legacy select by item key.
   *  AbstractSelect.changeVariables() reads "selected" as String[], so the tag
   *  must be "S" (VTYPE_STRINGARRAY). The generic "a" deserialises to the wrong
   *  Java type and the server drops it silently — no error, no changes. */
  selectOption(pid, key, filterText = '') {
    return this.rpc([
      [String(pid), LEGACY, LEGACY, ['filter', uidlValue(filterText)]],
      [String(pid), LEGACY, LEGACY, ['page', uidlValue(0)]],
      [String(pid), LEGACY, LEGACY, ['selected', ['S', [String(key)]]]],
    ], { raiseOnError: false });
  }

  get isLoggedIn() {
    return !this.find('kz.kbtu.officeregistrar.widget.api.LoginView').length;
  }

  /** Open another WSP view reusing this session's cookies. The JSESSIONID is
   *  shared across the webapp, so an already-authenticated jar usually lands
   *  straight in the view; fall back to logging in if it does not. */
  async openView(view, username, password) {
    const s = new WspSession(this.relay, view);
    s.cookies = this.cookies;
    s.browserUuid = this.browserUuid;
    await s.handshake();
    if (s.isLoggedIn) {
      // Column captions are parsed by name, so the view must be in English even
      // when we skipped the login screen that normally sets it.
      await s.setLanguage('en', { required: false });
      return s;
    }
    await s.announceBrowser();
    await s.setLanguage('en');
    const res = await s.login(username, password);
    if (!res.ok) throw new WspError(res.error);
    return s;
  }

  /** Re-run bootstrap+handshake on the same cookie jar. Vaadin authenticates by
   *  telling the client to reload; the session cookie is already logged in. */
  async reattach() {
    this.state = {}; this.types = {}; this.hierarchy = {}; this.typeNames = {};
    this.syncId = 0; this.clientId = 0; this.appId = null;
    return this.handshake();
  }

  async login(username, password) {
    const userPid = this.findOne('com.vaadin.ui.ComboBox');
    const passPid = this.findOne('com.vaadin.ui.PasswordField');
    const btnPid = this.findByCaption('com.vaadin.ui.Button', ['Кіру', 'Вход', 'Log in']);
    const before = new Set(Object.keys(this.types));
    await this.rpc([
      [userPid, LEGACY, LEGACY, ['newitem', uidlValue(username)]],
      [passPid, LEGACY, LEGACY, ['text', uidlValue(password)]],
      [btnPid, BTN_RPC, 'click', [CLICK_EVENT]],
    ]);
    const fresh = Object.keys(this.types).filter((p) => !before.has(p));
    const err = this.errorText(fresh);
    if (err) return { ok: false, error: err };
    await this.reattach();
    if (this.find('kz.kbtu.officeregistrar.widget.api.LoginView').length) {
      return { ok: false, error: 'Login did not take effect' };
    }
    return { ok: true };
  }

  /** Auth failure renders a modal Window styled 'global-error' wrapping a Label. */
  errorText(pids = Object.keys(this.types)) {
    for (const pid of pids) {
      if (this.cls(pid) !== 'com.vaadin.ui.Window') continue;
      if (!(this.state[pid]?.styles || []).includes('global-error')) continue;
      for (const d of this.descendants(pid)) {
        const t = this.state[d]?.text;
        if (t && this.cls(d) === 'com.vaadin.ui.Label') return t;
      }
      return 'Unknown error';
    }
    return null;
  }

  // ---- state mirror ----
  _absorb(frame) {
    if (Number.isInteger(frame.syncId) && frame.syncId >= 0) this.syncId = frame.syncId;
    if ('clientId' in frame) this.clientId = frame.clientId;
    for (const [pid, st] of Object.entries(frame.state || {})) {
      this.state[pid] = { ...(this.state[pid] || {}), ...st };
    }
    Object.assign(this.types, frame.types || {});
    Object.assign(this.hierarchy, frame.hierarchy || {});
    for (const [name, tid] of Object.entries(frame.typeMappings || {})) {
      this.typeNames[String(tid)] = name;
    }
  }

  // ---- introspection ----
  cls(pid) { return this.typeNames[String(this.types[String(pid)])] || '?'; }
  kids(pid) { return this.hierarchy[String(pid)] || []; }

  descendants(pid) {
    const out = [], stack = [String(pid)];
    while (stack.length) {
      const cur = stack.pop();
      out.push(cur);
      stack.push(...this.kids(cur));
    }
    return out;
  }

  find(...names) {
    return Object.keys(this.types)
      .filter((p) => names.some((n) => this.cls(p) === n || this.cls(p).endsWith(n)))
      .sort((a, b) => Number(a) - Number(b));
  }

  findOne(...names) {
    const hit = this.find(...names)[0];
    if (!hit) {
      const seen = [...new Set(Object.keys(this.types).map((p) => this.cls(p).split('.').pop()))];
      throw new WspError(
        `WSP page did not contain ${names.map((n) => n.split('.').pop()).join('/')}. `
        + `Got: ${seen.join(', ') || '(empty page)'}`
      );
    }
    return hit;
  }

  findByCaption(name, captions) {
    for (const p of this.find(name)) {
      if (captions.includes(this.state[p]?.caption)) return p;
    }
    throw new WspError(`no ${name} captioned ${captions}`);
  }

  styles(pid) { return this.state[String(pid)]?.styles || []; }
  text(pid) { return this.state[String(pid)]?.text; }
}
