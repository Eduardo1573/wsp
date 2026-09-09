import { RELAY_URL } from './config.js';
import { WspSession, WspError, extractSelected } from './lib/uidl.js';
import {
  parseSchedule, DAYS, DAY_FULL, todayKey, lessonStatus, nextUp, toMin,
} from './lib/schedule.js';
import { parseTable, toRecords, summarise, parseSubject, presenceOf } from './lib/journal.js';

const $ = (id) => document.getElementById(id);
const CACHE_KEY = 'wsp.schedule.v1';
const JOURNAL_KEY = 'wsp.journal.v2';
const CRED_KEY = 'wsp.credentials.v1';

/** Resolve JournalView connectors by class.
 *
 *  Ids are NOT fixed: logging in and re-attaching creates the login-form
 *  connectors first, so the subject combo lands at 41 — but entering the view on
 *  an already-authenticated session skips all of that and every id shifts. Only
 *  class names are stable. */
function journalPids(js) {
  const wrapper = js.find('SemesterSubjectComboBox')[0];
  const subject = wrapper
    ? js.kids(wrapper).find((c) => js.cls(c) === 'com.vaadin.ui.ComboBox')
    : js.find('com.vaadin.ui.ComboBox')[0];
  return {
    year: js.find('YearComboBox')[0],
    term: js.find('SemesterPeriodComboBox')[0],
    subject,
    table: js.find('com.vaadin.ui.Table')[0],
  };
}

let schedule = null;
let selectedDay = todayKey();
let session = null;
let refreshing = false;

let tab = 'schedule';
let journal = null;          // { term, subjects: [{key, code, name, records, summary}] }
let openSubject = null;      // key of the subject being viewed
let journalLoading = false;

// ── persistence ──────────────────────────────────────────────
const loadCache = () => {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY)); } catch { return null; }
};
const saveCache = (data) =>
  localStorage.setItem(CACHE_KEY, JSON.stringify({ data, at: Date.now() }));

const loadCreds = () => {
  try { return JSON.parse(localStorage.getItem(CRED_KEY)); } catch { return null; }
};

const loadJournal = () => {
  try { return JSON.parse(localStorage.getItem(JOURNAL_KEY)); } catch { return null; }
};
const saveJournal = (data) =>
  localStorage.setItem(JOURNAL_KEY, JSON.stringify({ data, at: Date.now() }));

// ── rendering ────────────────────────────────────────────────
function renderDays() {
  const nav = $('days');
  nav.replaceChildren(...DAYS.map((d) => {
    const b = document.createElement('button');
    b.className = 'day-chip';
    b.type = 'button';
    b.role = 'tab';
    b.textContent = d;
    b.setAttribute('aria-selected', String(d === selectedDay));
    if (d === todayKey()) b.classList.add('is-today');
    const count = schedule?.[d]?.length || 0;
    if (!count) b.classList.add('is-empty');
    else if (d !== selectedDay) {
      const dot = document.createElement('span');
      dot.className = 'dot';
      b.append(dot);
    }
    b.addEventListener('click', () => { selectedDay = d; render(); });
    return b;
  }));
}

