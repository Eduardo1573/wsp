# wsp-relay

Stateless CORS relay. WSP sends no `Access-Control-*` headers, so browser JS
cannot talk to it directly; this adds them and nothing else.

    npm i -g wrangler
    wrangler login
    wrangler deploy

Set `ALLOWED_ORIGINS` in `wrangler.toml` once your frontend has a URL.

## What it does and does not do

It stores nothing. No sessions, no KV, no logs of request bodies. The browser
holds the cookie jar and replays it via `X-WSP-Cookie`; the relay just forwards.

It still *transits* your password on the way to WSP — that is unavoidable for a
web app, since WSP needs the plaintext to authenticate you. If that is not
acceptable, build the Capacitor variant instead, where the same frontend talks
to WSP directly from the device and no relay exists.
