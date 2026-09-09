"""
Find the wire encoding that actually registers a ComboBox selection.

AbstractSelect.changeVariables() reads "selected" as a String[], so the UidlValue
type tag probably has to be "S" (VTYPE_STRINGARRAY) rather than the generic "a".
Try the candidates and see which one makes the table populate.

    export WSP_USER=... ; read -rs WSP_PASS && export WSP_PASS
    ./.venv/bin/python tools/probes/probe_select_format.py
"""
import json
import os
import sys

sys.path.insert(0, "tools")
from vaadin import VaadinSession, LEGACY, BTN_RPC, CLICK_EVENT

user, pwd = os.environ.get("WSP_USER"), os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first")

SUBJ, TOTAL = "41", "43"

CANDIDATES = {
    'S  ["S", ["1"]]':            ["S", ["1"]],
    'a  ["a", [["s","1"]]]':      ["a", [["s", "1"]]],
    's  ["s", "1"]':              ["s", "1"],
}

def session():
    s = VaadinSession(view="JournalView", verbose=False)
    s.handshake(); s.announce_browser(); s.set_language("en")
    if not s.login(user, pwd):
        sys.exit(f"login rejected: {s.error_text()}")
    return s

for name, encoded in CANDIDATES.items():
    s = session()
    s.combo_options(SUBJ)                      # populate the server's key map
    before = set(s.types)
    # mimic VFilterSelect: filter + page + selected in one batch
    s.rpc([[SUBJ, LEGACY, LEGACY, ["filter", ["s", ""]]],
           [SUBJ, LEGACY, LEGACY, ["page", ["i", 0]]],
           [SUBJ, LEGACY, LEGACY, ["selected", encoded]]],
          label="select", raise_on_error=False)
    ch = json.dumps(s.last_changes, ensure_ascii=False)
    new = sorted(set(s.types) - before, key=lambda p: int(p))
    btn = s.state.get(TOTAL, {})
    print(f"\n{name}")
    print(f"   changes={len(s.last_changes)} bytes={len(ch)} newPids={new[:14]}")
    print(f"   ShowTotal state={json.dumps(btn, ensure_ascii=False)[:120]}")
    if len(ch) > 400:
        print(f"   PAYLOAD LOOKS REAL -> {ch[:400]}")
