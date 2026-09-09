import sys, uuid
sys.path.insert(0, "tools")
from vaadin import VaadinSession
LS_RPC  = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"
BTN_RPC = "com.vaadin.shared.ui.button.ButtonServerRpc"
MED     = "LEFT,120,240,false,false,false,false,1,12,10"

def fresh():
    s = VaadinSession(view="StudentSchedule", verbose=False)
    s.handshake()
    s.rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]])
    return s

# pid 7 = RU flag button. If the click format is valid, captions should switch to Russian.
s = fresh()
print("before:", {p: s.state[p].get("caption") for p in ("14","15","16","17") if p in s.state})
fr = s.rpc([["7", BTN_RPC, "click", [MED]]])
err = (fr[-1].get("meta") or {}).get("appError")
print("click ru-flag ->", "ERROR: " + err["caption"] if err else "ok")
print("after :", {p: s.state[p].get("caption") for p in ("14","15","16","17") if p in s.state})
