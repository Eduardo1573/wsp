/**
 * Parse Vaadin legacy Table UIDL into journal records.
 * Ported from tools/parse_journal.py; validated against real KBTU data.
 *
 * The table arrives as nested tagged arrays inside the `changes` payload:
 *   ["change", {pid}, [typeId, {cols, totalrows, …},
 *      ["rows", {}, ["tr", {key}, "02.09.2026", "Л21", "Absent", "0.00", ""], …],
 *      ["visiblecolumns", {}, ["column", {cid, caption}], …]]]
 */

function* walk(node) {
  yield node;
  if (Array.isArray(node)) for (const c of node) yield* walk(c);
}

function tagged(node, tag) {
  const out = [];
  for (const n of walk(node)) {
    if (Array.isArray(n) && n[0] === tag) out.push(n);
  }
  return out;
}

export function parseTable(changes, pid) {
  for (const change of changes || []) {
    if (!Array.isArray(change) || change.length < 3 || change[0] !== 'change') continue;
    if (pid != null && String(change[1]?.pid) !== String(pid)) continue;
    const body = change[2];
    if (!Array.isArray(body) || typeof body[1] !== 'object' || body[1] === null) continue;
    const attrs = body[1];
    if (!('cols' in attrs) && !('totalrows' in attrs)) continue;

    const columns = tagged(body, 'column').map((c) => c[1]?.caption ?? '');
    const rows = tagged(body, 'tr').map((tr) => {
      // Cells are positional and may be plain strings OR embedded components
      // (an icon, a download button). Keep both: /StudentFiles puts the whole
      // download mechanism in a component cell.
      const cells = [];
      const components = [];
      for (const c of tr.slice(2)) {
        if (c !== null && typeof c === 'object') { cells.push(null); components.push(c); }
        else cells.push(c == null ? '' : String(c));
      }
      return {
        key: String(tr[1]?.key ?? ''),
        cells,
        text: cells.filter((c) => c !== null),
        components,
      };
    });
    return { columns, rows, totalrows: attrs.totalrows ?? rows.length };
  }
  return null;
}

/* Attendance is three-state: attended / late / absent.
 *
 * Matched by vocabulary rather than an allow-list of "present" wordings — an
 * unlisted variant used to fall through to absent, which is why every subject
 * once read 0%. Late is checked first so it is not swallowed by either of the
 * others, and anything else non-empty counts as attended. */
const LATE_RE = /late|опозд|кешік/i;
const ABSENT_RE = /absent|отсут|не\s*был|пропуск|қатыспа/i;

/** -> 'present' | 'late' | 'absent' | null (nothing recorded) */
export function attendanceKind(attendance) {
  const v = (attendance || '').trim();
  if (!v) return null;
  if (LATE_RE.test(v)) return 'late';
  if (ABSENT_RE.test(v)) return 'absent';
  return 'present';
}

export function isPresent(attendance) {
  const k = attendanceKind(attendance);
  return k === null ? null : k !== 'absent';
}

export function toRecords(table) {
  if (!table) return [];
  const idx = {};
  table.columns.forEach((c, i) => { idx[c.trim().toLowerCase()] = i; });
  const get = (cells, ...names) => {
    for (const n of names) {
      const i = idx[n];
      if (i != null && i < cells.length && cells[i] != null) return cells[i].trim();
    }
    return '';
  };
  return table.rows.map(({ cells }) => {
    const attendance = get(cells, 'attendance', 'присутствие', 'қатысу');
    const rawScore = get(cells, 'score', 'оценка', 'grade');
    const m = rawScore && rawScore.match(/-?\d+(?:[.,]\d+)?/);
    return {
      date: get(cells, 'date', 'дата'),
      lesson: get(cells, 'lesson', 'урок'),
      attendance,
      present: isPresent(attendance),
      score: m ? parseFloat(m[0].replace(',', '.')) : null,
      comment: get(cells, 'comment', 'комментарий'),
    };
  });
}

/** Attendance kind for a record, re-derived from the label rather than read from
 *  the stored flag. Cached entries may have been parsed by an older, wronger
 *  rule — deriving here means a logic fix takes effect immediately instead of
 *  waiting for every cache to expire. */
export function presenceOf(record) {
  return attendanceKind(record.attendance);
}

/** What the Итог / "Show Total" button reports — computed locally instead, so it
 *  costs no round-trip and still works offline.
 *
 *  A late arrival counts as half an attendance. */
export function summarise(records) {
  const kinds = records.map(presenceOf);
  const known = kinds.filter((k) => k !== null);
  const present = kinds.filter((k) => k === 'present').length;
  const late = kinds.filter((k) => k === 'late').length;
  const absent = kinds.filter((k) => k === 'absent').length;
  const credit = present + late / 2;
  const scored = records.filter((r) => r.score !== null);
  const points = scored.reduce((a, r) => a + r.score, 0);
  const graded = scored.filter((r) => r.score > 0);
  return {
    classes: records.length,
    attended: present,
    late,
    absent,
    attendancePct: known.length ? Math.round((1000 * credit) / known.length) / 10 : null,
    points: scored.length ? Math.round(points * 100) / 100 : null,
    average: graded.length
      ? Math.round((graded.reduce((a, r) => a + r.score, 0) / graded.length) * 100) / 100
      : null,
    graded: graded.length,
  };
}

/** "STAT2201 Statistics (STAT2201) (Fall)" -> {code:"STAT2201", name:"Statistics"}
 *  Everything from the first "(" is dropped, so level markers like "(А1)" go too —
 *  match courses against the schedule by code, not by name. */
export function parseSubject(raw) {
  const parts = raw.split('(')[0].split(/\s+/).filter(Boolean);
  return {
    code: parts[0] || '',
    name: parts.slice(1).join(' ').trim() || parts[0] || raw.trim(),
    raw,
  };
}

/** DD.MM.YYYY -> Date (WSP's format; Date.parse gets this wrong). */
export function parseDate(s) {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(s || '');
  return m ? new Date(+m[3], +m[2] - 1, +m[1]) : null;
}
