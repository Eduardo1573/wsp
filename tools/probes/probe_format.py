import sys, uuid
sys.path.insert(0, "tools")
from vaadin import VaadinSession
LS_RPC = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"

def fresh():
    s = VaadinSession(view="StudentSchedule", verbose=False)
    s.handshake()
    s.rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]])
    return s

VARIANTS = {
  'A  ["text", ["s","pw"]]':  ["text", ["s", "zz_fake_pw"]],
  'B  ["text", "pw"]':        ["text", "zz_fake_pw"],
  'C  ["text", {"s":"pw"}]':  ["text", {"s": "zz_fake_pw"}],
  'D  [["s","text"],["s","pw"]]': [["s","text"], ["s","zz_fake_pw"]],
}
for name, params in VARIANTS.items():
    s = fresh()
    try:
        fr = s.rpc([["15", "v", "v", params]])
        err = (fr[-1].get("meta") or {}).get("appError")
        print(f"{'ERROR' if err else '  OK '}  {name}")
    except Exception as e:
        print(f"EXC    {name}  {type(e).__name__}")
