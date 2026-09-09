"""
Log into WSP with YOUR credentials and dump the authenticated component tree.

Your password is read from the environment, never printed, and never leaves this
machine. PasswordField contents are masked in all output.

    export WSP_USER='e_levin'
    read -rs WSP_PASS && export WSP_PASS      # typed silently, not in shell history
    ./.venv/bin/python tools/login_and_dump.py

Writes tools/dump_schedule.json (gitignored — contains your real schedule).
"""
import json
import os
import sys

sys.path.insert(0, "tools")
from vaadin import VaadinSession

user = os.environ.get("WSP_USER")
pwd = os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first (see docstring)")

view = os.environ.get("WSP_VIEW", "StudentSchedule")
s = VaadinSession(view=view)
s.handshake()
s.announce_browser()
s.set_language("en")

ok = s.login(user, pwd)
print(f"\nlogin -> {ok}")
if not ok and s.error_text():
    sys.exit(f"rejected: {s.error_text()}")

print("\n=== AUTHENTICATED TREE ===")
s.tree()

print("\n=== NON-LAYOUT COMPONENTS (the data-bearing ones) ===")
SKIP = ("Layout", "Panel", "CssLayout")
for pid in sorted(s.types, key=lambda p: int(p)):
    c = s.cls(pid)
    if any(k in c for k in SKIP):
        continue
    st = {k: v for k, v in s.state.get(pid, {}).items()
          if k in ("caption", "text", "value", "columns", "visibleColumns", "pageLength", "selectable")}
    print(f"  [{pid}] {c}  {json.dumps(st, ensure_ascii=False)[:220]}")

out = {"view": s.view, "state": s.state, "types": s.types,
       "hierarchy": s.hierarchy, "type_names": s.type_names,
       "server_rpc": s.server_rpc}
dest = os.environ.get("WSP_OUT") or f"tools/dump_{view.lower()}.json"
with open(dest, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"\nwrote {dest} ({len(s.types)} connectors)")
