#!/usr/bin/env python3
"""HarnessKit conflict check.

Finds functional conflicts between installed skills/plugins and candidates
BEFORE they are installed or wired into a harness.

Deterministic layer (this script):
  - catalog conflicts recorded with source quotes
  - slot contention (output style, process owner, harness builder, session bootstrap)
  - role duplication (two memory systems, two HWP tools, ...)
  - duplicate skill names
  - heavy always-on cost (session-start injection, prompt hooks)
  - policy notes (external data, excluded tools)
Review layer (the calling agent): description pairs that overlap a lot are
returned with file paths so the agent can read the texts and judge them
against references/conflict-rules.md.

Usage:
  hkcheck.py [--env ENV.json | --project DIR] [--candidate CATALOG_ID ...]
             [--candidate-scan REPO.json ...] [--md] [--out FILE]
"""
import argparse
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hkcatalog  # noqa: E402
import hkscan  # noqa: E402

DEFAULT_CATALOG = os.path.join(HERE, "..", "references", "catalog.json")
SEVERITY_ORDER = {"high": 0, "medium": 1, "review": 2, "low": 3, "info": 4}
EXCLUSIVE_SLOTS = {"output-style", "process", "harness-builder"}
# Intent vocabulary for the review layer. Two skills from different sources
# that claim the same intent may fire on the same request.
INTENTS = {
    "code-write": r"\bimplement\w*|writing code|write code|\brefactor\w*|\bfeature\w*|bugfix|building components|adding functionality|코드 작성|구현|리팩터",
    "code-review": r"\breview\w*|코드 리뷰|코드 검토",
    "test": r"\btests?\b|\btesting\b|\btdd\b|테스트",
    "debug": r"\bdebug\w*|\bbugs?\b|test failure|unexpected behavior|디버그|버그|오류 원인",
    "plan": r"\bplan\w*|brainstorm\w*|\bdesign\b|\bspec\b|계획|설계",
    "verify": r"verification-before|before claiming|claiming (?:work|that)|완료 전 검증",
    "office-docs": r"\bdocx\b|\bxlsx\b|\bpptx\b|\bpdf\b|\bword document|\bexcel\b|powerpoint|엑셀|워드|파워포인트",
    "hwp": r"\bhwpx?\b|한글 문서|아래아한글",
    "korean-writing": r"윤문|번역투|humaniz\w*|한글 텍스트|문체",
    "browser": r"\bbrowser\b|\bweb (?:page|app|ui)|playwright|브라우저",
    "memory": r"\bmemory\b|\bremember\b|\brecall\b|장기 기억|메모리",
    "answer-style": r"\bconcise\b|\bbrevity\b|\btl;?dr\b|bottom line|답변 형식|결론부터",
    "harness": r"\bharness\b|하네스|agent team|에이전트 팀",
    "skill-routing": r"\bskill invocation\b|find and use skills|starting any conversation",
}
INTENT_RE = {k: re.compile(v, re.I) for k, v in INTENTS.items()}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- components

def component_from_item(item, source, runtime="claude"):
    skills = [s for s in item.get("skills", []) if not s.get("disable_model_invocation")]
    if item.get("override") in ("off", "user-invocable-only"):
        skills = []
    return {
        "key": f"{source}:{item['id']}",
        "label": item.get("plugin_id") or item.get("name") or item["id"],
        "kind": item.get("kind"),
        "source": source,
        "runtime": item.get("runtime", runtime),
        "plugin_name": item.get("name") if item.get("kind") == "plugin" else None,
        "skills": skills,
        "agents": item.get("agents", []),
        "hooks": item.get("hooks", []),
        "output_styles": item.get("output_styles", []),
        "mcp": item.get("mcp", []) + ([item["name"]] if item.get("kind") == "mcp" else []),
        "catalog_ids": [],
    }


