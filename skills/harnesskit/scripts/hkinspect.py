#!/usr/bin/env python3
"""HarnessKit security gate: run NVIDIA SkillSpector before anything is installed.

  hkinspect.py PATH [--plugin NAME] [--full] [--baseline FILE] [--out FILE] [--timeout SEC]

By default only the install scope is scanned: what an agent loads or runs
(skills, agents, commands, hooks, output styles, plugin manifest, MCP config).
Tests, CI files, translated READMEs and adapters for other tools are left out.
--full scans the whole repository.

PATH is a local directory (a cloned repository, a plugin folder, or a skill
folder) or a single SKILL.md. With --plugin, PATH is a marketplace repository
and only that plugin's folder is scanned.

The scan always runs with --no-llm: file contents never go to an LLM. When the
network is available, SkillSpector still sends dependency names and versions
to OSV.dev for CVE lookups; offline it uses a built-in fallback list.

Verdicts follow SkillSpector's recommendation: SAFE, CAUTION, DO_NOT_INSTALL.
An incomplete analysis is raised to at least CAUTION.

Exit codes: 0 SAFE, 1 CAUTION, 2 DO_NOT_INSTALL, 3 SkillSpector missing,
4 scan error or plugin not found. Output is JSON on stdout (or --out).
Standard library only; never executes code from the scanned path.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

INSTALL = [
    "uv tool install git+https://github.com/NVIDIA/skillspector.git",
    "(uv가 없으면 먼저: python3 -m pip install --user uv  또는  https://docs.astral.sh/uv/ 설치 안내)",
]
EXIT = {"SAFE": 0, "CAUTION": 1, "DO_NOT_INSTALL": 2}
RANK = {"SAFE": 0, "CAUTION": 1, "DO_NOT_INSTALL": 2}


def find_skillspector():
    exe = shutil.which("skillspector")
    if exe:
        return exe
    cand = os.path.join(os.path.expanduser("~"), ".local", "bin", "skillspector")
    return cand if os.path.isfile(cand) else None


def resolve_plugin(repo, name):
    """Return the local folder of plugin NAME in a marketplace repo, or a remote source."""
    mk = os.path.join(repo, ".claude-plugin", "marketplace.json")
    try:
        with open(mk, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None, None
    for p in data.get("plugins", []):
        if p.get("name") == name:
            src = p.get("source")
            if isinstance(src, str):
                path = os.path.normpath(os.path.join(repo, src))
                return (path, None) if os.path.isdir(path) else (None, src)
            return None, src
    return None, None


PLUGIN_PARTS = [".claude-plugin", "skills", "agents", "commands", "hooks", "output-styles", ".mcp.json",
                "SKILL.md", "scripts", "references", "assets"]
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "tests", "test", "node_modules", ".github")


def stage(target):
    """Copy only what an agent loads or runs (the install scope) into a temp folder.

    Whole repositories also carry tests, translated READMEs, CI files and adapters
    for other tools; scanning those buries the findings that matter.
    """
    tmp = tempfile.mkdtemp(prefix="hk-inspect-")
    # A folder named like "x.md" is read as a markdown file by SkillSpector; keep the name plain.
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(os.path.normpath(target))).strip("-") or "target"
    dst = os.path.join(tmp, name)
    if os.path.isfile(target):
        os.makedirs(dst)
        shutil.copy2(target, dst)
        return tmp, dst, [os.path.basename(target)]
    parts = []
    manifest = os.path.join(target, ".claude-plugin", "plugin.json")
    if os.path.isfile(manifest) or os.path.isdir(os.path.join(target, "skills")):
        parts = list(PLUGIN_PARTS)
        try:
            with open(manifest, encoding="utf-8") as f:
                m = json.load(f)
            for key in ("skills", "agents", "commands", "hooks", "outputStyles"):
                v = m.get(key)
                for p in ([v] if isinstance(v, str) else v if isinstance(v, list) else []):
                    parts.append(os.path.normpath(p).split(os.sep)[0])
        except (OSError, ValueError):
            pass
    if not parts:  # a single skill folder or an unknown layout: everything except noise
        shutil.copytree(target, dst, ignore=SKIP)
        return tmp, dst, ["(전체)"]
    os.makedirs(dst)
    kept = []
    for p in dict.fromkeys(parts):
        src = os.path.join(target, p)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, p), ignore=SKIP)
            kept.append(p + "/")
        elif os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst, p))
            kept.append(p)
    return tmp, dst, kept


def summarize(report, exit_code):
    risk = report.get("risk_assessment") or {}
    rec = risk.get("recommendation") or ("DO_NOT_INSTALL" if exit_code == 1 else "SAFE")
    comp = report.get("analysis_completeness") or {}
    complete = comp.get("is_complete", True)
    if complete is False and RANK.get(rec, 0) < RANK["CAUTION"]:
        rec = "CAUTION"
    issues = report.get("issues") or []
    by_sev = {}
    for i in issues:
        s = str(i.get("severity", "UNKNOWN")).upper()
        by_sev[s] = by_sev.get(s, 0) + 1
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    # SkillSpector expands grouped findings per occurrence; keep one line per (rule, place).
    seen, unique = set(), []
    for i in sorted(issues, key=lambda i: (order.get(str(i.get("severity", "")).upper(), 9), -float(i.get("confidence") or 0))):
        loc = i.get("location") or {}
        key = (i.get("id"), loc.get("file"), loc.get("start_line"))
        if key not in seen:
            seen.add(key)
            unique.append(i)
    top = unique[:10]
    meta = report.get("metadata") or {}
    return {
        "status": "ok",
        "verdict": rec,
        "score": risk.get("score"),
        "severity": risk.get("severity"),
        "complete": complete,
        "issues_by_severity": by_sev,
        "top_issues": [{
            "id": i.get("id"), "category": i.get("category"), "severity": i.get("severity"),
            "confidence": i.get("confidence"),
            "where": f"{(i.get('location') or {}).get('file', '?')}:{(i.get('location') or {}).get('start_line', '?')}",
            "surface": i.get("surface"),
        } for i in top],
        "has_executable_scripts": meta.get("has_executable_scripts"),
        "llm_requested": meta.get("llm_requested"),
        "skillspector_version": meta.get("skillspector_version"),
        "skillspector_exit": exit_code,
    }


def run(path, plugin=None, timeout=900, full=False, baseline=None):
    target = os.path.abspath(path)
    mk = os.path.join(target, ".claude-plugin", "marketplace.json")
    if not plugin and os.path.isfile(mk) and not os.path.isfile(os.path.join(target, ".claude-plugin", "plugin.json")):
        # A marketplace repository: scan the plugin, not the whole repository.
        try:
            with open(mk, encoding="utf-8") as f:
                names = [p.get("name") for p in json.load(f).get("plugins", [])]
        except (OSError, ValueError):
            names = []
        if len(names) == 1:
            plugin = names[0]
        elif names:
            return {"status": "choose-plugin", "plugins": names,
                    "next": "설치할 플러그인 이름을 --plugin 으로 지정해 다시 실행한다."}, 4
    if plugin:
        local, remote = resolve_plugin(target, plugin)
        if not local:
            return {"status": "plugin-not-found" if remote is None else "remote-source",
                    "plugin": plugin, "remote_source": remote,
                    "next": "remote_source의 저장소를 새 임시 폴더에 받은 뒤 그 경로로 다시 실행한다." if remote else
                            "marketplace.json에서 플러그인 이름을 확인한다."}, 4
        target = local
    if not os.path.exists(target):
        return {"status": "error", "message": f"경로가 없음: {target}"}, 4
    exe = find_skillspector()
    if not exe:
        return {"status": "missing", "message": "SkillSpector가 없어 보안 점검을 할 수 없다. 점검 없이는 설치하지 않는다.",
                "install": INSTALL, "requires": "Python 3.12 이상 (uv가 자동으로 받는다)"}, 3
    tmp, scan_path, scope = (None, target, ["(저장소 전체)"]) if full else stage(target)
    cmd = [exe, "scan", scan_path, "--no-llm", "--format", "json"]
    if baseline:
        cmd += ["--baseline", os.path.abspath(baseline)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"{timeout}초 안에 끝나지 않음", "target": target}, 4
    except OSError as e:
        return {"status": "error", "message": str(e), "target": target}, 4
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if proc.returncode == 2:
        return {"status": "error", "message": (proc.stderr or proc.stdout).strip()[-800:], "target": target}, 4
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        return {"status": "error", "message": "JSON 출력을 읽지 못함", "stderr": proc.stderr.strip()[-800:], "target": target}, 4
    out = summarize(report, proc.returncode)
    out["target"] = target
    out["scope"] = scope
    return out, EXIT.get(out["verdict"], 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--plugin")
    ap.add_argument("--out")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--full", action="store_true", help="scan the whole repository instead of the install scope")
    ap.add_argument("--baseline", help="SkillSpector baseline file with reviewed, accepted findings")
    a = ap.parse_args(argv)
    result, code = run(a.path, a.plugin, a.timeout, a.full, a.baseline)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    sys.exit(code)


if __name__ == "__main__":
    main()
