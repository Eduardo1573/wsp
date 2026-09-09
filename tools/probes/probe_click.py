import sys, uuid
sys.path.insert(0, "tools")
from vaadin import VaadinSession
LS_RPC  = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"
BTN_RPC = "com.vaadin.shared.ui.button.ButtonServerRpc"

def fresh():
    s = VaadinSession(view="StudentSchedule", verbose=False)
    s.handshake()
    s.rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]])
    return s

CANDS = {
  "LEFT,...,type=1":  "LEFT,120,240,false,false,false,false,1,12,10",
  "LEFT,...,type=0":  "LEFT,120,240,false,false,false,false,0,12,10",
  "0,...,type=1":     "0,120,240,false,false,false,false,1,12,10",
}
for name, med in CANDS.items():
    s = fresh()
    fr = s.rpc([["17", BTN_RPC, "click", [med]]])
    err = (fr[-1].get("meta") or {}).get("appError")
    new = sorted(set(s.types) - {"0","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18"}, key=lambda p:int(p))
    print(f"  {'ERROR' if err else '  OK '}  {name:20s} new_pids={new}")
