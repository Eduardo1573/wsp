# KBTU Schedule

A mobile web app for `wsp.kbtu.kz`, KBTU's student portal.

The portal is a Vaadin 7 desktop app that talks to its browser over a JSON
protocol. Rather than scrape the rendered DOM with Selenium, this speaks that
protocol directly — so there is no browser automation, no scraping, and no
machine that has to stay switched on at home.

```
phone (PWA)  ──►  relay (Cloudflare Worker)  ──►  wsp.kbtu.kz
             ◄──   adds CORS, stores nothing  ◄──
```

## Layout

| Path | What it is |
|---|---|
| `PROTOCOL.md` | How WSP's wire protocol works, and how each fact was established |
| `tools/vaadin.py` | Python UIDL client — the reverse-engineering workbench |
| `tools/parse_schedule.py` | Connector tree → structured schedule |
| `proxy/worker.js` | Stateless CORS relay |
| `web/` | The PWA (no build step — plain ES modules) |

## Setup

**1. Deploy the relay.** WSP sends no CORS headers, so browser JS cannot reach
it directly.

```bash
cd proxy
npx wrangler login
npx wrangler deploy          # -> https://wsp-relay.<you>.workers.dev
```

Then set `ALLOWED_ORIGINS` in `proxy/wrangler.toml` once the frontend has a URL,
so the relay can't be used as an open proxy.

**2. Point the app at it.** Edit `web/config.js`, replacing `YOUR-SUBDOMAIN`.

**3. Serve the app.**

```bash
cd web && python3 -m http.server 8899     # local
npx wrangler pages deploy web             # or deploy it
```

Open it on your phone and **Add to Home Screen** — it runs standalone, offline,
with your last schedule cached.

## Reverse-engineering workbench

`tools/` drives WSP from Python without a browser. Useful when the portal
changes or when adding a screen.

```bash
python3 -m venv .venv && ./.venv/bin/pip install requests
./tools/fetch_intermediate.sh        # WSP ships an incomplete cert chain

export WSP_USER='your_username'
read -rs WSP_PASS && export WSP_PASS  # typed silently, stays out of shell history
./.venv/bin/python tools/login_and_dump.py
./.venv/bin/python tools/parse_schedule.py
```

`tools/dump_*.json` holds real student data and is gitignored.

## Privacy

Credentials are held on your device and sent to WSP through your own relay. The
relay is stateless: no sessions, no storage, no logging of request bodies. It
does still *transit* the password, which is unavoidable for a web app — WSP
needs the plaintext to authenticate. If that is not acceptable, the same
frontend can be wrapped with Capacitor so it talks to WSP directly from the
device and no relay exists at all.

"Stay signed in" stores your credentials in `localStorage` on that device only.
Leave it unchecked on shared machines.
