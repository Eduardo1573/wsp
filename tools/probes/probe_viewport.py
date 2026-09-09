"""Does WSP render a different component tree for small viewports?"""
import sys, uuid, json, time
sys.path.insert(0, "tools")
import requests
from vaadin import VaadinSession, LS_RPC, _strip_xss_prefix

VIEWPORTS = {
    "mac chrome 1512x945":  dict(sw=1512, sh=945, cw=1512, ch=832),
    "iphone 15 393x852":    dict(sw=393,  sh=852, cw=393,  ch=659),
    "iphone SE 375x667":    dict(sw=375,  sh=667, cw=375,  ch=553),
    "iphone standalone":    dict(sw=393,  sh=852, cw=393,  ch=852),
}

for name, vp in VIEWPORTS.items():
    s = VaadinSession(view="StudentSchedule", verbose=False)
    s.bootstrap()
    ts = int(time.time() * 1000)
    form = {
        "v-browserDetails": "1", "theme": "r5", "v-appId": s.app_id,
        "v-sh": str(vp["sh"]), "v-sw": str(vp["sw"]),
        "v-cw": str(vp["cw"]), "v-ch": str(vp["ch"]),
        "v-curdate": str(ts), "v-tzo": "-300", "v-dstd": "0",
        "v-rtzo": "-300", "v-dston": "false",
        "v-vw": str(vp["cw"]), "v-vh": "0",
        "v-loc": s.url, "v-wn": f"{s.app_id}-0.{ts%10**9}",
    }
    r = s.http.post(f"{s.url}/?v-{ts}", data=form, timeout=30,
                    headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    payload = json.loads(_strip_xss_prefix(r.text))
    s.ui_id = payload["v-uiId"]
    uidl = json.loads(payload["uidl"])
    s.csrf = uidl["Vaadin-Security-Key"]
    s._absorb(uidl)

    ls = s.find("com.r5.core.web.addon.LocalStorage")
    s.rpc([[ls[0] if ls else "18", LS_RPC, "updateUuid", [str(uuid.uuid4())]]],
          raise_on_error=False)
    combo = s.find("com.vaadin.ui.ComboBox")
    pw = s.find("com.vaadin.ui.PasswordField")
    print(f"{name:24s} LocalStorage={ls}  ComboBox={combo}  PasswordField={pw}")
