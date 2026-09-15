/**
 * Parse /StudentFiles — a server-side directory tree.
 *
 *   TableEntity
 *     ListToolBar > MenuBar        "Back" (id 8) / "Enter" (id 9)
 *     Table  columns [folder, name, file]
 *       folder cell -> Image component (folder.png | file.png)
 *       name   cell -> plain string
 *       file   cell -> Button component (download.png), whose child is a
 *                      FileDownloader carrying the actual URL
 *
 * Navigation is SERVER-SIDE state: selecting a row and clicking Enter changes
 * what the table paints. That means the session must be kept alive — a resync
 * or re-attach rebuilds the view and drops you back at the root.
 */
import { parseTable } from './journal.js';

const FOLDER_ICON = /folder\.png/i;

/** A component cell looks like ["33", {"id": "90", "cached": true}] */
function componentPid(cell) {
  try {
    return String(cell[1].id);
  } catch {
    return null;
  }
}

function iconUrl(s, pid) {
  return (s.state[pid]?.resources?.source || {}).uRL || null;
}

/** Button -> child FileDownloader -> its "dl" resource. */
function downloadFor(s, buttonPid) {
  for (const child of s.kids(buttonPid)) {
    if (!s.cls(child).endsWith('FileDownloader')) continue;
    const raw = (s.state[child]?.resources?.dl || {}).uRL;
    if (raw) return { downloaderPid: child, url: s.resourceUrl(raw), raw };
  }
  return null;
}

export function tablePid(s) {
  return s.find('com.vaadin.ui.Table')[0] || null;
}
export function menuPid(s) {
  return s.find('com.vaadin.ui.MenuBar')[0] || null;
}

export function menuItem(s, word) {
  const w = word.toLowerCase();
  const words = {
    enter: ['enter', 'войти', 'кіру', 'ашу', 'open'],
    back: ['back', 'назад', 'артқа', 'up'],
  }[w] || [w];
  return s.menuItems(menuPid(s)).find(
    (i) => words.includes((i.text || '').trim().toLowerCase())) || null;
}

/** Rows of the current directory. */
export function parseListing(s) {
  const tp = tablePid(s);
  if (!tp) return [];
  const t = parseTable(s.legacyOf(tp), tp);
  if (!t) return [];

  return t.rows.map((r) => {
    const pids = r.components.map(componentPid).filter(Boolean);
    const icons = pids.map((p) => iconUrl(s, p)).filter(Boolean);
    const isFolder = icons.some((u) => FOLDER_ICON.test(u));
    // The download button is the component that is a Button, not the icon Image.
    const buttonPid = pids.find((p) => s.cls(p) === 'com.vaadin.ui.Button');
    const dl = buttonPid ? downloadFor(s, buttonPid) : null;
    return {
      key: r.key,
      name: (r.text || []).find(Boolean) || '',
      isFolder,
      buttonPid: buttonPid || null,
      download: dl,
    };
  }).sort((a, b) => (b.isFolder - a.isFolder) || a.name.localeCompare(b.name));
}

/** Select a row, then click Enter. Both are required: Enter acts on selection. */
export async function enterFolder(s, row) {
  const tp = tablePid(s);
  await s.selectOption(tp, row.key);
  const item = menuItem(s, 'enter');
  if (!item) throw new Error('no Enter item in the toolbar');
  await s.clickMenu(menuPid(s), item.id);
}

export async function goBack(s) {
  const item = menuItem(s, 'back');
  if (!item) throw new Error('no Back item in the toolbar');
  await s.clickMenu(menuPid(s), item.id);
}

/** Fetch a file through the relay and hand it to the browser to save. */
export async function downloadFile(s, row) {
  if (!row.download?.url) throw new Error('no download URL for this row');
  const headers = {};
  if (s.cookies.size) headers['X-WSP-Cookie'] = s.cookieHeader;
  const resp = await fetch(row.download.url, { headers });
  if (!resp.ok) throw new Error(`download failed (${resp.status})`);

  const blob = await resp.blob();
  const disp = resp.headers.get('Content-Disposition') || '';
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disp);
  const name = m ? decodeURIComponent(m[1]) : row.name;

  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  a.rel = 'noopener';
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 30_000);
  return { name, size: blob.size, type: blob.type };
}
