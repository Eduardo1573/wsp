# Probes

Throwaway scripts that established the protocol facts now written up in
`../../PROTOCOL.md`. Kept because they show how each conclusion was reached, and
because they are the fastest way to re-derive things if WSP changes.

| Script | What it settled |
|---|---|
| `recon.py` | Handshake works over plain HTTP; dumps the connector tree |
| `probe_login.py` | `updateUuid` is what makes the login form appear |
| `probe_bisect.py` | Every legacy variable change failed — the format was wrong |
| `probe_format.py` | Params are `[varName, ["s", value]]`, not a map |
| `probe_click.py` / `probe_click2.py` | `MouseEventDetails` as a string → HTTP 500 |
| `probe_click3.py` | It is bean-serialized; proved by flipping the UI language |
| `probe_auth.py` | Full login round-trip, verified with fake credentials |

Run from the repo root: `./.venv/bin/python tools/probes/recon.py StudentSchedule`
