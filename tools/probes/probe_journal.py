"""
Map /JournalView: find the subject / year / semester selectors and the Итог
button, then drive them once so we can see what the grades payload looks like.

Read-only — it selects a subject and asks for the summary, nothing else.

    export WSP_USER='e_levin'
    read -rs WSP_PASS && export WSP_PASS
    ./.venv/bin/python tools/probes/probe_journal.py
"""
import json
import os
import sys

sys.path.insert(0, "tools")
from vaadin import VaadinSession, VaadinError

user, pwd = os.environ.get("WSP_USER"), os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first (see docstring)")

s = VaadinSession(view="JournalView")
s.handshake()
s.announce_browser()
s.set_language("en")
if not s.login(user, pwd):
    sys.exit(f"login rejected: {s.error_text()}")
print("\n=== AUTHENTICATED JournalView TREE ===")
s.tree()

print("\n=== SELECTORS ===")
combos = s.find("com.vaadin.ui.ComboBox") + s.find("ComboBox")
combos = sorted(set(combos), key=lambda p: int(p))
combo_report = {}
for pid in combos:
    st = s.state.get(pid, {})
    try:
        opts, _ = s.combo_options(pid)
    except VaadinError as e:
        opts = [{"error": str(e)}]
    combo_report[pid] = {"class": s.cls(pid), "caption": st.get("caption"),
                         "state": st, "options": opts}
    print(f"\n  [{pid}] {s.cls(pid).split('.')[-1]}  caption={st.get('caption')!r}")
    for o in opts[:40]:
        mark = " <- selected" if o.get("selected") else ""
        print(f"        key={o.get('key'):>4}  {str(o.get('caption'))[:70]}{mark}")
    if len(opts) > 40:
        print(f"        … {len(opts)-40} more")

print("\n=== BUTTONS ===")
for pid in s.find("com.vaadin.ui.Button"):
    st = s.state.get(pid, {})
    icon = ((st.get("resources") or {}).get("icon") or {}).get("uRL", "")
    if st.get("caption") or icon:
        print(f"  [{pid}] caption={st.get('caption')!r} icon={icon!r} styles={st.get('styles')}")

print("\n=== TABLES / GRIDS ===")
for pid in s.find("com.vaadin.ui.Table", "com.vaadin.ui.Grid", "Table", "Grid"):
    st = s.state.get(pid, {})
    print(f"  [{pid}] {s.cls(pid)}  "
          f"{json.dumps({k: v for k, v in st.items() if k in ('caption','columns','visibleColumns','pageLength')}, ensure_ascii=False)[:200]}")

out = {"view": s.view, "state": s.state, "types": s.types, "hierarchy": s.hierarchy,
       "type_names": s.type_names, "combos": combo_report}
with open("tools/dump_journal.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"\nwrote tools/dump_journal.json ({len(s.types)} connectors)")
print("NOTE: contains your real grades — gitignored.")
