"""Parse Vaadin legacy Table UIDL into rows, and derive the summary."""
import json
import re

# Legacy UIDL is nested tagged arrays: [tag, attrs, ...children]
def _walk(node):
    yield node
    if isinstance(node, list):
        for c in node:
            yield from _walk(c)

def _tagged(node, tag):
    """Find [tag, {...}, ...] nodes anywhere in the tree."""
    for n in _walk(node):
        if isinstance(n, list) and n and n[0] == tag:
            yield n

def parse_table(changes, pid=None):
    """Extract columns + rows for a Table connector from a `changes` payload."""
    for change in changes:
        if not (isinstance(change, list) and len(change) >= 3 and change[0] == "change"):
            continue
        if pid is not None and str(change[1].get("pid")) != str(pid):
            continue
        body = change[2]
        if not (isinstance(body, list) and len(body) >= 2 and isinstance(body[1], dict)):
            continue
        attrs = body[1]
        if "cols" not in attrs and "totalrows" not in attrs:
            continue

        cols = [c[1].get("caption", "") for c in _tagged(body, "column")]
        rows = []
        for tr in _tagged(body, "tr"):
            cells = [c for c in tr[2:] if not isinstance(c, (list, dict))]
            rows.append({
                "key": str(tr[1].get("key", "")),
                "cells": [("" if c is None else str(c)) for c in cells],
            })
        return {
            "columns": cols,
            "rows": rows,
            "totalrows": attrs.get("totalrows", len(rows)),
            "firstrow": attrs.get("firstrow", 0),
        }
    return None


def parse_subject(raw):
    """"STAT2201 Statistics (STAT2201) (Fall)" -> code STAT2201, name "Statistics".

    Everything from the first "(" is dropped (the repeated code and the term),
    and the leading token is the course code. Note this also drops level markers
    like "(А1)", so LAN1175 reads "General Kazakh language 1" here while the
    schedule keeps the marker — match courses by code, not name.
    """
    head = raw.split("(")[0]
    parts = head.split()
    return {
        "code": parts[0] if parts else "",
        "name": " ".join(parts[1:]).strip() or (parts[0] if parts else raw.strip()),
        "raw": raw,
    }


ATTENDED = {"present", "присутствовал", "присутствовала", "қатысты"}
ABSENT = {"absent", "отсутствовал", "отсутствовала", "қатыспады"}

def to_records(table):
    """Columns -> named fields, tolerant of column reordering."""
    if not table:
        return []
    idx = {c.strip().lower(): i for i, c in enumerate(table["columns"])}
    def get(cells, *names):
        for n in names:
            i = idx.get(n)
            if i is not None and i < len(cells):
                return cells[i].strip()
        return ""
    out = []
    for r in table["rows"]:
        c = r["cells"]
        raw_att = get(c, "attendance", "присутствие")
        raw_score = get(c, "score", "оценка", "grade")
        score = None
        if raw_score:
            m = re.search(r"-?\d+(?:[.,]\d+)?", raw_score)
            if m:
                score = float(m.group().replace(",", "."))
        out.append({
            "date": get(c, "date", "дата"),
            "lesson": get(c, "lesson", "урок"),
            "attendance": raw_att,
            "present": (raw_att.lower() in ATTENDED) if raw_att else None,
            "score": score,
            "comment": get(c, "comment", "комментарий"),
        })
    return out


def summarise(records):
    """What the Итог / Show Total button would tell you — computed locally, so
    it needs no extra round-trip and works offline."""
    known = [r for r in records if r["present"] is not None]
    attended = [r for r in known if r["present"]]
    scored = [r for r in records if r["score"] is not None]
    graded = [r for r in scored if r["score"] > 0]
    return {
        "classes": len(records),
        "attended": len(attended),
        "absent": len(known) - len(attended),
        "attendance_pct": round(100 * len(attended) / len(known), 1) if known else None,
        "average": round(sum(r["score"] for r in graded) / len(graded), 2) if graded else None,
        "graded": len(graded),
    }


if __name__ == "__main__":
    d = json.load(open("tools/dump_journal_table.json", encoding="utf-8"))
    print(f"subject: {d['selected']['caption']}")
    print(f"defaults: {d['defaults']}\n")
    for stage in ("after_select", "after_rows", "after_total"):
        t = parse_table(d.get(stage, []), pid="60")
        if not t:
            print(f"{stage:14s} -> no table")
            continue
        recs = to_records(t)
        print(f"{stage:14s} -> cols={t['columns']} totalrows={t['totalrows']}")
        for r in recs:
            print(f"                 {r['date']}  {r['lesson']:<6} {r['attendance']:<10} "
                  f"score={r['score']}  {r['comment']!r}")
        print(f"                 summary: {summarise(recs)}")
