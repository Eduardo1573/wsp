"""
Capture /RegistrationOnline states — including the short window when the
attendance button is live.

    export WSP_USER='e_levin'; read -rs WSP_PASS && export WSP_PASS

    # one snapshot right now
    ./.venv/bin/python tools/probes/probe_attendance.py

    # watch: poll every 5s, auto-save a dump whenever the page changes
    ./.venv/bin/python tools/probes/probe_attendance.py --watch 5

Every distinct state lands in tools/dump_registration_<HHMMSS>.json, so you can
leave it running through a lesson and collect states 2 and 3 without timing it.
Read-only: it never clicks anything.
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "tools")
from vaadin import VaadinSession, VaadinError

user, pwd = os.environ.get("WSP_USER"), os.environ.get("WSP_PASS")
if not user or not pwd:
    sys.exit("set WSP_USER and WSP_PASS first")

watch = 0
if "--watch" in sys.argv:
    i = sys.argv.index("--watch")
    watch = float(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 5.0

VIEW = os.environ.get("WSP_VIEW", "RegistrationOnline")


def snapshot(s):
    """Everything that could distinguish one page state from another."""
    return {
        "types": s.types, "hierarchy": s.hierarchy, "type_names": s.type_names,
        "state": s.state,
    }


def signature(s):
    """Structure + visible text + enabled/caption flags."""
    bits = []
    for pid in sorted(s.types, key=lambda p: int(p) if p.isdigit() else 0):
        st = s.state.get(pid, {})
        bits.append(f"{pid}:{s.cls(pid)}:{st.get('caption')}:{st.get('text')}:"
                    f"{st.get('enabled')}:{st.get('styles')}")
    return hashlib.sha256("|".join(bits).encode()).hexdigest()[:12]


def describe(s):
    """One-line-per-interesting-connector summary."""
    out = []
    for pid in sorted(s.types, key=lambda p: int(p) if p.isdigit() else 0):
        cls = s.cls(pid)
        st = s.state.get(pid, {})
        short = cls.split(".")[-1]
        if short in ("VerticalLayout", "HorizontalLayout", "CssLayout", "GridLayout"):
            continue
        interesting = {k: v for k, v in st.items()
                       if k in ("caption", "text", "enabled", "styles", "description",
                                "disableOnClick", "readOnly", "value")}
        if interesting or short in ("Button", "Table", "CheckBox", "Label"):
            out.append(f"    [{pid}] {short}  {json.dumps(interesting, ensure_ascii=False)[:180]}")
    return "\n".join(out)


def connect():
    s = VaadinSession(view=VIEW, verbose=False)
    s.handshake()
    # A fresh session lands on the login screen; an authenticated cookie jar
    # goes straight into the view.
    if s.find("kz.kbtu.officeregistrar.widget.api.LoginView"):
        s.announce_browser()
        s.set_language("en")
        if not s.login(user, pwd):
            raise VaadinError(f"login rejected: {s.error_text()}")
    return s


def capture(tag=""):
    s = connect()
    sig = signature(s)
    stamp = time.strftime("%H%M%S")
    path = f"tools/dump_registration_{stamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"capturedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "view": VIEW, "signature": sig, **snapshot(s)}, f,
                  ensure_ascii=False, indent=1)
    print(f"\n[{time.strftime('%H:%M:%S')}] sig={sig} connectors={len(s.types)} {tag}")
    print(describe(s))
    print(f"    -> {path}")
    return sig


if not watch:
    capture("(single snapshot)")
    sys.exit(0)

print(f"watching {VIEW} every {watch}s — Ctrl-C to stop")
seen = set()
while True:
    try:
        s = connect()
        sig = signature(s)
        if sig not in seen:
            seen.add(sig)
            capture(f"(NEW STATE #{len(seen)})")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] unchanged ({sig})", end="\r", flush=True)
    except KeyboardInterrupt:
        print("\nstopped")
        break
    except Exception as e:
        print(f"\n[{time.strftime('%H:%M:%S')}] error: {type(e).__name__}: {e}")
    time.sleep(watch)
