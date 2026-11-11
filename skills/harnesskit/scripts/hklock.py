#!/usr/bin/env python3
"""HarnessKit lock file: record, detect drift, and mirror a harness.

  hklock.py write  --project DIR --data DATA.json
      Create or update PROJECT/harnesskit.lock. DATA holds the decisions the
      agent made with the user: runtimes, tools (use/disabled/skipped with a
      reason), decisions (conflict resolutions), and harness (orchestrator,
      agents, skills). The script adds an environment snapshot and file hashes.

  hklock.py status --project DIR [--brief]
      Compare the project with its lock. Reports new or removed tools, harness
      files edited outside HarnessKit, and whether a review (evolve) is due.
      --brief prints at most one line and nothing when there is no signal,
      so an orchestrator can run it every time at almost no cost.

  hklock.py mirror --project DIR [--to codex|claude]
      Copy harness skills between .claude/skills and .agents/skills and
      convert agent definitions between .claude/agents/*.md and
      .codex/agents/*.toml, so one harness serves both runtimes.

Standard library only.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hkscan  # noqa: E402

VERSION = "0.1.0"
LOCK_NAME = "harnesskit.lock"
REVIEW_AFTER_DAYS = 14
REVIEW_AFTER_RUNS = 3


def now():
    return dt.datetime.now().replace(microsecond=0).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def harness_paths(project, harness):
    """Files that make up the harness, for both runtimes."""
    paths = []
    for a in harness.get("agents", []):
        paths += [os.path.join(".claude", "agents", a + ".md"), os.path.join(".codex", "agents", a + ".toml")]
    for s in harness.get("skills", []):
        for base in (os.path.join(".claude", "skills", s), os.path.join(".agents", "skills", s)):
            full = os.path.join(project, base)
            if os.path.isdir(full):
                for root, _, files in os.walk(full):
                    for f in files:
                        paths.append(os.path.relpath(os.path.join(root, f), project))
    return [p for p in sorted(set(paths)) if os.path.isfile(os.path.join(project, p))]


def env_snapshot(project):
    env = hkscan.scan_env(project)
    c = env["claude"]
    return {
        "claude_plugins": sorted(i["plugin_id"] for i in c["items"] if i["kind"] == "plugin" and i.get("enabled") is not False),
        "claude_skills": sorted(i["id"] for i in c["items"] if i["kind"] == "skill"),
        "claude_mcp": sorted(i["id"] for i in c["items"] if i["kind"] == "mcp"),
        "output_style": c["settings"].get("outputStyle"),
        "codex_skills": sorted(i["id"] for i in env["codex"]["items"] if i["kind"] == "skill"),
        "codex_mcp": sorted(i["id"] for i in env["codex"]["items"] if i["kind"] == "mcp"),
    }


def load_lock(project):
    p = os.path.join(project, LOCK_NAME)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cmd_write(project, data_path):
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    old = load_lock(project) or {}
    harness = data.get("harness") or old.get("harness") or {}
    lock = {
        "harnesskit": VERSION,
        "created": old.get("created") or now(),
        "updated": now(),
        "runtimes": data.get("runtimes") or old.get("runtimes") or ["claude"],
        "tools": data.get("tools", old.get("tools", [])),
        "decisions": old.get("decisions", []) + [dict(d, date=d.get("date") or now()[:10]) for d in data.get("decisions", [])],
        "harness": dict(harness, files={p: sha256(os.path.join(project, p)) for p in harness_paths(project, harness)}),
        "env_snapshot": env_snapshot(project),
        "evolve": old.get("evolve", {"last": None, "count": 0}),
    }
    if data.get("evolved"):
        lock["evolve"] = {"last": now(), "count": lock["evolve"].get("count", 0) + 1}
    with open(os.path.join(project, LOCK_NAME), "w", encoding="utf-8") as f:
        json.dump(lock, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(os.path.join(project, LOCK_NAME))


def workspace_runs_since(project, since_iso):
    """Count orchestrator runs (archived _workspace dirs) newer than the lock."""
    try:
        since = dt.datetime.fromisoformat(since_iso).timestamp()
    except (TypeError, ValueError):
        return 0
    n = 0
    for d in os.listdir(project):
        if d.startswith("_workspace") and os.path.isdir(os.path.join(project, d)):
            if os.path.getmtime(os.path.join(project, d)) > since:
                n += 1
    return n


def cmd_status(project, brief):
    lock = load_lock(project)
    if not lock:
        if not brief:
            print(json.dumps({"lock": False}))
        return
    snap_old, snap_new = lock.get("env_snapshot", {}), env_snapshot(project)
    env_changes = {}
    for k in snap_new:
        a, b = snap_old.get(k), snap_new[k]
        if isinstance(b, list):
            added, removed = sorted(set(b) - set(a or [])), sorted(set(a or []) - set(b))
            if added or removed:
                env_changes[k] = {"added": added, "removed": removed}
        elif a != b:
            env_changes[k] = {"from": a, "to": b}

    harness = lock.get("harness", {})
    recorded = harness.get("files", {})
    edited = [p for p, h in recorded.items() if os.path.isfile(os.path.join(project, p)) and sha256(os.path.join(project, p)) != h]
    missing = [p for p in recorded if not os.path.isfile(os.path.join(project, p))]
    current = set(harness_paths(project, harness))
    new_files = sorted(current - set(recorded))

    since = (lock.get("evolve") or {}).get("last") or lock.get("updated")
    try:
        age = (dt.datetime.now() - dt.datetime.fromisoformat(since)).days
    except (TypeError, ValueError):
        age = 0
    runs = workspace_runs_since(project, since)

    signals = []
    if env_changes:
        signals.append(("check", "설치 환경이 lock 이후 바뀌었습니다. 충돌 체크를 권장합니다."))
    if edited or missing or new_files:
        signals.append(("evolve", "하네스 파일이 HarnessKit 밖에서 바뀌었습니다. 회고(evolve)로 기록을 맞추길 권장합니다."))
    if age >= REVIEW_AFTER_DAYS and runs >= REVIEW_AFTER_RUNS:
        signals.append(("evolve", f"마지막 회고 후 {age}일, 실행 {runs}회가 지났습니다. 회고(evolve)를 권장합니다."))

    if brief:
        if signals:
            kinds = sorted({k for k, _ in signals})
            print(f"[HarnessKit] {signals[0][1]} (harnesskit {'/'.join(kinds)})")
        return
    print(json.dumps({
        "lock": True, "env_changes": env_changes,
        "harness_files": {"edited": edited, "missing": missing, "new": new_files},
        "days_since_review": age, "runs_since_review": runs,
        "signals": [{"suggest": k, "message": m} for k, m in signals],
    }, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- mirror

def toml_multiline(text):
    if "'''" not in text:
        return "'''\n" + text + "'''"
    esc = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""\n' + esc + '"""'


