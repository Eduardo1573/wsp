"""
Select a subject in /JournalView and capture the grades table.

Never touches Year/Term — the server already defaults them (2026-2027 / Fall)
and the subject list arrives pre-filtered, so leaving them alone IS the
"keep the defaults" behaviour.

Read-only.

    export WSP_USER=... ; read -rs WSP_PASS && export WSP_PASS
    ./.venv/bin/python tools/probes/probe_journal_table.py [subject_index]
"""
import json
import os
import sys

sys.path.insert(0, "tools")
from vaadin import VaadinSession

user, pwd = os.environ.get("WSP_USER"), os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first")
pick = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SUBJ, TOTAL, TABLE = "41", "43", "60"

s = VaadinSession(view="JournalView")
s.handshake(); s.announce_browser(); s.set_language("en")
if not s.login(user, pwd):
    sys.exit(f"login rejected: {s.error_text()}")

defaults = {}
for pid, label in (("36", "Year"), ("38", "Term")):
    opts, raw = s.combo_options(pid)
    sel = s._extract_selected(raw)
    defaults[label] = next((o["caption"] for o in opts if o["key"] in sel), None)
print(f"=== DEFAULTS (untouched): {defaults} ===")

opts, _ = s.combo_options(SUBJ)
subjects = [o for o in opts if o["caption"]]
target = subjects[min(pick, len(subjects) - 1)]
print(f"\n=== SELECT [{pick}] {target['caption']} (key={target['key']}) ===")
s.select_option(SUBJ, target["key"])
after_select = list(s.last_changes)
print(f"  changes: {len(after_select)}  bytes: {len(json.dumps(after_select))}")

print("\n=== REQUEST TABLE ROWS ===")
s.request_rows(TABLE)
after_rows = list(s.last_changes)
print(f"  changes: {len(after_rows)}  bytes: {len(json.dumps(after_rows, ensure_ascii=False))}")

print("\n=== CLICK 'Show Total' ===")
s.click(TOTAL, label="Show Total")
after_total = list(s.last_changes)
print(f"  changes: {len(after_total)}  bytes: {len(json.dumps(after_total, ensure_ascii=False))}")

out = {"defaults": defaults, "subjects": subjects, "selected": target,
       "after_select": after_select, "after_rows": after_rows, "after_total": after_total,
       "state": s.state, "types": s.types, "hierarchy": s.hierarchy, "type_names": s.type_names}
with open("tools/dump_journal_table.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("\nwrote tools/dump_journal_table.json")

for name, ch in (("after_select", after_select), ("after_rows", after_rows), ("after_total", after_total)):
    blob = json.dumps(ch, ensure_ascii=False)
    if len(blob) > 500:
        print(f"\n=== {name} (first 1800 chars) ===\n{blob[:1800]}")
