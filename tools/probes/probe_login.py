import sys, uuid
sys.path.insert(0, "tools")
from vaadin import VaadinSession

LS_RPC = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"

view = sys.argv[1] if len(sys.argv) > 1 else "StudentSchedule"
s = VaadinSession(view=view)
s.handshake()

browser_uuid = str(uuid.uuid4())
print(f"\n>>> sending updateUuid({browser_uuid}) to LocalStorage connector pid=18\n")
s.rpc([["18", LS_RPC, "updateUuid", [browser_uuid]]], label="updateUuid")

print("\n=== TREE AFTER updateUuid ===")
s.tree()

print("\n=== FULL STATE: login fields ===")
import json
for pid in ["12","13","14","15","16","17"]:
    print(f"\n--- pid {pid}  {s.cls(pid)} ---")
    print(json.dumps(s.state.get(pid, {}), ensure_ascii=False, indent=1)[:1400])
