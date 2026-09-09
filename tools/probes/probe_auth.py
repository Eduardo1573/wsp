"""Full login flow with deliberately FAKE credentials."""
import sys, uuid, json
sys.path.insert(0, "tools")
from vaadin import VaadinSession

LS_RPC  = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"
BTN_RPC = "com.vaadin.shared.ui.button.ButtonServerRpc"
CLICK   = {"button":"LEFT","clientX":120,"clientY":240,"altKey":False,"ctrlKey":False,
           "metaKey":False,"shiftKey":False,"type":1,"relativeX":12,"relativeY":10}
U, P = "zz_not_a_real_user_zz", "zz_not_a_real_password_zz"

s = VaadinSession(view="StudentSchedule", verbose=False)
s.handshake()
s.rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]])
s.rpc([["8", BTN_RPC, "click", [CLICK]]])          # pid 8 = GB flag -> English UI
print("UI language ->", s.state.get("17",{}).get("caption"))

before = set(s.types)
fr = s.rpc([
    ["14", "v", "v", ["newitem", ["s", U]]],
    ["15", "v", "v", ["text",    ["s", P]]],
    ["17", BTN_RPC, "click", [CLICK]],
])
err = (fr[-1].get("meta") or {}).get("appError")
print("login ->", "ERROR: " + err["caption"] if err else "no protocol error")
print("new connectors:", sorted(set(s.types) - before, key=lambda p: int(p)))
print("\n=== notifications / new components ===")
for pid in sorted(set(s.types) - before, key=lambda p: int(p)):
    print(f"  [{pid}] {s.cls(pid)}  {json.dumps(s.state.get(pid,{}), ensure_ascii=False)[:300]}")
print("\n=== meta ===")
print(json.dumps(fr[-1].get("meta"), ensure_ascii=False)[:900])