def match_catalog(comp, catalog):
    names = {
        "plugins": {comp["plugin_name"].lower()} if comp["plugin_name"] else set(),
        "skills": {s["name"].lower() for s in comp["skills"]},
        "mcp": {m.lower() for m in comp["mcp"]},
        "output_styles": {s["name"].lower() for s in comp["output_styles"]},
    }
    hits = []
    for e in catalog["entries"]:
        det = e.get("detect") or {}
        if names["plugins"] & {x.lower() for x in det.get("plugins", [])}:
            hits.append(e["id"])
        elif comp["kind"] != "plugin" and (
                names["skills"] & {x.lower() for x in det.get("skills", [])}
                or names["mcp"] & {x.lower() for x in det.get("mcp", [])}
                or names["output_styles"] & {x.lower() for x in det.get("output_styles", [])}):
            hits.append(e["id"])
    return hits


def build_components(env, candidates, cand_scans, catalog):
    comps = []
    for item in env["claude"]["items"]:
        if item.get("enabled") is False:
            continue
        comps.append(component_from_item(item, "installed"))
    for item in env.get("codex", {}).get("items", []):
        comps.append(component_from_item(item, "installed", "codex"))
    for scan in cand_scans:
        for item in scan["items"]:
            comps.append(component_from_item(item, "candidate"))
    by_id = {e["id"]: e for e in catalog["entries"]}
    for c in comps:
        c["catalog_ids"] = match_catalog(c, catalog)
    present_ids = {cid for c in comps for cid in c["catalog_ids"]}
    for cid in candidates:
        if cid not in by_id:
            raise SystemExit(f"unknown catalog id: {cid}")
        if cid in present_ids:
            continue
        comps.append({"key": f"candidate:catalog:{cid}", "label": by_id[cid]["name"], "kind": "catalog",
                      "source": "candidate", "runtime": "claude", "plugin_name": None, "skills": [],
                      "agents": [], "hooks": [], "output_styles": [], "mcp": [], "catalog_ids": [cid]})
    return comps


# ---------------------------------------------------------------- checks

def intents(text):
    return {k for k, rx in INTENT_RE.items() if rx.search(text or "")}


def finding(ftype, severity, items, detail, resolve, evidence=None, source="rule"):
    return {"type": ftype, "severity": severity, "items": items, "detail": detail,
            "resolve": resolve, "evidence": evidence or [], "source": source}