def toml_string(text):
    return json.dumps(text, ensure_ascii=False)


# Claude model tier -> Codex reasoning effort. See references/codex.md section 5.
TIER_TO_EFFORT = {"fable": "high", "opus": "medium", "sonnet": "low", "haiku": "low"}
EFFORT_TO_TIER = {"low": "sonnet", "medium": "opus", "high": "opus", "xhigh": "opus", "max": "opus", "ultra": "opus"}
VERIFY_ROLE = re.compile(r"review|verif|valid|\bqa\b|critic|audit|검증|리뷰|검토", re.I)


def claude_tier(model):
    m = (model or "").lower()
    return next((t for t in ("fable", "opus", "sonnet", "haiku") if t in m), None)


def md_agent_to_toml(md_text):
    meta, body = hkscan.parse_frontmatter(md_text)
    name, desc = meta.get("name", ""), meta.get("description", "")
    lines = [f"name = {toml_string(name)}", f"description = {toml_string(desc)}"]
    tier = claude_tier(meta.get("model"))
    if tier:
        effort = TIER_TO_EFFORT[tier]
        if tier == "opus" and VERIFY_ROLE.search(name + " " + desc):
            effort = "high"
        lines.append(f'model_reasoning_effort = "{effort}"')
        lines.append(f"# harnesskit: claude_model={meta['model']} (references/codex.md 5절). model 은 부모 세션에서 상속한다.")
        if tier in ("sonnet", "haiku"):
            lines.append('# 가벼운 역할: 계정에서 쓸 수 있으면 model = "gpt-6-luna" 를 지정한다.')
        elif tier == "fable":
            lines.append("# fable 급 역할은 보통 메인 에이전트가 맡는다. 서브에이전트로 둘 이유가 없으면 오케스트레이터에 합친다.")
    lines.append(f"developer_instructions = {toml_multiline(body.strip() + chr(10))}")
    return "\n".join(lines) + "\n"


