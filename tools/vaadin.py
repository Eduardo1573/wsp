"""
Minimal Vaadin 7.7 UIDL client — drives wsp.kbtu.kz with plain HTTP, no browser.

Reverse-engineered against the live site; see PROTOCOL.md for how each fact was
established. Once a screen's RPC sequence is understood here it gets ported to
web/src/lib/uidl.js for the real app.
"""
import json
import pathlib
import re
import time
import uuid

import requests

# wsp.kbtu.kz serves an INCOMPLETE certificate chain: only the leaf (CN=*.kbtu.kz),
# omitting the Sectigo DV R36 intermediate. macOS curl hides this by fetching the
# intermediate via AIA; OpenSSL/Node/undici do not. So we pin certifi + that
# intermediate. Rebuild with tools/fetch_intermediate.sh
CA_BUNDLE = str(pathlib.Path(__file__).parent / "certs" / "wsp-ca-bundle.pem")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# --- RPC interfaces, lifted from the compiled widgetset ---
LS_RPC  = "com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc"
BTN_RPC = "com.vaadin.shared.ui.button.ButtonServerRpc"

# Legacy variable changes use interface="v", method="v" and params
# [varName, UidlValue] where UidlValue is a [typeTag, value] pair.
LEGACY = "v"

# MouseEventDetails is bean-serialized (NOT the string form of .serialize()).
CLICK_EVENT = {"button": "LEFT", "clientX": 120, "clientY": 240,
               "altKey": False, "ctrlKey": False, "metaKey": False,
               "shiftKey": False, "type": 1, "relativeX": 12, "relativeY": 10}


def uidl_value(v):
    """Wrap a Python value as Vaadin's UidlValue [typeTag, value]."""
    if isinstance(v, bool):    return ["b", v]
    if isinstance(v, int):     return ["i", v]
    if isinstance(v, float):   return ["d", v]
    if isinstance(v, str):     return ["s", v]
    if v is None:              return ["n", None]
    if isinstance(v, (list, tuple)):
        return ["a", [uidl_value(x) for x in v]]
    raise TypeError(f"cannot encode {type(v)}")


def _strip_xss_prefix(text):
    """Vaadin guards UIDL responses with `for(;;);` to defeat JSON hijacking."""
    text = text.lstrip()
    return text[len("for(;;);"):] if text.startswith("for(;;);") else text


class VaadinError(RuntimeError):
    pass