function lessonEl(les, i) {
  const el = document.createElement('article');
  el.style.animationDelay = `${Math.min(i * 45, 320)}ms`;

  if (les.unparsed) {
    el.className = 'lesson kind-other';
    el.innerHTML = `<div class="lesson-time">—</div><div class="lesson-rule"></div>
      <div><div class="lesson-name"></div></div>`;
    el.querySelector('.lesson-name').textContent = les.raw;
    return el;
  }

  const status = selectedDay === todayKey() ? lessonStatus(les) : 'upcoming';
  el.className = `lesson kind-${les.kind} is-${status}`;

  const time = document.createElement('div');
  time.className = 'lesson-time';
  time.append(les.start);
  const small = document.createElement('small');
  small.textContent = les.end;
  time.append(small);

  const rule = document.createElement('div');
  rule.className = 'lesson-rule';

  const body = document.createElement('div');
  const name = document.createElement('div');
  name.className = 'lesson-name';
  name.textContent = les.name;

  const meta = document.createElement('div');
  meta.className = 'lesson-meta';
  const room = document.createElement('span');
  room.textContent = les.room ? `Room ${les.room}` : '—';
  const kind = document.createElement('span');
  kind.textContent = les.kind === 'lecture' ? 'Lecture' : 'Practice';
  meta.append(kind, sep(), room, sep(), text(les.instructor));

  const code = document.createElement('div');
  code.className = 'lesson-code';
  code.textContent = les.code;

  body.append(name, meta, code);
  el.append(time, rule, body);
  return el;
}

const sep = () => Object.assign(document.createElement('span'), { className: 'sep', textContent: '·' });
const text = (t) => Object.assign(document.createElement('span'), { textContent: t });

function renderTimeline() {
  const list = $('timeline');
  const lessons = schedule?.[selectedDay] || [];

  if (!lessons.length) {
    list.replaceChildren(Object.assign(document.createElement('div'), {
      className: 'empty',
      innerHTML: `<div class="big">Nothing scheduled</div><p>${DAY_FULL[selectedDay]} is clear.</p>`,
    }));
    return;
  }
  list.replaceChildren(...lessons.map(lessonEl));
}

function renderNextUp() {
  const el = $('nextUp');
  if (selectedDay !== todayKey()) { el.hidden = true; return; }
  const up = nextUp(schedule?.[todayKey()] || []);
  if (!up) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = '';
  if (up.inMin === 0) {
    el.append(text('In progress — '), bold(up.lesson.name),
      text(up.lesson.room ? `, room ${up.lesson.room}` : ''));
  } else {
    const h = Math.floor(up.inMin / 60), m = up.inMin % 60;
    const when = h ? `${h} h ${m} min` : `${m} min`;
    el.append(bold(up.lesson.name), text(` in ${when}`),
      text(up.lesson.room ? ` · room ${up.lesson.room}` : ''));
  }
}
const bold = (t) => Object.assign(document.createElement('b'), { textContent: t });

function renderHeader() {
  const now = new Date();
  $('topDate').textContent = now.toLocaleDateString(undefined,
    { weekday: 'long', day: 'numeric', month: 'long' });
  $('topTitle').textContent = selectedDay === todayKey() ? 'Today' : DAY_FULL[selectedDay];
}

function renderStatus() {
  // The status line was removed from the UI; the refresh button's spinner is the
  // only progress indicator now. Kept as a no-op so callers need not change.
}

function render() {
  renderHeader();
  renderDays();
  renderNextUp();
  renderTimeline();
  renderStatus();
}

// ── data ─────────────────────────────────────────────────────
async function fetchSchedule(username, password) {
  const s = new WspSession(RELAY_URL, 'StudentSchedule');
  await s.handshake();
  await s.announceBrowser();
  await s.setLanguage('en');
  const res = await s.login(username, password);
  if (!res.ok) throw new WspError(res.error);
  session = s;
  startHeartbeat(s);
  return parseSchedule(s);
}

let hbTimer = null;
function startHeartbeat(s) {
  clearInterval(hbTimer);
  const every = (s.cfg.heartbeatInterval || 120) * 1000;
  hbTimer = setInterval(() => s.heartbeat(), every);
}

async function refresh() {
  const creds = loadCreds();
  if (!creds) return showLogin();
  refreshing = true;
  $('refresh').classList.add('spinning');
  renderStatus();
  try {
    schedule = await fetchSchedule(creds.u, creds.p);
    saveCache(schedule);
  } catch (err) {
    if (err instanceof WspError && /login|password/i.test(err.message)) {
      localStorage.removeItem(CRED_KEY);
      return showLogin('Your saved password no longer works. Sign in again.');
    }
    console.warn('refresh failed:', err);
  } finally {
    refreshing = false;
    $('refresh').classList.remove('spinning');
    render();
  }
}