def toml_agent_to_md(toml_text):
    def basic(m):
        return json.loads('"' + m.group(1) + '"') if m else ""
    name = basic(re.search(r'^name\s*=\s*"(.*)"', toml_text, re.M))
    desc = basic(re.search(r'^description\s*=\s*"(.*)"', toml_text, re.M))
    body = re.search(r"developer_instructions\s*=\s*(?:'''|\"\"\")\n?(.*?)(?:'''|\"\"\")", toml_text, re.S)
    tier = re.search(r"#\s*harnesskit:\s*claude_model=([\w.-]+)", toml_text)
    effort = re.search(r'^model_reasoning_effort\s*=\s*"(\w+)"', toml_text, re.M)
    model = tier.group(1) if tier else EFFORT_TO_TIER.get(effort.group(1)) if effort else None
    head = f"---\nname: {name}\ndescription: {json.dumps(desc, ensure_ascii=False)}\n"
    if model:
        head += f"model: {model}\n"
    return head + f"---\n\n{body.group(1).strip() if body else ''}\n"


def cmd_mirror(project, to):
    lock = load_lock(project)
    if not lock:
        sys.exit("harnesskit.lock not found; run `hklock.py write` first")
    h = lock.get("harness", {})
    src_skills, dst_skills = (".claude/skills", ".agents/skills") if to == "codex" else (".agents/skills", ".claude/skills")
    done = []
    for s in h.get("skills", []):
        src, dst = os.path.join(project, src_skills, s), os.path.join(project, dst_skills, s)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            done.append(os.path.relpath(dst, project))
    for a in h.get("agents", []):
        if to == "codex":
            src, dst = os.path.join(project, ".claude", "agents", a + ".md"), os.path.join(project, ".codex", "agents", a + ".toml")
            conv = md_agent_to_toml
        else:
            src, dst = os.path.join(project, ".codex", "agents", a + ".toml"), os.path.join(project, ".claude", "agents", a + ".md")
            conv = toml_agent_to_md
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, encoding="utf-8") as f:
                text = conv(f.read())
            with open(dst, "w", encoding="utf-8") as f:
                f.write(text)
            done.append(os.path.relpath(dst, project))
    print(json.dumps({"mirrored": done}, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--project", default=os.getcwd())
    w.add_argument("--data", required=True)
    s = sub.add_parser("status")
    s.add_argument("--project", default=os.getcwd())
    s.add_argument("--brief", action="store_true")
    m = sub.add_parser("mirror")
    m.add_argument("--project", default=os.getcwd())
    m.add_argument("--to", choices=("codex", "claude"), default="codex")
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.cmd == "write":
        cmd_write(project, a.data)
    elif a.cmd == "status":
        cmd_status(project, a.brief)
    else:
        cmd_mirror(project, a.to)


if __name__ == "__main__":
    main()
