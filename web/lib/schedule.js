/**
 * Turn the WSP connector tree into structured schedule data.
 * Ported from tools/parse_schedule.py; validated against a real KBTU tree.
 */

export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const DAY_FULL = {
  Mon: 'Monday', Tue: 'Tuesday', Wed: 'Wednesday', Thu: 'Thursday',
  Fri: 'Friday', Sat: 'Saturday', Sun: 'Sunday',
};

// "CSCI2104 Databases Saimassayeva S. Л 450 (08:00-09:00)"
// Course names may contain parentheses — "General Kazakh language 1 (А1)" — and
// so may rooms — "Игровой зал Баскетбол ДМиС (юн)". Anchoring on the trailing
// time span and the "Surname I." instructor pattern stops one from swallowing
// the other; both name and room stay non-greedy.
const LESSON_RE = new RegExp(
  '^(\\S+)\\s+' +              // 1 course code
  '(.*?)\\s+' +               // 2 course name
  '(\\S+\\s+[A-ZА-ЯЁ]\\.)\\s+' + // 3 instructor "Surname I."
  '([ЛПлп])\\s+' +            // 4 Л lecture / П practice
  '(.*?)\\s*' +               // 5 room
  '\\((\\d{1,2}:\\d{2})\\s*-\\s*(\\d{1,2}:\\d{2})\\)\\s*$' // 6,7 times
);

const KIND = { 'Л': 'lecture', 'П': 'practice' };
const squash = (s) => s.replace(/\s{2,}/g, ' ').trim();
const pad = (t) => (t.length === 4 ? '0' + t : t);

export function parseLesson(raw) {
  const m = LESSON_RE.exec(raw.trim());
  if (!m) return { raw, unparsed: true };
  return {
    code: m[1],
    name: squash(m[2]),
    instructor: squash(m[3]),
    kind: KIND[m[4].toUpperCase()] || 'other',
    room: squash(m[5]),
    start: pad(m[6]),
    end: pad(m[7]),
  };
}

/** WSP emits one 40px block per hour; collapse consecutive blocks of the same
 *  class so a 3-hour lab reads as one entry rather than three. */
export function mergeRuns(lessons) {
  const out = [];
  for (const les of [...lessons].sort((a, b) => (a.start || '').localeCompare(b.start || ''))) {
    const prev = out.at(-1);
    const same = prev && !prev.unparsed && !les.unparsed
      && prev.code === les.code && prev.room === les.room
      && prev.kind === les.kind && prev.instructor === les.instructor
      && prev.end === les.start;
    if (same) prev.end = les.end;
    else out.push({ ...les });
  }
  return out;
}

const FULL_TO_SHORT = {
  Monday: 'Mon', Tuesday: 'Tue', Wednesday: 'Wed', Thursday: 'Thu',
  Friday: 'Fri', Saturday: 'Sat', Sunday: 'Sun',
  Понедельник: 'Mon', Вторник: 'Tue', Среда: 'Wed', Четверг: 'Thu',
  Пятница: 'Fri', Суббота: 'Sat', Воскресенье: 'Sun',
};
const dayKey = (t) => (DAYS.includes(t) ? t : FULL_TO_SHORT[(t || '').trim()] || null);

const KIND_CHAR = { 'Л': 'lecture', 'П': 'practice', 'L': 'lecture', 'P': 'practice' };

/**
 * Mobile layout (WSP, Sept 2026 onward). Served when the handshake reports a
 * small viewport; desktop viewports still get the v1 AbsoluteLayout grid.
 *
 *   StudentScheduleMobileComponent > VerticalLayout
 *     Label "Monday"                 <- day header
 *     HorizontalLayout               <- one lesson
 *       VerticalLayout [ "11:00", "12:00" ]
 *       VerticalLayout [ "LAN1175 General Kazakh language 1 (А1)",
 *                        "П · 251 ", "Mangysheva Z." ]
 *
 * Fields arrive pre-split here, so no regex is needed — a nice simplification
 * over v1, where everything was crammed into a single label.
 */