// ── journal ──────────────────────────────────────────────────
let journalSession = null;   // reused across subjects: one login, many fetches
let journalPidCache = null;

function renderSubjects() {
  const host = $('subjectList');
  const subjects = journal?.subjects || [];
  $('journalTerm').textContent = journal?.term || '—';
  $('journalTitle').textContent = 'Journal';
  $('journalBack').hidden = true;
  $('subjectDetail').hidden = true;
  host.hidden = false;

  if (!subjects.length) {
    host.replaceChildren(Object.assign(document.createElement('div'), {
      className: 'empty',
      innerHTML: journalLoading
        ? '<div class="big">Loading…</div><p>Fetching your subjects.</p>'
        : '<div class="big">No subjects</div><p>Nothing registered for this term.</p>',
    }));
    return;
  }

  host.replaceChildren(...subjects.map((sub, i) => {
    const b = document.createElement('button');
    b.className = 'subject';
    b.type = 'button';
    b.style.animationDelay = `${Math.min(i * 40, 260)}ms`;

    const left = document.createElement('div');
    left.append(
      Object.assign(document.createElement('div'), { className: 'subject-name', textContent: sub.name }),
      Object.assign(document.createElement('div'), { className: 'subject-code', textContent: sub.code }),
    );

    const chev = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chev.setAttribute('viewBox', '0 0 24 24');
    chev.setAttribute('class', 'chev');
    chev.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M9 6l6 6-6 6');
    chev.append(path);

    b.append(left, chev);
    b.addEventListener('click', () => openSubjectView(sub.key));
    return b;
  }));
}

function renderDetail() {
  const sub = (journal?.subjects || []).find((x) => x.key === openSubject);
  if (!sub) { openSubject = null; return renderSubjects(); }

  $('subjectList').hidden = true;
  $('subjectDetail').hidden = false;
  $('journalBack').hidden = false;
  $('journalTerm').textContent = sub.code;
  $('journalTitle').textContent = sub.name;

  const box = $('detailSummary');
  box.replaceChildren();
  // Always recompute from the records. A stored summary may have been produced
  // by an older, wronger rule, and preferring it kept showing a stale 0%.
  const sum = sub.records ? summarise(sub.records) : sub.summary;
  if (sum) {
    const cell = (value, label, cls = '') => {
      const d = document.createElement('div');
      if (cls) d.className = cls;
      d.append(Object.assign(document.createElement('b'), { textContent: value }),
               Object.assign(document.createElement('small'), { textContent: label }));
      return d;
    };
    box.append(
      cell(sum.attendancePct === null ? '—' : `${sum.attendancePct}%`, 'Attendance',
           sum.attendancePct === null ? '' : sum.attendancePct >= 70 ? 'stat-good' : 'stat-warn'),
      cell(sum.points === null ? '—' : String(sum.points), 'Points'),
      cell(String(sum.classes), 'Classes'),
    );
  }

  const rows = $('detailRows');
  if (sub.records === null) {
    rows.replaceChildren(Object.assign(document.createElement('div'), {
      className: 'empty', innerHTML: '<div class="big">Loading…</div><p>Fetching entries.</p>',
    }));
    return;
  }
  if (!sub.records.length) {
    rows.replaceChildren(Object.assign(document.createElement('div'), {
      className: 'empty',
      innerHTML: '<div class="big">No entries yet</div><p>Nothing recorded for this subject.</p>',
    }));
    return;
  }

  rows.replaceChildren(...sub.records.map((r, i) => {
    const el = document.createElement('article');
    el.className = 'record';
    el.style.animationDelay = `${Math.min(i * 30, 240)}ms`;

    const [dd, mm, yyyy] = (r.date || '').split('.');
    const date = document.createElement('div');
    date.className = 'record-date';
    date.append(dd && mm ? `${dd}.${mm}` : (r.date || '—'));
    if (yyyy) date.append(Object.assign(document.createElement('small'), { textContent: yyyy }));

    const mid = document.createElement('div');
    mid.append(Object.assign(document.createElement('div'),
      { className: 'record-lesson', textContent: r.lesson || '—' }));
    if (r.attendance) {
      const chip = document.createElement('span');
      chip.className = `chip ${presenceOf(r) || ''}`;   // present | late | absent
      chip.textContent = r.attendance;
      mid.append(chip);
    }
    if (r.comment) {
      mid.append(Object.assign(document.createElement('div'),
        { className: 'record-comment', textContent: r.comment }));
    }

    const hasScore = r.score !== null && r.score > 0;
    const score = document.createElement('div');
    score.className = `record-score ${hasScore ? '' : 'none'}`;
    score.textContent = hasScore ? r.score.toFixed(2) : '—';

    el.append(date, mid, score);
    return el;
  }));
}

