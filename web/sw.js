/* Offline shell.
 *
 * Scope is deliberately narrow: ONLY the static files listed below are ever
 * cached. Everything else — above all the /StudentSchedule and /JournalView
 * relay paths — goes straight to the network.
 *
 * That matters more than it looks. Those relay responses carry live session
 * cookies (JSESSIONID + the sticky `route`) in X-WSP-Set-Cookie. Caching one
 * means replaying a dead session on the next launch, which manifests much later
 * as "no connector of type com.vaadin.ui.ComboBox" when the login form fails to
 * render. An allowlist is the only safe shape here; a denylist missed the
 * bootstrap GET.
 *
 * Schedule data is NOT cached here — it lives in localStorage (see app.js).
 */
const CACHE = 'wsp-shell-v17';

const SHELL = [
  './', './index.html', './styles.css', './app.js', './config.js',
  './lib/uidl.js', './lib/schedule.js', './lib/journal.js', './lib/attendance.js', './lib/files.js',
  './manifest.webmanifest',
  './icon.svg', './icon-152.png', './icon-167.png', './icon-180.png',
  './icon-192.png', './icon-512.png',
];

const shellPaths = new Set(SHELL.map((p) => new URL(p, self.location.href).pathname));
const indexPath = new URL('./index.html', self.location.href).pathname;

// Anything the relay handles. Never cached, never intercepted.
const RELAY = /^\/(StudentSchedule|JournalView|RegistrationOnline|StudentFiles)(\/(UIDL|HEARTBEAT))?\/?$|^\/[A-Za-z]+\/APP\/connector\//;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;   // fonts, CDNs — let the network handle it
  if (RELAY.test(url.pathname)) return;              // live WSP traffic — must never be cached

  // Navigations fall back to the cached shell so the app opens offline.
  if (request.mode === 'navigate') {
    e.respondWith(fetch(request).catch(() => caches.match(indexPath)));
    return;
  }


  if (!shellPaths.has(url.pathname)) return;         // unknown asset — straight to network

  // Network-first, cache as fallback. Cache-first meant a code change did not
  // reach an installed app until the worker updated AND the page was reloaded
  // twice — the page would render new HTML against stale JS. The shell is a few
  // tens of KB, so always revalidating costs little and keeps offline working.
  e.respondWith(
    fetch(request)
      .then((resp) => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return resp;
      })
      .catch(() => caches.match(request))
  );
});
