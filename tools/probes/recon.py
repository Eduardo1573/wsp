import sys
sys.path.insert(0, "tools")
from vaadin import VaadinSession

view = sys.argv[1] if len(sys.argv) > 1 else "StudentSchedule"
s = VaadinSession(view=view)
s.handshake()
print("\n=== CONNECTOR TREE (unauthenticated) ===")
s.tree()
print("\n=== ALL CLASSES SEEN ===")
for tid, name in sorted(s.type_names.items(), key=lambda x: int(x[0])):
    pids = [p for p in s.types if str(s.types[p]) == str(tid)]
    print(f"  {name}   pids={sorted(pids, key=lambda p:int(p))}")