def check(env, comps, catalog, max_review=8):
    by_id = {e["id"]: e for e in catalog["entries"]}
    out = []
    present = {}
    for c in comps:
        for cid in c["catalog_ids"]:
            present.setdefault(cid, []).append(c)

    def label(cid):
        srcs = sorted({c["source"] for c in present.get(cid, [])})
        return f"{cid} ({'/'.join(srcs)})"

    # 1. catalog conflicts with recorded evidence
    seen = set()
    for cid in present:
        for cf in by_id[cid].get("conflicts", []):
            other = cf["with"]
            pair = tuple(sorted((cid, other)))
            if other in present and pair not in seen:
                seen.add(pair)
                sev = "high" if cf["type"] in ("contradiction", "trigger", "slot") else "medium"
                detail, resolve = cf["detail"], cf["resolve"]
                if detail.endswith("항목 참고."):
                    back = next((x for x in by_id[other].get("conflicts", []) if x["with"] == cid), None)
                    if back:
                        detail, resolve = back["detail"], back["resolve"]
                out.append(finding(cf["type"], sev, [label(cid), label(other)], detail, resolve, source="catalog"))
            elif other not in by_id and (cid, other) not in seen:
                seen.add((cid, other))
                out.append(finding(cf["type"], "low", [label(cid)], cf["detail"], cf["resolve"], source="catalog"))

    # 2. slot contention and role duplication from catalog metadata
    for key, field in (("slot", "slot"), ("role", "role")):
        groups = {}
        for cid in present:
            v = by_id[cid].get(field)
            if v:
                groups.setdefault(v, set()).add(cid)
        for v, ids in groups.items():
            if len(ids) < 2:
                continue
            pairs_done = any(tuple(sorted(p)) in seen for p in itertools.combinations(ids, 2))
            if pairs_done and len(ids) == 2:
                continue
            if field == "slot":
                sev = "high" if v in EXCLUSIVE_SLOTS else "medium"
                out.append(finding("slot", sev, [label(i) for i in sorted(ids)],
                                   f"'{v}' 자리를 여러 도구가 차지한다.",
                                   "자리마다 하나만 남기거나, 어느 쪽이 이기는지 우선순위 한 줄을 적는다."))
            else:
                out.append(finding("role", "medium", [label(i) for i in sorted(ids)],
                                   f"같은 일('{v}')을 하는 도구가 여럿이다.",
                                   "프로젝트에 맞는 하나를 남기고 나머지는 끈다."))

    # 3. output style slot from the scan itself
    active = env["claude"]["settings"].get("outputStyle")
    styled = [c for c in comps if c["output_styles"] and c["source"] == "candidate"]
    if active and styled:
        out.append(finding("slot", "medium", [active + " (active)"] + [c["label"] for c in styled],
                           "이미 출력 스타일이 선택돼 있는데 후보가 다른 출력 스타일을 가져온다. 하나만 선택할 수 있다.",
                           "어떤 스타일을 쓸지 정한다."))

    # 4. session bootstrap injections
    boots = []
    for c in comps:
        for h in c["hooks"]:
            est = h.get("injects_estimate") or {}
            if h.get("event") == "SessionStart" and est.get("chars", 0) > 0:
                boots.append((c, est))
    if len(boots) > 1:
        out.append(finding("slot", "medium", [c["label"] for c, _ in boots],
                           "세션을 시작할 때마다 지침을 주입하는 SessionStart 훅이 둘 이상이다. 규칙이 쌓이고 서로 어긋날 수 있다.",
                           "주입되는 파일(근거)을 읽고 시작 지침은 하나만 남긴다.",
                           [p for _, e in boots for p in e.get("files", [])]))

    # 5. duplicate skill names across components
    names = {}
    for c in comps:
        for s in c["skills"]:
            names.setdefault((c["runtime"], s["name"].lower()), []).append((c, s))
    for (_, n), hits in names.items():
        owners = {c["key"] for c, _ in hits}
        if len(owners) > 1:
            out.append(finding("trigger", "high", [c["label"] for c, _ in hits],
                               f"'{n}' 스킬이 두 군데 이상 있어 같은 요청을 두고 경쟁한다.",
                               "하나만 남긴다.", [s["path"] for _, s in hits]))

    # 6. heavy always-on cost
    for c in comps:
        for h in c["hooks"]:
            est = h.get("injects_estimate") or {}
            if est.get("chars", 0) >= 1500:
                out.append(finding("cost", "low", [c["label"]],
                                   f"{h['event']} 훅이 실행될 때마다 약 {est['chars']}자(추정 {est.get('tokens')}토큰)를 주입한다 (matcher: {h.get('matcher') or '전체'}).",
                                   "그 절차가 필요한 프로젝트에서만 켠다.", est.get("files", [])))
            if h.get("type") == "prompt":
                out.append(finding("cost", "medium", [c["label"]],
                                   f"prompt 유형 {h['event']} 훅이 실행될 때마다 LLM 판정이 돈다.",
                                   "필요한 세션에서만 켠다."))
        if len(c["agents"]) >= 6:
            out.append(finding("cost", "low", [c["label"]],
                               f"서브에이전트 설명문 {len(c['agents'])}개가 매 세션 목록에 올라간다.",
                               "그 에이전트들을 쓴다면 괜찮다. 쓰지 않는 프로젝트에서는 플러그인을 끄는 것을 검토한다."))

    # 7. policy notes
    for cid, cs in present.items():
        e = by_id[cid]
        if e.get("layer") == "excluded":
            out.append(finding("policy", "medium", [label(cid)],
                               f"카탈로그 제외 도구: {' '.join(e.get('skip_when', [])) or e.get('always_on', '')}",
                               "제거하거나, 남긴다면 이유를 harnesskit.lock에 적는다."))
        ext = e.get("external_data", "")
        if ext and not ext.startswith(("없음", "확인된 것 없음")):
            out.append(finding("policy", "info", [label(cid)], f"외부 전송: {ext}",
                               "회사 정책상 허용되는지 확인한다."))

    # 8. review layer: skills from different sources that claim the same intent
    pool = []
    for c in comps:
        for s in c["skills"]:
            pool.append((c, s, intents(s["name"] + " " + s["description"])))
    scored = []
    for (c1, s1, i1), (c2, s2, i2) in itertools.combinations(pool, 2):
        # Skills only compete inside one runtime; same-name pairs are reported above.
        if c1["key"] == c2["key"] or c1["runtime"] != c2["runtime"] or s1["name"].lower() == s2["name"].lower():
            continue
        pair = tuple(sorted((c1["catalog_ids"][:1] or [c1["key"]])[0:1] + (c2["catalog_ids"][:1] or [c2["key"]])[0:1]))
        if pair in seen:
            continue
        common = i1 & i2
        if common:
            scored.append((len(common), c1, s1, c2, s2, common))
    scored.sort(key=lambda x: -x[0])
    for _, c1, s1, c2, s2, common in scored[:max_review]:
        out.append(finding("trigger?", "review", [f"{c1['label']}:{s1['name']}", f"{c2['label']}:{s2['name']}"],
                           f"둘 다 같은 의도({', '.join(sorted(common))})를 주장한다. 트리거 겹침이나 역할 중복일 수 있다.",
                           "두 SKILL.md를 읽고 conflict-rules.md 기준으로 판정한다.",
                           [s1["path"], s2["path"]], source="heuristic"))
    if len(scored) > max_review:
        out.append(finding("trigger?", "info", [f"그 외 {len(scored) - max_review}쌍"],
                           "표시한 것보다 의도가 겹치는 쌍이 더 있다.", "필요하면 후보를 좁혀 다시 실행한다."))

    out.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    return out


