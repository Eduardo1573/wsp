# wsp.kbtu.kz — Vaadin UIDL protocol

Everything here was established empirically against the live site, or decompiled
from the shipped widgetset. No credentials were used to derive it: the login
form and its full wire format are reachable unauthenticated.

## Platform

| | |
|---|---|
| Framework | **Vaadin 7.7.13** (not Vaadin 6) |
| Widgetset | `kz.kbtu.officeregistrar.portlet.admin.widgetset.OfficeregistrarWidgetset` |
| Theme | `r5` |
| Heartbeat | 120 s |
| Views | `/StudentSchedule` → `ScheduleUI`, `/JournalView` → `JournalUI` |

## Gotchas that will cost you a day each

**Incomplete TLS chain.** The server sends only the leaf `CN=*.kbtu.kz` and omits
the `Sectigo Public Server Authentication CA DV R36` intermediate
(`openssl s_client` → `Verify return code: 21`). macOS `curl` hides this by
fetching the intermediate over AIA; **OpenSSL, Node and undici do not**. Any
proxy must ship the intermediate. Rebuild the bundle with
`tools/fetch_intermediate.sh`.

**Sticky sessions.** Two cookies matter: `JSESSIONID` *and* `route`. WSP is
load-balanced (sessions land on e.g. `node9`) and the session exists on exactly
one node. Drop `route` and you get mystery session expiry.

**No CORS whatsoever.** No `Access-Control-Allow-*` on any response, so browser
JavaScript cannot call WSP directly. A relay is mandatory for a web app.

**Heartbeat or death.** `POST /<View>/HEARTBEAT/?v-uiId=<id>` every 120 s.

## The four requests

### 1. Bootstrap
`GET /StudentSchedule` → HTML containing
`vaadin.initApplication("StudentSchedule-1022739922", {...})`. Parse out the
appId and config.

### 2. Browser-details handshake
`POST /StudentSchedule/?v-<epoch_ms>`, form-encoded, with `v-browserDetails=1`,
`theme`, `v-appId`, viewport/timezone fields, `v-loc`, `v-wn`. Returns

```json
{"v-uiId":0,"uidl":"{\"Vaadin-Security-Key\":\"<csrf>\", \"state\":…, \"hierarchy\":…, \"types\":…}"}
```

Keep `Vaadin-Security-Key` — it is the CSRF token for every later call.

### 3. RPC
`POST /StudentSchedule/UIDL/?v-uiId=0`, `Content-Type: application/json`:

```json
{"csrfToken":"<key>","rpc":[ <invocation>, … ],"syncId":<n>,"clientId":<n>}
```

Responses are prefixed `for(;;);` (anti-JSON-hijacking) — strip it before
parsing. Apply `state` / `hierarchy` / `types` deltas onto a local mirror.
`"syncId": -1` plus `meta.appError` means the server threw.

### 4. Heartbeat
`POST /<View>/HEARTBEAT/?v-uiId=<id>`.

## Invocation formats

An invocation is `[connectorId, interfaceName, methodName, params]`.

**Typed RPC** — params is an array of encoded arguments:

```json
["17","com.vaadin.shared.ui.button.ButtonServerRpc","click",[{ …MouseEventDetails… }]]
```

`MouseEventDetails` is **bean-serialized as a JSON object**, not the
comma-joined string that `MouseEventDetails.serialize()` produces. Passing the
string form yields a server-side 500. `null` also works.

```json
{"button":"LEFT","clientX":120,"clientY":240,"altKey":false,"ctrlKey":false,
 "metaKey":false,"shiftKey":false,"type":1,"relativeX":12,"relativeY":10}
```

**Legacy variable change** — interface and method are both `"v"`, and params is
a **2-element array** `[variableName, UidlValue]`:

```json
["15","v","v",["text",["s","secret"]]]
```

Decompiled from the widgetset, which settles the shape:

```js
function Ene(a,b,c){ quc.call(this, a, 'v', 'v', [b, new Pne(c)]); … }
//                    MethodInvocation(connectorId, 'v', 'v', [varName, UidlValue(value)])
```

A `UidlValue` is `[typeTag, value]`: `s` string, `i` int, `d` double,
`b` boolean, `a` array, `n` null. Passing a bare value, or a `{name: value}`
map, produces a 500.

## Login

The login form does **not** exist in the initial tree — `pid 11` comes back an
empty `VerticalLayout`. It is rendered only after the client reports a device
id. The `LocalStorage` addon (`pid 18`) reads `secretBrowserUuid` from
`localStorage`, generating a UUID if absent, and sends:

```json
["18","com.r5.core.web.addon.client.localstorage.LocalStorageServerRpc","updateUuid",["<uuid>"]]
```

Decompiled source of that connector:

```js
_.yi = function Y0b(){
  var a = window.localStorage.getItem('secretBrowserUuid');
  if (a == null || !a.length || a=='null' || a=='undefined') {
      a = generateUUID(); window.localStorage.setItem('secretBrowserUuid', a);
  }
  vVc(this.a, a);            // -> LocalStorageServerRpc.updateUuid
}
```

Persist one UUID per install and reuse it, exactly as a browser would.

The form then appears:

```
[12] Panel → [13] FormLayout
      [14] ComboBox      'Username'     ← note: a ComboBox, not a TextField
      [15] PasswordField 'Password'
      [16] CheckBox      'Remember me'
      [17] Button        'Log in'
```

Username is a **ComboBox** (it remembers previous logins), which is why
DOM-scraping this form was so brittle. Send a typed username as `newitem`:

```json
[["14","v","v",["newitem",["s","<user>"]]],
 ["15","v","v",["text",   ["s","<pass>"]]],
 ["17","com.vaadin.shared.ui.button.ButtonServerRpc","click",[{…}]]]
```

Language can be switched first via the header flag buttons —
`pid 6` = Kazakh, `7` = Russian, `8` = English. Doing so makes every later
caption English, which is far easier to parse than mixed KZ/RU.

**Failure** renders a modal `Window` with style `global-error` containing a
`Label`, e.g. `"Invalid login or password"`. That is the signal to detect; there
is no HTTP status change.

## Resolving components

Never hardcode a pid. They are assigned per session and shift as the UI grows.
Resolve by Java class from `types` + `typeMappings`, disambiguating on
`caption` — that is what `VaadinSession.find_by_caption()` does.
