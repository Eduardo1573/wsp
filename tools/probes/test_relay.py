"""Exercise the deployed relay exactly as web/lib/uidl.js does — the browser
holds the cookie jar and replays it via X-WSP-Cookie."""
import json, re, sys, time, uuid
import requests

RELAY = sys.argv[1] if len(sys.argv) > 1 else "https://wsp-relay.kbtu.workers.dev"
ORIGIN = "http://localhost:8899"
VIEW = "StudentSchedule"
LS_RPC = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"
BTN_RPC = "com.vaadin.shared.ui.button.ButtonServerRpc"
CLICK = {"button":"LEFT","clientX":120,"clientY":240,"altKey":False,"ctrlKey":False,
         "metaKey":False,"shiftKey":False,"type":1,"relativeX":12,"relativeY":10}

jar = {}
def call(path, **kw):
    h = dict(kw.pop("headers", {})); h["Origin"] = ORIGIN
    if jar: h["X-WSP-Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
    r = requests.request(kw.pop("method", "GET"), RELAY + path, headers=h, timeout=30, **kw)
    sc = r.headers.get("X-WSP-Set-Cookie")
    if sc:
        for pair in sc.split(";"):
            if "=" in pair:
                k, v = pair.strip().split("=", 1); jar[k] = v
    return r

strip = lambda t: t[len("for(;;);"):] if t.lstrip().startswith("for(;;);") else t

# 1. bootstrap
html = call(f"/{VIEW}").text
app_id = re.search(r'vaadin\.initApplication\("([^"]+)"', html).group(1)
print(f"1. bootstrap   appId={app_id}  cookies={list(jar)}")

# 2. handshake
ts = int(time.time() * 1000)
form = {"v-browserDetails":"1","theme":"r5","v-appId":app_id,"v-sh":"926","v-sw":"428",
        "v-cw":"428","v-ch":"926","v-curdate":str(ts),"v-tzo":"-300","v-dstd":"0",
        "v-rtzo":"-300","v-dston":"false","v-vw":"428","v-vh":"0",
        "v-loc":f"https://wsp.kbtu.kz/{VIEW}","v-wn":f"{app_id}-0.{ts%10**9}"}
r = call(f"/{VIEW}/?v-{ts}", method="POST", data=form,
         headers={"Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"})
payload = json.loads(strip(r.text))
ui_id, uidl = payload["v-uiId"], json.loads(payload["uidl"])
csrf = uidl["Vaadin-Security-Key"]
print(f"2. handshake   uiId={ui_id}  csrf={csrf[:8]}…")

# 3. updateUuid -> login form should materialise
def rpc(calls, sync, client):
    r = call(f"/{VIEW}/UIDL/?v-uiId={ui_id}", method="POST",
             headers={"Content-Type":"application/json; charset=UTF-8"},
             data=json.dumps({"csrfToken":csrf,"rpc":calls,"syncId":sync,"clientId":client}))
    return json.loads(strip(r.text))

frames = rpc([["18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]], 0, 0)
tm = {str(v): k for k, v in (frames[-1].get("typeMappings") or uidl.get("typeMappings", {})).items()}
types = {**uidl.get("types", {}), **(frames[-1].get("types") or {})}
state = {**uidl.get("state", {}), **(frames[-1].get("state") or {})}
found = {p: tm.get(str(types[p]), "?") for p in types}
form_bits = {p: state.get(p, {}).get("caption") for p, c in found.items()
             if c in ("com.vaadin.ui.ComboBox","com.vaadin.ui.PasswordField",
                      "com.vaadin.ui.CheckBox") or (c=="com.vaadin.ui.Button" and state.get(p,{}).get("caption"))}
print(f"3. updateUuid  login form -> {form_bits}")

# 4. reject fake credentials
f2 = rpc([["14","v","v",["newitem",["s","zz_fake_user"]]],
          ["15","v","v",["text",["s","zz_fake_pw"]]],
          ["17", BTN_RPC, "click", [CLICK]]],
         frames[-1].get("syncId",1), frames[-1].get("clientId",1))
labels = [v.get("text") for v in (f2[-1].get("state") or {}).values() if v.get("text")]
print(f"4. fake login  server says -> {labels}")
print("\nRELAY OK — full Vaadin protocol traverses the worker end to end.")
