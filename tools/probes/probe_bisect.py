import sys, uuid, json
sys.path.insert(0, "tools")
from vaadin import VaadinSession

LS_RPC = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"

def fresh():
    s = VaadinSession(view="StudentSchedule", verbose=False)
    s.handshake()
    s.rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]])
    return s

CASES = {
  "password text":        [["15", "v", "v", [{"text": "zz_fake_pw"}]]],
  "combobox filter+page": [["14", "v", "v", [{"filter": "zz_fake_user", "page": 0}]]],
  "combobox newitem":     [["14", "v", "v", [{"newitem": "zz_fake_user"}]]],
  "combobox selected":    [["14", "v", "v", [{"selected": ["zz_fake_user"]}]]],
  "checkbox state":       [["16", "v", "v", [{"state": False}]]],
}

for name, calls in CASES.items():
    s = fresh()
    try:
        fr = s.rpc(calls)
        err = (fr[-1].get("meta") or {}).get("appError")
        ch  = fr[-1].get("changes")
        n   = len(ch) if isinstance(ch, list) else len(ch or {})
        print(f"{'ERROR ' if err else 'ok    '} {name:24s} changes={n} "
              f"{'<- ' + err['caption'] if err else ''}")
    except Exception as e:
        print(f"EXC    {name:24s} {type(e).__name__}: {e}")