class VaadinSession:
    def __init__(self, base="https://wsp.kbtu.kz", view="StudentSchedule", verbose=True):
        self.base = base.rstrip("/")
        self.view = view.strip("/")
        self.url = f"{self.base}/{self.view}"
        self.http = requests.Session()
        self.http.headers["User-Agent"] = UA
        self.http.verify = CA_BUNDLE
        self.verbose = verbose

        self.app_id = None
        self.cfg = {}
        self.ui_id = None
        self.csrf = None
        self.sync_id = 0
        self.client_id = 0
        self.browser_uuid = str(uuid.uuid4())

        # Mirror of server-side UI state, updated by every response.
        self.state, self.types, self.hierarchy, self.type_names = {}, {}, {}, {}
        self.last_frames, self.server_rpc, self.last_meta = [], [], {}
        self.last_changes = []
        # Latest legacy UIDL node per connector. Legacy components (Table,
        # MenuBar, selects) paint into `changes` rather than shared state, and a
        # later response that does not repaint them must not erase what we know.
        self.legacy = {}

    def log(self, *a):
        if self.verbose:
            print(*a)

    # ---------- 1. bootstrap ----------
    def bootstrap(self):
        r = self.http.get(self.url, timeout=30)
        r.raise_for_status()
        m = re.search(r'vaadin\.initApplication\("([^"]+)",(\{.*?\})\);', r.text, re.S)
        if not m:
            raise VaadinError("no vaadin.initApplication() — not a Vaadin view?")
        self.app_id, self.cfg = m.group(1), json.loads(m.group(2))
        self.log(f"[bootstrap] appId={self.app_id} "
                 f"vaadin={self.cfg['versionInfo']['vaadinVersion']} "
                 f"heartbeat={self.cfg.get('heartbeatInterval')}s")
        return self.cfg

    # ---------- 2. browser-details handshake ----------
    def handshake(self):
        if not self.app_id:
            self.bootstrap()
        ts = int(time.time() * 1000)
        form = {
            "v-browserDetails": "1", "theme": self.cfg.get("theme", "r5"),
            "v-appId": self.app_id,
            "v-sh": "926", "v-sw": "428", "v-cw": "428", "v-ch": "926",
            "v-curdate": str(ts), "v-tzo": "-300", "v-dstd": "0",
            "v-rtzo": "-300", "v-dston": "false", "v-vw": "428", "v-vh": "0",
            "v-loc": self.url, "v-wn": f"{self.app_id}-0.{ts % 10**9}",
        }
        r = self.http.post(f"{self.url}/?v-{ts}", data=form, timeout=30,
                           headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        r.raise_for_status()
        payload = json.loads(_strip_xss_prefix(r.text))
        self.ui_id = payload["v-uiId"]
        uidl = json.loads(payload["uidl"])
        self.csrf = uidl.get("Vaadin-Security-Key")
        # Legacy component data (Table rows, select options) rides in `changes`
        # on the handshake too, not only on RPC responses.
        self.last_changes = uidl.get("changes") or []
        self._absorb(uidl)
        self.log(f"[handshake] uiId={self.ui_id} csrf={self.csrf}")
        return uidl

    def resync(self):
        """Single-POST re-render: keeps the cached app_id so no bootstrap GET."""
        if not self.app_id:
            return self.reattach()
        self.state, self.types, self.hierarchy, self.type_names = {}, {}, {}, {}
        self.sync_id = self.client_id = 0
        return self.handshake()

    # ---------- 3. RPC ----------
    def rpc(self, calls, label="", raise_on_error=True):
        body = {"csrfToken": self.csrf, "rpc": calls,
                "syncId": self.sync_id, "clientId": self.client_id}
        r = self.http.post(f"{self.url}/UIDL/?v-uiId={self.ui_id}",
                           data=json.dumps(body).encode("utf-8"), timeout=30,
                           headers={"Content-Type": "application/json; charset=UTF-8"})
        r.raise_for_status()
        text = _strip_xss_prefix(r.text)
        try:
            frames = json.loads(text)
        except json.JSONDecodeError:
            raise VaadinError(f"non-JSON response (session dead?): {text[:300]}")
        if isinstance(frames, dict):
            frames = [frames]
        for f in frames:
            self._absorb(f)
        self.last_frames = frames
        self.last_changes = [c for f in frames for c in (f.get("changes") or [])]
        self.server_rpc = [c for f in frames for c in (f.get("rpc") or [])]
        self.last_meta = frames[-1].get("meta") or {}
        err = (frames[-1].get("meta") or {}).get("appError")
        if err and raise_on_error:
            raise VaadinError(f"server error on {label or calls}: {err.get('caption')}")
        self.log(f"[rpc {label}] syncId={self.sync_id}")
        return frames

    def heartbeat(self):
        """Must run every cfg['heartbeatInterval'] seconds or the session dies."""
        return self.http.post(f"{self.url}/HEARTBEAT/?v-uiId={self.ui_id}", timeout=15).status_code

    def click_menu(self, pid, item_id):
        """Vaadin 7 MenuBar reports a click through the legacy `clickedId`
        variable carrying the item's integer id."""
        return self.rpc([[str(pid), LEGACY, LEGACY, ["clickedId", ["i", int(item_id)]]]],
                        label=f"menu {pid}#{item_id}", raise_on_error=False)

    # ---------- high-level actions ----------
    def set_var(self, pid, name, value, label=None):
        return self.rpc([[str(pid), LEGACY, LEGACY, [name, uidl_value(value)]]],
                        label=label or f"set {name}")

    def combo_options(self, pid, filter_text="", page=0):
        """Open a ComboBox and read its options. Vaadin 7 selects are legacy
        components: their items arrive in the UIDL `changes` array as
        ["change", {...}, ["options", ..., [["so", {"key": "3", "caption": "..."}]]]]
        rather than in shared state."""
        self.rpc([[str(pid), LEGACY, LEGACY, ["filter", uidl_value(filter_text)]],
                  [str(pid), LEGACY, LEGACY, ["page", uidl_value(page)]]],
                 label=f"open combo {pid}", raise_on_error=False)
        return self._extract_options(self.last_changes), self.last_changes

    @staticmethod
    def _extract_options(changes):
        """Walk arbitrarily nested legacy UIDL for {'key':..,'caption':..} nodes."""
        found, stack = [], list(changes)
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                if "key" in n and "caption" in n:
                    found.append({"key": str(n["key"]), "caption": n["caption"],
                                  "selected": bool(n.get("selected"))})
                stack.extend(n.values())
            elif isinstance(n, list):
                stack.extend(n)
        return sorted(found, key=lambda o: int(o["key"]) if o["key"].isdigit() else 0)

    @staticmethod
    def _extract_selected(changes):
        """Legacy selects report their current value as a `selectedKeys` /
        `selected` variable rather than on the option nodes."""
        keys, stack = [], list(changes)
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                for k in ("selectedKeys", "selected", "selectedKey"):
                    if k in n:
                        v = n[k]
                        keys.extend(v if isinstance(v, list) else [v])
                stack.extend(n.values())
            elif isinstance(n, list):
                stack.extend(n)
        return [str(k) for k in keys if k not in (None, "", [])]

    def select_option(self, pid, key):
        """Set a legacy select's value by its server-assigned item key."""
        return self.rpc([[str(pid), LEGACY, LEGACY, ["selected", ["a", [["s", str(key)]]]]]],
                        label=f"select {pid}={key}", raise_on_error=False)

    @staticmethod
    def _extract_selected(changes):
        """Legacy selects report their current value via a selectedKeys/selected
        variable rather than on the option nodes themselves."""
        keys, stack = [], list(changes)
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                for k in ("selectedKeys", "selected", "selectedKey"):
                    if k in n:
                        v = n[k]
                        keys.extend(v if isinstance(v, list) else [v])
                stack.extend(n.values())
            elif isinstance(n, list):
                stack.extend(n)
        return [str(k) for k in keys if k not in (None, "", [])]

    def select_option(self, pid, key, filter_text=""):
        """Set a legacy select's value by its server-assigned item key.

        AbstractSelect.changeVariables() reads "selected" as a String[], so the
        UidlValue tag must be "S" (VTYPE_STRINGARRAY). The generic array tag "a"
        deserialises to the wrong Java type and the server drops the variable
        silently — no error, no changes. Verified against the live server: with
        "S" the response echoes back v.selected, with "a" it does not.

        filter + page accompany it, mirroring what VFilterSelect sends on pick.
        """
        return self.rpc([[str(pid), LEGACY, LEGACY, ["filter", ["s", filter_text]]],
                         [str(pid), LEGACY, LEGACY, ["page", ["i", 0]]],
                         [str(pid), LEGACY, LEGACY, ["selected", ["S", [str(key)]]]]],
                        label=f"select {pid}={key}", raise_on_error=False)

    def request_rows(self, pid, first=0, count=200):
        """Vaadin Tables lazy-load: rows only arrive when the client asks for a
        range. Without this the table connector exists but stays empty."""
        return self.rpc([[str(pid), LEGACY, LEGACY, ["firstvisible", ["i", first]]],
                         [str(pid), LEGACY, LEGACY, ["reqfirstrow", ["i", first]]],
                         [str(pid), LEGACY, LEGACY, ["reqrows", ["i", count]]]],
                        label=f"rows {pid}", raise_on_error=False)

    def click(self, pid, label=None):
        return self.rpc([[str(pid), BTN_RPC, "click", [CLICK_EVENT]]],
                        label=label or f"click {pid}")

    def announce_browser(self):
        """The LocalStorage addon reports a device UUID; the login form is only
        rendered after this arrives. Resolved by class, not pid."""
        pid = self.find_one("com.r5.core.web.addon.LocalStorage")
        r = self.rpc([[pid, LS_RPC, "updateUuid", [self.browser_uuid]]], label="updateUuid")
        if not self.find("com.vaadin.ui.PasswordField"):
            raise VaadinError("WSP did not render the login form (stale session?)")
        return r

    def set_language(self, lang="en"):
        """Header flag buttons, resolved by icon rather than pid."""
        want = {"kz": "flags/kz.png", "ru": "flags/ru.png", "en": "flags/gb.png"}[lang]
        for p in self.find("com.vaadin.ui.Button"):
            url = ((self.state.get(p, {}).get("resources") or {}).get("icon") or {}).get("uRL", "")
            if want in url:
                return self.click(p, label=f"lang={lang}")
        raise VaadinError(f"no {lang} language button found")

    def login(self, username, password, remember=False):
        """Returns True on success. Never logs the password."""
        user_pid = self.find_one("com.vaadin.ui.ComboBox")
        pass_pid = self.find_one("com.vaadin.ui.PasswordField")
        btn_pid  = self.find_by_caption("com.vaadin.ui.Button", ("Кіру", "Вход", "Log in"))
        calls = [
            [user_pid, LEGACY, LEGACY, ["newitem", uidl_value(username)]],
            [pass_pid, LEGACY, LEGACY, ["text",    uidl_value(password)]],
        ]
        if remember:
            cb = self.find_one("com.vaadin.ui.CheckBox")
            calls.append([cb, LEGACY, LEGACY, ["state", uidl_value(True)]])
        calls.append([btn_pid, BTN_RPC, "click", [CLICK_EVENT]])
        before = set(self.types)
        self.rpc(calls, label="login")
        err = self.error_text(set(self.types) - before)
        if err:
            self.log(f"[login] rejected: {err}")
            return False
        if self.server_rpc:
            self.log(f"[login] server->client rpc: {json.dumps(self.server_rpc)[:300]}")
        if self.last_meta:
            self.log(f"[login] meta: {json.dumps(self.last_meta, ensure_ascii=False)[:300]}")
        self.log("[login] accepted — reattaching to authenticated session")
        self.reattach()
        still_login = bool(self.find("kz.kbtu.officeregistrar.widget.api.LoginView"))
        if still_login:
            self.log("[login] WARNING: still on LoginView after reattach")
        return not still_login

    def reattach(self):
        """Re-run bootstrap+handshake on the SAME cookie jar. Vaadin logs a user in
        by instructing the client to reload; the session cookie is already
        authenticated, so the new UI comes back logged in."""
        self.state, self.types, self.hierarchy, self.type_names = {}, {}, {}, {}
        self.sync_id = self.client_id = 0
        self.app_id = None
        self.bootstrap()
        return self.handshake()

    def _descendants(self, pid):
        out, stack = [], [str(pid)]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(self.hierarchy.get(cur, []))
        return out

    def error_text(self, pids=None):
        """Auth failure renders a modal Window styled 'global-error' whose subtree
        holds the message Label. Search inside that window, not the whole UI."""
        pids = pids if pids is not None else set(self.types)
        for pid in pids:
            if self.cls(pid) != "com.vaadin.ui.Window":
                continue
            if "global-error" not in (self.state.get(pid, {}).get("styles") or []):
                continue
            for d in self._descendants(pid):
                if self.cls(d) == "com.vaadin.ui.Label":
                    txt = self.state.get(d, {}).get("text")
                    if txt:
                        return txt
            return "unknown error"
        return None

    def _remember_legacy(self, changes):
        for ch in changes or []:
            if isinstance(ch, list) and len(ch) >= 3 and ch[0] == "change":
                pid = str((ch[1] or {}).get("pid"))
                if pid:
                    self.legacy[pid] = ch

    def legacy_of(self, pid):
        """Latest legacy UIDL for a connector, as a one-element changes list."""
        node = self.legacy.get(str(pid))
        return [node] if node else []

    def menu_items(self, pid):
        """Flatten a MenuBar's items. Vaadin 7 MenuBar is legacy-painted, so the
        items arrive in UIDL `changes` keyed by text/id, not in shared state."""
        out, stack = [], list(self.legacy_of(pid))
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                if "text" in n and "id" in n:
                    out.append({"id": n.get("id"), "text": n.get("text"),
                                "enabled": n.get("enabled", True)})
                stack.extend(n.values())
            elif isinstance(n, list):
                stack.extend(n)
        seen, uniq = set(), []
        for it in out:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            uniq.append(it)
        return sorted(uniq, key=lambda x: (x["id"] is None, x["id"]))

    # ---------- state mirror ----------
    def _absorb(self, frame):
        sid = frame.get("syncId")
        if isinstance(sid, int) and sid >= 0:
            self.sync_id = sid
        if "clientId" in frame:
            self.client_id = frame["clientId"]
        self._remember_legacy(frame.get("changes"))
        for pid, st in (frame.get("state") or {}).items():
            self.state.setdefault(pid, {}).update(st)
        self.types.update(frame.get("types") or {})
        self.hierarchy.update(frame.get("hierarchy") or {})
        for name, tid in (frame.get("typeMappings") or {}).items():
            self.type_names[str(tid)] = name

    # ---------- introspection ----------
    def cls(self, pid):
        return self.type_names.get(str(self.types.get(str(pid))), "?")

    def find(self, *class_names):
        return sorted((p for p in self.types
                       if any(self.cls(p).endswith(c) or self.cls(p) == c for c in class_names)),
                      key=lambda p: int(p) if p.isdigit() else 10**9)

    def find_one(self, *class_names):
        hits = self.find(*class_names)
        if not hits:
            raise VaadinError(f"no connector of type {class_names}")
        return hits[0]

    def find_by_caption(self, class_name, captions):
        for p in self.find(class_name):
            if self.state.get(p, {}).get("caption") in captions:
                return p
        raise VaadinError(f"no {class_name} captioned {captions}")

    def root_pid(self):
        """After a re-attach the UI root is no longer pid 0."""
        children = {c for ch in self.hierarchy.values() for c in ch}
        roots = [p for p in self.types if p not in children]
        return roots[0] if roots else "0"

    def tree(self, root=None, depth=0, seen=None):
        if root is None:
            root = self.root_pid()
        seen = seen if seen is not None else set()
        if root in seen:
            return
        seen.add(root)
        st = self.state.get(root, {})
        secret = self.cls(root).endswith("PasswordField")
        bits = [f"{k}=" + ("'***'" if secret and k == "text" else f"{str(st[k])[:44]!r}")
                for k in ("caption", "text", "value", "id")
                if st.get(k) not in (None, "", [], {})]
        print("  " * depth + f"[{root}] {self.cls(root)}" + ("  " + " ".join(bits) if bits else ""))
        for ch in self.hierarchy.get(root, []):
            self.tree(ch, depth + 1, seen)
