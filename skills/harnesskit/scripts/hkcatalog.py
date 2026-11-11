#!/usr/bin/env python3
"""Query the HarnessKit catalog, and keep a personal catalog of skills to try later.

  hkcatalog.py find [--role R ...] [--cap C ...] [--category C] [--text WORDS] [--layer L ...] [--mine]
  hkcatalog.py show ID [ID ...]
  hkcatalog.py roles
  hkcatalog.py add --file ENTRY.json      save one entry to the personal catalog
  hkcatalog.py remove ID                  remove an entry from the personal catalog
  hkcatalog.py mine                       list the personal catalog
  hkcatalog.py path                       print where the personal catalog lives

The kit catalog ships inside the skill and is replaced on update. The personal
catalog lives outside it (~/.harnesskit/catalog.local.json)
so saved entries survive updates. Both are merged for find/show/roles and for
hkcheck.py. Standard library only.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "catalog.json")
REQUIRED = ("id", "name", "repo", "license", "layer", "use_when", "skip_when", "install",
            "detect", "always_on", "external_data", "conflicts", "verified")
LAYERS = ("kit", "always-on", "task", "tool", "optional", "excluded")


def user_catalog_path():
    return os.path.join(os.path.expanduser("~"), ".harnesskit", "catalog.local.json")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_catalog():
    """Kit catalog plus the personal catalog, with each entry's origin marked."""
    cat = _read(CATALOG)
    for e in cat["entries"]:
        e.setdefault("origin", "kit")
    mine = _read(user_catalog_path()) or {"entries": []}
    ids = {e["id"] for e in cat["entries"]}
    for e in mine.get("entries", []):
        if e.get("id") not in ids:
            cat["entries"].append(dict(e, origin="mine"))
    return cat


def load():
    return load_catalog()["entries"]


def norm_repo(url):
    url = (url or "").strip().lower()
    url = re.sub(r"\s.*$", "", url)  # drop trailing notes like "(skills/x)"
    url = re.sub(r"^https?://(www\.)?", "", url)
    url = url.rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def validate(entry, types):
    problems = [f"필드 없음: {k}" for k in REQUIRED if k not in entry]
    if entry.get("layer") not in LAYERS:
        problems.append(f"layer는 {'/'.join(LAYERS)} 중 하나")
    if entry.get("verified") not in ("direct", "survey"):
        problems.append("verified는 direct 또는 survey")
    for c in entry.get("conflicts", []):
        if c.get("type") not in types:
            problems.append(f"충돌 유형이 잘못됨: {c.get('type')}")
        for k in ("with", "detail", "resolve"):
            if k not in c:
                problems.append(f"충돌 항목에 {k} 없음")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", entry.get("id", "")):
        problems.append("id는 영문 소문자·숫자·-·_·. 만")
    return problems


def add(path):
    with open(path, encoding="utf-8") as f:
        entry = json.load(f)
    kit = _read(CATALOG)
    problems = validate(entry, kit["conflict_types"])
    if problems:
        sys.exit("저장하지 않음:\n- " + "\n- ".join(problems))
    upath = user_catalog_path()
    mine = _read(upath) or {"about": "HarnessKit 개인 카탈로그. 나중에 써 볼 스킬을 보관한다.", "entries": []}
    for e in kit["entries"]:
        if e["id"] == entry["id"] or norm_repo(e.get("repo")) == norm_repo(entry.get("repo")):
            sys.exit(f"이미 키트 카탈로그에 있음: {e['id']} ({e.get('repo')})")
    replaced = [e for e in mine["entries"] if e["id"] == entry["id"] or norm_repo(e.get("repo")) == norm_repo(entry.get("repo"))]
    mine["entries"] = [e for e in mine["entries"] if e not in replaced]
    entry.setdefault("saved_at", dt.date.today().isoformat())
    entry.pop("origin", None)
    mine["entries"].append(entry)
    os.makedirs(os.path.dirname(upath), exist_ok=True)
    tmp = upath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mine, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, upath)
    print(json.dumps({"saved": entry["id"], "updated": bool(replaced), "path": upath,
                      "total_mine": len(mine["entries"])}, ensure_ascii=False))


def remove(entry_id):
    upath = user_catalog_path()
    mine = _read(upath) or {"entries": []}
    before = len(mine["entries"])
    mine["entries"] = [e for e in mine["entries"] if e["id"] != entry_id]
    if len(mine["entries"]) == before:
        sys.exit(f"개인 카탈로그에 없음: {entry_id}")
    with open(upath, "w", encoding="utf-8") as f:
        json.dump(mine, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"removed": entry_id, "total_mine": len(mine["entries"])}, ensure_ascii=False))


def short(e):
    first = lambda xs: (xs or [""])[0]
    ext = e.get("external_data", "")
    out = {
        "id": e["id"], "name": e.get("name"), "origin": e.get("origin", "kit"), "layer": e.get("layer"),
        "slot_or_role": e.get("slot") or e.get("role"),
        "use_when": first(e.get("use_when")), "skip_when": first(e.get("skip_when")),
        "external": "" if ext.startswith(("없음", "확인된 것 없음")) else ext[:80],
        "verified": e.get("verified"),
        "conflicts_with": [c["with"] for c in e.get("conflicts", [])],
    }
    if e.get("security"):
        out["security"] = e["security"][:120]
    if e.get("memo"):
        out["memo"] = e["memo"]
    return out


def matches(e, roles, caps, words, layers, category=None, mine_only=False):
    if mine_only and e.get("origin") != "mine":
        return False
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
    f.add_argument("--mine", action="store_true", help="only the personal catalog")
    s = sub.add_parser("show")
    s.add_argument("ids", nargs="+")
    sub.add_parser("roles")
    ad = sub.add_parser("add")
    ad.add_argument("--file", required=True)
    rm = sub.add_parser("remove")
    rm.add_argument("id")
    sub.add_parser("mine")
    sub.add_parser("path")
    a = ap.parse_args(argv)

    if a.cmd == "add":
        return add(a.file)
    if a.cmd == "remove":
        return remove(a.id)
    if a.cmd == "path":
        return print(user_catalog_path())

    entries = load()
    # A conflict recorded on one side applies to both; show it from either entry.
    reverse = {}
    for e in entries:
        for c in e.get("conflicts", []):
            reverse.setdefault(c["with"], set()).add(e["id"])
    if a.cmd in ("find", "mine"):
        mine_only = a.cmd == "mine" or a.mine
        args = (a.role, a.cap, a.text.split(), a.layer, a.category) if a.cmd == "find" else ([], [], [], [], None)
        hits = []
        for e in entries:
            if matches(e, *args, mine_only=mine_only):
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
            roles.setdefault(k, []).append(e["id"] + (" (내 카탈로그)" if e.get("origin") == "mine" else ""))
        for k in sorted(roles):
            print(f"{k}: {', '.join(roles[k])}")


if __name__ == "__main__":
    main()