function renderJournal() {
  if (openSubject) renderDetail();
  else renderSubjects();
}

/** One authenticated JournalView session, reused for every subject. */
async function getJournalSession(creds) {
  if (journalSession) return journalSession;
  const base = session && session.isLoggedIn
    ? session
    : await (async () => {
        const s0 = new WspSession(RELAY_URL, 'StudentSchedule');
        await s0.handshake(); await s0.announceBrowser(); await s0.setLanguage('en');
        const r = await s0.login(creds.u, creds.p);
        if (!r.ok) throw new WspError(r.error);
        session = s0;
        return s0;
      })();
  const js = await base.openView('JournalView', creds.u, creds.p);
  journalPidCache = journalPids(js);
  if (!journalPidCache.subject) {
    throw new WspError('Could not find the subject selector on JournalView. Saw: '
      + [...new Set(Object.keys(js.types).map((p) => js.cls(p).split('.').pop()))].join(', '));
  }
  journalSession = js;
  return js;
}

/** Subject list only — no per-subject rows. Entering the tab should be cheap. */
async function loadSubjects(creds) {
  if (journalLoading) return;
  journalLoading = true;
  if (tab === 'journal') renderJournal();
  try {
    const js = await getJournalSession(creds);
    const J = journalPidCache;

    let term = '';
    try {
      const y = await js.comboOptions(J.year);
      const ysel = extractSelected(y.raw);
      const t = await js.comboOptions(J.term);
      const tsel = extractSelected(t.raw);
      const yname = y.options.find((o) => ysel.includes(o.key))?.caption || '';
      const tname = t.options.find((o) => tsel.includes(o.key))?.caption || '';
      term = [tname, yname].filter(Boolean).join(' · ');
    } catch { /* header only */ }

    const { options } = await js.comboOptions(J.subject);
    const prev = new Map((journal?.subjects || []).map((s2) => [s2.key, s2]));
    journal = {
      term,
      subjects: options.filter((o) => o.caption).map((o) => {
        const meta = parseSubject(o.caption);
        const old = prev.get(o.key);
        return { key: o.key, ...meta,
                 records: old?.records ?? null, summary: old?.summary ?? null };
      }),
    };
    saveJournal(journal);
  } catch (err) {
    console.warn('subject list failed:', err);
  } finally {
    journalLoading = false;
    if (tab === 'journal') renderJournal();
    renderStatus();
  }
}

/** Fetch one subject's rows, on demand. */
async function loadSubjectRecords(key) {
  const sub = (journal?.subjects || []).find((x) => x.key === key);
  const creds = loadCreds();
  if (!sub || !creds || !navigator.onLine || sub.loading) return;
  sub.loading = true;
  try {
    const js = await getJournalSession(creds);
    await js.selectOption(journalPidCache.subject, key);
    sub.records = toRecords(parseTable(js.lastChanges, journalPidCache.table));
    sub.summary = summarise(sub.records);
    saveJournal(journal);
  } catch (err) {
    console.warn('subject fetch failed:', err);
    if (sub.records === null) sub.records = [];
  } finally {
    sub.loading = false;
    if (tab === 'journal' && openSubject === key) renderDetail();
  }
}

