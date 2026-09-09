"""
Fetch every subject's journal in one session, to (a) validate the parser against
varied data and (b) measure whether preloading all subjects is affordable.

Read-only. Never touches Year/Term.

    export WSP_USER=... ; read -rs WSP_PASS && export WSP_PASS
    ./.venv/bin/python tools/probes/probe_all_subjects.py
"""
import json, os, sys, time
sys.path.insert(0, "tools")
from vaadin import VaadinSession
from parse_journal import parse_table, to_records, summarise

user, pwd = os.environ.get("WSP_USER"), os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first")
SUBJ, TABLE = "41", "60"

t0 = time.time()
s = VaadinSession(view="JournalView", verbose=False)
s.handshake(); s.announce_browser(); s.set_language("en")
if not s.login(user, pwd):
    sys.exit(f"login rejected: {s.error_text()}")
print(f"login + handshake: {time.time()-t0:.2f}s")

defaults = {}
for pid, label in (("36", "Year"), ("38", "Term")):
    opts, raw = s.combo_options(pid)
    sel = s._extract_selected(raw)
    defaults[label] = next((o["caption"] for o in opts if o["key"] in sel), None)
print(f"defaults: {defaults}\n")

opts, _ = s.combo_options(SUBJ)
subjects = [o for o in opts if o["caption"]]

results, total = [], 0.0
for o in subjects:
    t = time.time()
    s.select_option(SUBJ, o["key"])
    dt = time.time() - t
    total += dt
    tab = parse_table(s.last_changes, pid=TABLE)
    recs = to_records(tab) if tab else []
    summ = summarise(recs)
    results.append({"subject": o["caption"], "key": o["key"],
                    "records": recs, "summary": summ, "seconds": round(dt, 2)})
    print(f"{o['caption'][:52]:54s} {dt:.2f}s  rows={summ['classes']:>3} "
          f"att={summ['attendance_pct']}%  avg={summ['average']}")

print(f"\nall {len(subjects)} subjects: {total:.2f}s  (avg {total/len(subjects):.2f}s each)")

nonzero = [r for res in results for r in res["records"] if r["score"] not in (None, 0.0)]
commented = [r for res in results for r in res["records"] if r["comment"]]
statuses = sorted({r["attendance"] for res in results for r in res["records"] if r["attendance"]})
print(f"\nattendance values seen : {statuses}")
print(f"rows with non-zero score: {len(nonzero)}  -> {nonzero[:5]}")
print(f"rows with a comment     : {len(commented)} -> {commented[:3]}")

with open("tools/dump_journal_all.json", "w", encoding="utf-8") as f:
    json.dump({"defaults": defaults, "results": results}, f, ensure_ascii=False, indent=1)
print("\nwrote tools/dump_journal_all.json")