# ---------------------------------------------------------------- output

def to_markdown(comps, findings):
    lines = ["| # | 심각도 | 유형 | 대상 | 내용 | 해결안 |", "|---|---|---|---|---|---|"]
    for i, f in enumerate(findings, 1):
        detail = f["detail"].replace("|", "\\|")
        lines.append(f"| {i} | {f['severity']} | {f['type']} | {'<br>'.join(f['items'])} | {detail} | {f['resolve']} |")
    head = (f"검사 대상: 설치됨 {sum(1 for c in comps if c['source'] == 'installed')}개, "
            f"후보 {sum(1 for c in comps if c['source'] == 'candidate')}개 · 발견 {len(findings)}건")
    return head + "\n\n" + "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", help="output of `hkscan.py env`")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--candidate", action="append", default=[], help="catalog id to check before installing")
    ap.add_argument("--candidate-scan", action="append", default=[], help="output of `hkscan.py repo`")
    ap.add_argument("--catalog", default=DEFAULT_CATALOG)
    ap.add_argument("--md", action="store_true", help="print a markdown table instead of JSON")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    env = load_json(a.env) if a.env else hkscan.scan_env(a.project)
    # The default merges the personal catalog (hkcatalog.py add) with the kit catalog.
    catalog = hkcatalog.load_catalog() if os.path.abspath(a.catalog) == os.path.abspath(DEFAULT_CATALOG) else load_json(a.catalog)
    scans = [load_json(p) for p in a.candidate_scan]
    comps = build_components(env, a.candidate, scans, catalog)
    findings = check(env, comps, catalog)
    if a.md:
        text = to_markdown(comps, findings)
    else:
        text = json.dumps({
            "components": [{"label": c["label"], "source": c["source"], "runtime": c["runtime"],
                            "catalog_ids": c["catalog_ids"]} for c in comps],
            "findings": findings,
            "summary": {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER},
        }, ensure_ascii=False, indent=1)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(a.out)
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
