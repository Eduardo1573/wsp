import sys, uuid, json
sys.path.insert(0, "tools")
from vaadin import VaadinSession
LS_RPC  = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"
BTN_RPC = "com.vaadin.shared.ui.button.ButtonServerRpc"

def fresh():
    s = VaadinSession(view="StudentSchedule", verbose=False)
    s.handshake()
    s.rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]])
    return s

BEAN = {"button":"LEFT","clientX":120,"clientY":240,"altKey":False,"ctrlKey":False,
        "metaKey":False,"shiftKey":False,"type":1,"relativeX":12,"relativeY":10}

CANDS = {
  "bean object":            [BEAN],
  "bean object, type=0":    [dict(BEAN, type=0)],
  "no params":              [],
  "null param":             [None],
  "empty object":           [{}],
}
for name, params in CANDS.items():
    s = fresh()
    before = s.state.get("17",{}).get("caption")
    try:
        fr = s.rpc([["7", BTN_RPC, "click", params]])
        err = (fr[-1].get("meta") or {}).get("appError")
        after = s.state.get("17",{}).get("caption")
        print(f"  {'ERROR' if err else '  OK '}  {name:22s} login-btn caption: {before!r} -> {after!r}")
    except Exception as e:
        print(f"  EXC    {name:22s} {type(e).__name__}")
