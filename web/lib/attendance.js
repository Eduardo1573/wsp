/**
 * Parse /RegistrationOnline — the attendance-mark page.
 *
 * A teacher opens a short window during a lesson; a button appears and has to be
 * pressed before it closes.
 *
 *   RegistrationOnlineView
 *     VerticalHLayout (header, flags)
 *     VerticalLayout
 *       VerticalLayout [card]        <- one lesson
 *         Label [bold]  "Course<br>Teacher<br>Л27 (15:00 - 16:00)<br>1 minutes left"
 *         Button        "Отметиться" (enabled) | "Marked" (enabled: false)
 *
 * Availability is keyed off `enabled`, not the caption: captions are localised
 * ("Отметиться" / "Marked") and change with the UI language, while `enabled` is
 * the same signal in every locale.
 */

const MARKED_RE = /marked|отмеч|белгіленген/i;

/** "Л27 (15:00 - 16:00)" -> { lesson, start, end } */
const SLOT_RE = /^(\S+)\s*\((\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\)/;

/** "1 minutes left" / "Осталось 2 мин." -> 1 / 2 */
export function minutesLeft(text) {
  const m = /(\d+)/.exec(text || '');
  return m ? parseInt(m[1], 10) : null;
}

function decodeEntities(s) {
  return (s || '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
}

export function parseInfoLabel(html) {
  const lines = decodeEntities(html)
    .split(/<br\s*\/?>/i)
    .map((x) => x.replace(/<[^>]*>/g, '').trim())
    .filter(Boolean);
  const [course = '', teacher = '', slot = '', countdown = ''] = lines;
  const m = SLOT_RE.exec(slot);
  return {
    course,
    teacher,
    lesson: m ? m[1] : slot,
    start: m ? m[2].padStart(5, '0') : '',
    end: m ? m[3].padStart(5, '0') : '',
    countdown,
    minutesLeft: minutesLeft(countdown),
  };
}

/**
 * @param {import('./uidl.js').WspSession} s
 * @returns {Array<{buttonPid, status, caption, ...}>} one entry per lesson card
 */
export function parseAttendance(s) {
  const root = s.find('RegistrationOnlineView')[0] || s.find('RegistrationOnlineUI')[0];
  if (!root) return [];

  const out = [];
  for (const node of s.descendants(root)) {
    if (s.cls(node) !== 'com.vaadin.ui.VerticalLayout') continue;
    const kids = s.kids(node);
    const labelPid = kids.find((k) => s.cls(k) === 'com.vaadin.ui.Label');
    const buttonPid = kids.find((k) => s.cls(k) === 'com.vaadin.ui.Button');
    if (!labelPid || !buttonPid) continue;

    const st = s.state[buttonPid] || {};
    const caption = st.caption || '';
    // Vaadin omits `enabled` from shared state when it is true.
    const enabled = st.enabled !== false;
    const status = enabled ? 'available' : MARKED_RE.test(caption) ? 'marked' : 'closed';

    out.push({
      buttonPid,
      labelPid,
      caption,
      status,
      ...parseInfoLabel(s.text(labelPid)),
    });
  }
  // Stable order: by start time, then lesson code.
  return out.sort((a, b) => (a.start || '').localeCompare(b.start || '')
    || (a.lesson || '').localeCompare(b.lesson || ''));
}

export const hasActionable = (items) => items.some((i) => i.status === 'available');
