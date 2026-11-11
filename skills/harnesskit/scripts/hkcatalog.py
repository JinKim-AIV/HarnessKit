#!/usr/bin/env python3
"""Query the HarnessKit catalog without loading the whole file into context.

  hkcatalog.py find [--role R ...] [--cap C ...] [--category C] [--text WORDS] [--layer L ...]
  hkcatalog.py show ID [ID ...]
  hkcatalog.py roles

find prints one short line per matching entry. show prints full entries.
Standard library only.
"""
import argparse
import json
import os
import sys

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "catalog.json")


def load():
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)["entries"]


def short(e):
    first = lambda xs: (xs or [""])[0]
    ext = e.get("external_data", "")
    return {
        "id": e["id"], "name": e.get("name"), "layer": e.get("layer"),
        "slot_or_role": e.get("slot") or e.get("role"),
        "use_when": first(e.get("use_when")), "skip_when": first(e.get("skip_when")),
        "external": "" if ext.startswith(("없음", "확인된 것 없음")) else ext[:80],
        "verified": e.get("verified"),
        "conflicts_with": [c["with"] for c in e.get("conflicts", [])],
    }


def matches(e, roles, caps, words, layers, category=None):
    if category and e.get("category") != category:
        return False
    if roles and (e.get("role") or e.get("slot")) not in roles:
        return False
    if caps and not set(caps) & set(e.get("capabilities", [])):
        return False
    if layers and e.get("layer") not in layers:
        return False
    if words:
        hay = json.dumps(e, ensure_ascii=False).lower()
        return all(w.lower() in hay for w in words)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("--role", action="append", default=[])
    f.add_argument("--cap", action="append", default=[])
    f.add_argument("--layer", action="append", default=[])
    f.add_argument("--text", default="")
    f.add_argument("--category")
    s = sub.add_parser("show")
    s.add_argument("ids", nargs="+")
    sub.add_parser("roles")
    a = ap.parse_args(argv)
    entries = load()
    # A conflict recorded on one side applies to both; show it from either entry.
    reverse = {}
    for e in entries:
        for c in e.get("conflicts", []):
            reverse.setdefault(c["with"], set()).add(e["id"])
    if a.cmd == "find":
        hits = []
        for e in entries:
            if matches(e, a.role, a.cap, a.text.split(), a.layer, a.category):
                h = short(e)
                h["conflicts_with"] = sorted(set(h["conflicts_with"]) | reverse.get(e["id"], set()))
                hits.append(h)
        for h in hits:
            print(json.dumps(h, ensure_ascii=False))
        if not hits:
            print("{}")
    elif a.cmd == "show":
        by_id = {e["id"]: e for e in entries}
        missing = [i for i in a.ids if i not in by_id]
        print(json.dumps([by_id[i] for i in a.ids if i in by_id], ensure_ascii=False, indent=1))
        if missing:
            sys.exit("not in catalog: " + ", ".join(missing))
    else:
        roles = {}
        for e in entries:
            k = e.get("slot") or e.get("role") or "-"
            roles.setdefault(k, []).append(e["id"])
        for k in sorted(roles):
            print(f"{k}: {', '.join(roles[k])}")


if __name__ == "__main__":
    main()
