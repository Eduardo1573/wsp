/**
 * Regression tests for the schedule parsers.
 *
 * WSP serves two different trees depending on the viewport reported during the
 * handshake: a desktop AbsoluteLayout grid (v1) and, since Sept 2026, a
 * StudentScheduleMobileComponent (v2). Both must keep working — a phone gets
 * one, a laptop the other.
 *
 * The two fixtures capture the SAME week, so the parsers must agree exactly.
 * That equivalence is the real test: it catches a v2 regression even though v2
 * has a completely different shape.
 *
 *   node tools/test_parsers.mjs
 *
 * Fixtures hold real student data and are gitignored; the run skips if absent.
 */
import fs from 'node:fs';
import path from 'node:path';
import { parseScheduleV1, parseScheduleV2, parseSchedule, DAYS }
  from '../web/lib/schedule.js';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const F = (n) => path.join(HERE, 'fixtures', n);
const V1 = F('schedule-v1-2026-09-08.json');
const V2 = F('schedule-v2-2026-09-09.json');

function sessionFrom(file) {
  const d = JSON.parse(fs.readFileSync(file, 'utf8'));
  const cls = (p) => d.type_names[String(d.types[String(p)])] || '?';
  return {
    types: d.types, state: d.state, cls,
    kids: (p) => d.hierarchy[String(p)] || [],
    text: (p) => d.state[String(p)]?.text,
    styles: (p) => d.state[String(p)]?.styles || [],
    descendants(p) {
      const out = [], stack = [String(p)];
      while (stack.length) { const c = stack.pop(); out.push(c); stack.push(...this.kids(c)); }
      return out;
    },
    find(...names) {
      return Object.keys(d.types)
        .filter((p) => names.some((n) => cls(p) === n || cls(p).endsWith(n)))
        .sort((a, b) => Number(a) - Number(b));
    },
  };
}

let failed = 0;
const check = (name, cond, detail = '') => {
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
  if (!cond) failed++;
};

for (const f of [V1, V2]) {
  if (!fs.existsSync(f)) {
    console.log(`skipped: missing fixture ${path.basename(f)}`);
    console.log('regenerate with: WSP_OUT=... ./.venv/bin/python tools/login_and_dump.py');
    process.exit(0);
  }
}

const s1 = sessionFrom(V1);
const s2 = sessionFrom(V2);
const a = parseScheduleV1(s1);
const b = parseScheduleV2(s2);
const norm = (l) => `${l.start}-${l.end} ${l.code} ${l.kind} ${l.room} | ${l.name} | ${l.instructor}`;

console.log('schedule parsers');
check('v1 parses the desktop fixture', Object.values(a).flat().length === 12,
      `${Object.values(a).flat().length} lessons`);
check('v2 parses the mobile fixture', b && Object.values(b).flat().length === 12,
      `${b ? Object.values(b).flat().length : 0} lessons`);
check('v2 returns null on a desktop tree', parseScheduleV2(s1) === null);
check('v1 still works on a desktop tree', parseScheduleV1(s1) !== null);
check('dispatcher handles desktop', Object.values(parseSchedule(s1)).flat().length === 12);
check('dispatcher handles mobile', Object.values(parseSchedule(s2)).flat().length === 12);

for (const d of DAYS) {
  const xs = (a[d] || []).map(norm);
  const ys = ((b || {})[d] || []).map(norm);
  check(`${d} identical across layouts`, JSON.stringify(xs) === JSON.stringify(ys),
        `v1=${xs.length} v2=${ys.length}`);
}

const wed = (b || {}).Wed || [];
check('consecutive hours merged (STAT2201 09:00-11:00)',
      wed.some((l) => l.code === 'STAT2201' && l.start === '09:00' && l.end === '11:00'));
check('room with dots/parens survives (ДМиС)',
      ((b || {}).Thu || []).some((l) => l.room.includes('Игровой зал') && l.room.includes('(юн)')));
check('course name keeps its level marker (А1)',
      ((b || {}).Mon || []).some((l) => l.name === 'General Kazakh language 1 (А1)'));

console.log(failed ? `\n${failed} check(s) failed` : '\nall checks passed');
process.exit(failed ? 1 : 0);