export function parseScheduleV2(s) {
  const root = s.find('StudentScheduleMobileComponent')[0];
  if (!root) return null;

  const days = Object.fromEntries(DAYS.map((d) => [d, []]));
  let current = null;
  let seen = false;

  // Children are a flat, ordered sequence of day headers and lesson rows.
  const container = s.kids(root).find((c) => s.kids(c).length) || root;
  for (const node of s.kids(container)) {
    const cls = s.cls(node);
    if (cls === 'com.vaadin.ui.Label') {
      const d = dayKey(s.text(node));
      if (d) current = d;
      continue;
    }
    if (cls !== 'com.vaadin.ui.HorizontalLayout' || !current) continue;

    const cols = s.kids(node).filter((c) => s.cls(c) === 'com.vaadin.ui.VerticalLayout');
    if (cols.length < 2) continue;
    const times = s.kids(cols[0]).map((c) => (s.text(c) || '').trim()).filter(Boolean);
    const info = s.kids(cols[1]).map((c) => (s.text(c) || '').trim());
    const [title = '', meta = '', instructor = ''] = info;

    const titleParts = title.split(/\s+/).filter(Boolean);
    const [kindChar, ...roomParts] = meta.split('·');
    const kc = (kindChar || '').trim().charAt(0).toUpperCase();

    days[current].push({
      code: titleParts[0] || '',
      name: titleParts.slice(1).join(' ').trim(),
      instructor: instructor.replace(/\s{2,}/g, ' ').trim(),
      kind: KIND_CHAR[kc] || 'other',
      room: roomParts.join('·').replace(/\s{2,}/g, ' ').trim(),
      start: times[0] || '',
      end: times[1] || times[0] || '',
    });
    seen = true;
  }
  return seen ? Object.fromEntries(Object.entries(days).map(([d, v]) => [d, mergeRuns(v)])) : null;
}

/** Desktop layout (the original). Kept as a fallback — WSP still serves it to
 *  large viewports, and it is what every pre-Sept-2026 capture looks like. */
export function parseScheduleV1(s) {
  const holders = s.find('ScheduleComponent').filter((p) => s.cls(p).includes('.api.'));
  const root = holders[0] || s.find('ScheduleComponent')[0];
  if (!root) throw new Error('no ScheduleComponent in tree');

  const days = Object.fromEntries(DAYS.map((d) => [d, []]));
  for (const col of s.descendants(root)) {
    if (s.cls(col) !== 'com.vaadin.ui.VerticalLayout') continue;
    // A day column is one whose subtree holds a bold Label naming the day.
    const header = s.descendants(col)
      .map((d) => (DAYS.includes(s.text(d)) && s.styles(d).includes('bold') ? s.text(d) : null))
      .find(Boolean);
    if (!header) continue;
    for (const node of s.descendants(col)) {
      if (!s.styles(node).includes('schedule-item')) continue;
      for (const lbl of s.descendants(node)) {
        const raw = s.text(lbl);
        if (raw) days[header].push(parseLesson(raw));
      }
    }
  }
  return Object.fromEntries(Object.entries(days).map(([d, v]) => [d, mergeRuns(v)]));
}

/** Try the mobile layout first, fall back to the desktop grid. WSP decides which
 *  it serves from the viewport we report during the handshake, so both must
 *  keep working. */
export function parseSchedule(s) {
  return parseScheduleV2(s) || parseScheduleV1(s);
}

/** Student name / group, for the header. */
export function parseStudent(s) {
  const comp = s.find('StudentInformationComponent')[0];
  if (!comp) return null;
  const texts = s.descendants(comp).map((d) => s.text(d)).filter(Boolean);
  return texts.length ? texts : null;
}

// ---- time helpers ----
export const toMin = (hhmm) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

export const todayKey = (d = new Date()) => DAYS[(d.getDay() + 6) % 7];

export function lessonStatus(les, now = new Date()) {
  const cur = now.getHours() * 60 + now.getMinutes();
  const a = toMin(les.start), b = toMin(les.end);
  if (cur >= a && cur < b) return 'now';
  if (cur < a) return 'upcoming';
  return 'past';
}

/** The next lesson today, and minutes until it starts. */
export function nextUp(lessons, now = new Date()) {
  const cur = now.getHours() * 60 + now.getMinutes();
  for (const l of lessons) {
    if (l.unparsed) continue;
    if (toMin(l.start) > cur) return { lesson: l, inMin: toMin(l.start) - cur };
    if (toMin(l.start) <= cur && cur < toMin(l.end)) return { lesson: l, inMin: 0 };
  }
  return null;
}