function openSubjectView(key) {
  openSubject = key;
  renderJournal();
  const sub = (journal?.subjects || []).find((x) => x.key === key);
  if (sub && sub.records === null) loadSubjectRecords(key);
}

// ── tabs ─────────────────────────────────────────────────────
function setTab(next) {
  tab = next;
  for (const b of document.querySelectorAll('.tab')) {
    b.setAttribute('aria-selected', String(b.dataset.tab === tab));
  }
  $('view-schedule').hidden = tab !== 'schedule';
  $('view-journal').hidden = tab !== 'journal';
  if (tab === 'journal') {
    if (!journal) {
      const cached = loadJournal();
      if (cached?.data) journal = cached.data;
    }
    renderJournal();
    // Fetch the subject list once. Re-entering the tab must not refetch —
    // that was causing the list to visibly reload on every switch.
    const creds = loadCreds();
    const stale = !journal || (Date.now() - (loadJournal()?.at ?? 0)) > 6 * 3600e3;
    if (creds && navigator.onLine && !journalLoading && stale) loadSubjects(creds);
  } else {
    render();
  }
}

// ── screens ──────────────────────────────────────────────────
function showLogin(msg) {
  $('boot').hidden = true;
  $('app').hidden = true;
  $('login').hidden = false;
  const e = $('loginError');
  e.hidden = !msg;
  if (msg) e.textContent = msg;
}

function showApp() {
  $('boot').hidden = true;
  $('login').hidden = true;
  $('app').hidden = false;
  render();
}

$('loginForm').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const u = $('username').value.trim();
  const p = $('password').value;
  const btn = $('loginBtn');
  const err = $('loginError');
  err.hidden = true;
  btn.disabled = true;
  btn.classList.add('loading');
  try {
    schedule = await fetchSchedule(u, p);
    saveCache(schedule);
    if ($('remember').checked) {
      localStorage.setItem(CRED_KEY, JSON.stringify({ u, p }));
    }
    selectedDay = todayKey();
    showApp();
  } catch (e2) {
    err.textContent = e2 instanceof WspError ? e2.message : 'Could not reach WSP. Check your connection.';
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
});

for (const b of document.querySelectorAll('.tab')) {
  b.addEventListener('click', () => setTab(b.dataset.tab));
}
$('journalBack').addEventListener('click', () => { openSubject = null; renderJournal(); });

$('refresh').addEventListener('click', refresh);
/** No sign-out control in the UI right now; kept reachable from the console. */
window.wspSignOut = () => {
  localStorage.removeItem(CRED_KEY);
  localStorage.removeItem(CACHE_KEY);
  localStorage.removeItem(JOURNAL_KEY);
  journal = null; openSubject = null; journalSession = null; journalPidCache = null;
  clearInterval(hbTimer);
  schedule = null;
  showLogin();
};

addEventListener('online', renderStatus);
addEventListener('offline', renderStatus);
// Keep "now" markers honest without a full re-fetch.
setInterval(() => { if (!$('app').hidden) { renderNextUp(); renderTimeline(); } }, 60_000);

// ── boot ─────────────────────────────────────────────────────
(function boot() {
  const cached = loadCache();
  if (cached?.data) {
    schedule = cached.data;
    showApp();          // instant paint from cache, then refresh behind it
    if (navigator.onLine && loadCreds()) refresh();
    return;
  }
  if (loadCreds() && navigator.onLine) {
    refresh().then(() => (schedule ? showApp() : showLogin()));
    return;
  }
  showLogin();
})();

if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
