"""
Walk /StudentFiles down to actual files and show how downloading is wired.

    export WSP_USER='e_levin'; read -rs WSP_PASS && export WSP_PASS

    # follow an explicit path of row indices (0-based) per level
    ./.venv/bin/python tools/probes/probe_files.py 2 3

    # or auto-descend into the first folder until files appear (max 6 levels)
    ./.venv/bin/python tools/probes/probe_files.py --auto

Read-only: navigates and reads; never downloads or modifies anything.
"""
import json
import os
import sys

sys.path.insert(0, "tools")
from vaadin import VaadinSession
from parse_journal import parse_table

user, pwd = os.environ.get("WSP_USER"), os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first")

args = [a for a in sys.argv[1:] if a != "--auto"]
auto = "--auto" in sys.argv
path = [int(a) for a in args] if args else []

s = VaadinSession(view="StudentFiles", verbose=False)
s.handshake()
s.announce_browser()
s.set_language("en")
if not s.login(user, pwd):
    sys.exit(f"login rejected: {s.error_text()}")
print("logged in")

TABLE = lambda: (s.find("com.vaadin.ui.Table") or [None])[0]
MENUBAR = lambda: (s.find("com.vaadin.ui.MenuBar") or [None])[0]


def icon_of(component):
    """component cell looks like ["33", {"id": "90", "cached": true}]"""
    try:
        pid = component[1]["id"]
    except Exception:
        return None
    res = (s.state.get(str(pid), {}).get("resources") or {}).get("source") or {}
    return res.get("uRL")


def listing():
    t = parse_table(s.legacy_of(TABLE()), pid=TABLE()) or {}
    out = []
    for r in t.get("rows", []):
        icons = [icon_of(c) for c in r["components"]]
        is_folder = any(i and "folder" in i for i in icons if i)
        out.append({
            "key": r["key"],
            "name": next((c for c in r["text"] if c), ""),
            "icons": [i for i in icons if i],
            "isFolder": is_folder,
            "components": r["components"],
            "cells": r["cells"],
        })
    return out, t.get("columns", [])


def menu(word):
    for it in s.menu_items(MENUBAR()):
        if (it["text"] or "").strip().lower() == word:
            return it
    return None


def enter(row):
    s.rpc([[TABLE(), "v", "v", ["selected", ["S", [row["key"]]]]]],
          label=f"select {row['name'][:28]}", raise_on_error=False)
    item = menu("enter")
    if not item:
        return False
    s.click_menu(MENUBAR(), item["id"])
    return True


def show(level, rows, cols):
    print(f"\n--- LEVEL {level}  columns={cols}  rows={len(rows)} ---")
    for i, r in enumerate(rows):
        kind = "DIR " if r["isFolder"] else "FILE"
        print(f"  [{i}] {kind} key={r['key']:>3}  {r['name'][:58]}")
        if not r["isFolder"]:
            print(f"        icons={r['icons']}  cells={r['cells']}")
            for c in r["components"]:
                print(f"        component: {json.dumps(c, ensure_ascii=False)[:200]}")


def download_plumbing():
    hits = []
    for pid in sorted(s.types, key=lambda p: int(p)):
        cls = s.cls(pid)
        res = s.state.get(pid, {}).get("resources") or {}
        urls = [v.get("uRL", "") for v in res.values() if isinstance(v, dict)]
        if any(u and not u.startswith("theme://") for u in urls) or \
           any(k in cls for k in ("Download", "Opener", "Extension", "Upload", "Link")):
            hits.append(f"  [{pid}] {cls}  {json.dumps(res, ensure_ascii=False)[:300]}")
    return hits


level = 0
while True:
    rows, cols = listing()
    show(level, rows, cols)
    files = [r for r in rows if not r["isFolder"]]
    if files:
        print(f"\n*** FOUND {len(files)} FILE ROW(S) at level {level} ***")
        break
    if level >= 6 or not rows:
        print("\n(no files found within depth limit)")
        break
    idx = path[level] if level < len(path) else (0 if auto or level >= len(path) else 0)
    if level >= len(path) and not auto:
        print("\n(no further path given; pass more indices or --auto)")
        break
    target = rows[min(idx, len(rows) - 1)]
    print(f"\n>>> entering [{idx}] {target['name']}")
    if not enter(target):
        print("no Enter menu item")
        break
    level += 1

print("\n--- DOWNLOAD PLUMBING ---")
hits = download_plumbing()
print("\n".join(hits) if hits else "  (none)")

print("\n--- ALL CONNECTOR CLASSES NOW PRESENT ---")
print("  " + ", ".join(sorted({s.cls(p).split(".")[-1] for p in s.types})))

with open("tools/dump_files.json", "w", encoding="utf-8") as f:
    json.dump({"state": s.state, "types": s.types, "hierarchy": s.hierarchy,
               "type_names": s.type_names, "legacy": s.legacy}, f,
              ensure_ascii=False, indent=1)
print("\nwrote tools/dump_files.json")
