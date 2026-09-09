"""Turn the WSP connector tree into structured schedule JSON."""
import json
import re

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# "CSCI2104 Databases Saimassayeva S. Л 450 (08:00-09:00)"
# Course names may contain parens — "General Kazakh language 1 (А1)" — and so may
# rooms — "Игровой зал Баскетбол ДМиС (юн)". Anchoring on the trailing time span
# and the "Surname I." instructor pattern is what keeps those from swallowing
# each other; both name and room stay non-greedy.
LESSON_RE = re.compile(
    r"^(?P<code>\S+)\s+"
    r"(?P<name>.*?)\s+"
    r"(?P<instructor>\S+\s+[A-ZА-ЯЁ]\.)\s+"
    r"(?P<type>[ЛПлп])\s+"
    r"(?P<room>.*?)\s*"
    r"\((?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})\)\s*$"
)
KIND = {"Л": "lecture", "П": "practice"}


class Tree:
    def __init__(self, dump):
        self.state = dump["state"]
        self.types = dump["types"]
        self.hier = dump["hierarchy"]
        self.names = dump["type_names"]

    def cls(self, pid):
        return self.names.get(str(self.types.get(str(pid))), "?")

    def kids(self, pid):
        return self.hier.get(str(pid), [])

    def descendants(self, pid):
        out, stack = [], [str(pid)]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(self.kids(cur))
        return out

    def find(self, suffix):
        return [p for p in self.types if self.cls(p).endswith(suffix)]

    def text(self, pid):
        return self.state.get(str(pid), {}).get("text")

    def styles(self, pid):
        return self.state.get(str(pid), {}).get("styles") or []


def parse_lesson(raw):
    m = LESSON_RE.match(raw.strip())
    if not m:
        return {"raw": raw, "unparsed": True}
    g = m.groupdict()
    return {
        "code": g["code"],
        "name": re.sub(r"\s{2,}", " ", g["name"]).strip(),
        "instructor": re.sub(r"\s{2,}", " ", g["instructor"]).strip(),
        "kind": KIND.get(g["type"].upper(), "other"),
        "room": re.sub(r"\s{2,}", " ", g["room"]).strip(),
        "start": g["start"].rjust(5, "0"),
        "end": g["end"].rjust(5, "0"),
    }


def merge_runs(lessons):
    """WSP emits one 40px block per hour. Collapse consecutive blocks of the same
    class into a single lesson so a 3-hour lab reads as one card, not three."""
    out = []
    for les in sorted(lessons, key=lambda x: x.get("start", "")):
        prev = out[-1] if out else None
        same = (prev and not prev.get("unparsed") and not les.get("unparsed")
                and prev["code"] == les["code"] and prev["room"] == les["room"]
                and prev["kind"] == les["kind"] and prev["instructor"] == les["instructor"]
                and prev["end"] == les["start"])
        if same:
            prev["end"] = les["end"]
        else:
            out.append(dict(les))
    return out


FULL_TO_SHORT = {
    "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu",
    "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun",
    "Понедельник": "Mon", "Вторник": "Tue", "Среда": "Wed", "Четверг": "Thu",
    "Пятница": "Fri", "Суббота": "Sat", "Воскресенье": "Sun",
}
KIND_CHAR = {"Л": "lecture", "П": "practice", "L": "lecture", "P": "practice"}


def _day_key(text):
    t = (text or "").strip()
    return t if t in DAYS else FULL_TO_SHORT.get(t)


def parse_v2(dump):
    """Mobile layout (WSP, Sept 2026+). Served to small viewports; desktop
    viewports still get the v1 grid. Fields arrive pre-split, so no regex."""
    t = Tree(dump)
    roots = t.find("StudentScheduleMobileComponent")
    if not roots:
        return None
    root = roots[0]
    container = next((c for c in t.kids(root) if t.kids(c)), root)

    days = {d: [] for d in DAYS}
    current, seen = None, False
    for node in t.kids(container):
        cls = t.cls(node)
        if cls == "com.vaadin.ui.Label":
            d = _day_key(t.text(node))
            if d:
                current = d
            continue
        if cls != "com.vaadin.ui.HorizontalLayout" or not current:
            continue
        cols = [c for c in t.kids(node) if t.cls(c) == "com.vaadin.ui.VerticalLayout"]
        if len(cols) < 2:
            continue
        times = [(t.text(c) or "").strip() for c in t.kids(cols[0])]
        times = [x for x in times if x]
        info = [(t.text(c) or "").strip() for c in t.kids(cols[1])]
        info += [""] * (3 - len(info))
        title, meta, instructor = info[0], info[1], info[2]

        parts = title.split()
        kind_char, _, room = meta.partition("·")
        kc = (kind_char or "").strip()[:1].upper()
        days[current].append({
            "code": parts[0] if parts else "",
            "name": " ".join(parts[1:]).strip(),
            "instructor": re.sub(r"\s{2,}", " ", instructor).strip(),
            "kind": KIND_CHAR.get(kc, "other"),
            "room": re.sub(r"\s{2,}", " ", room).strip(),
            "start": times[0] if times else "",
            "end": times[1] if len(times) > 1 else (times[0] if times else ""),
        })
        seen = True
    return {d: merge_runs(v) for d, v in days.items()} if seen else None


def parse_v1(dump):
    """Desktop layout (the original). Kept as the fallback."""
    t = Tree(dump)
    holders = t.find("ScheduleComponent")
    holders = [p for p in holders if "api." in t.cls(p)] or holders
    if not holders:
        raise ValueError("no ScheduleComponent in tree")

    # Day columns: a VerticalLayout whose subtree has a bold Label naming the day.
    days = {d: [] for d in DAYS}
    root = holders[0]
    for col in t.descendants(root):
        if t.cls(col) != "com.vaadin.ui.VerticalLayout":
            continue
        header = next((t.text(d) for d in t.descendants(col)
                       if t.text(d) in DAYS and "bold" in t.styles(d)), None)
        if not header:
            continue
        for node in t.descendants(col):
            if "schedule-item" not in t.styles(node):
                continue
            for lbl in t.descendants(node):
                raw = t.text(lbl)
                if raw:
                    days[header].append(parse_lesson(raw))
    return {d: merge_runs(v) for d, v in days.items()}


def parse(dump):
    """Mobile first, desktop grid as fallback."""
    return parse_v2(dump) or parse_v1(dump)


def student_info(dump):
    t = Tree(dump)
    info = {}
    for comp in t.find("StudentInformationComponent"):
        vals = [t.text(d) for d in t.descendants(comp) if t.text(d)]
        info["fields"] = vals
    return info


if __name__ == "__main__":
    dump = json.load(open("tools/dump_schedule.json", encoding="utf-8"))
    sched = parse(dump)
    total = sum(len(v) for v in sched.values())
    bad = [l for v in sched.values() for l in v if l.get("unparsed")]
    print(f"parsed {total} lessons, {len(bad)} unparsed\n")
    for day in DAYS:
        if not sched[day]:
            continue
        print(day)
        for l in sched[day]:
            if l.get("unparsed"):
                print(f"   !! {l['raw']}")
            else:
                print(f"   {l['start']}-{l['end']}  {l['code']:<10} {l['kind']:<9} "
                      f"{l['room']:<34} {l['name']}")
        print()
    if bad:
        print("UNPARSED:", json.dumps(bad, ensure_ascii=False, indent=1))
