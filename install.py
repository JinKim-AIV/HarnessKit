#!/usr/bin/env python3
"""Install, update, or remove the HarnessKit skill for Claude Code and/or Codex.

  python3 install.py                 # detect Claude Code / Codex and install to each
  python3 install.py --target codex  # claude | codex | both | auto (default)
  python3 install.py --dry-run       # show what would happen
  python3 install.py --uninstall     # remove (a backup is kept)

Update: `git pull` in this repository, then run install.py again.

Claude Code: ~/.claude/skills/harnesskit   (honours CLAUDE_CONFIG_DIR)
Codex:       ~/.codex/skills/harnesskit    (honours CODEX_HOME)

Copying (not symlinking) keeps it working on Windows without developer mode.
Standard library only.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(REPO, "skills", "harnesskit")
NAME = "harnesskit"
MARKER = ".harnesskit-install.json"
HOME = os.path.expanduser("~")


def homes():
    return {
        "claude": os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude"),
        "codex": os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex"),
    }


def detect():
    found = []
    for rt, home in homes().items():
        if os.path.isdir(home) or shutil.which(rt):
            found.append(rt)
    return found


def version():
    try:
        with open(os.path.join(REPO, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def commit():
    try:
        out = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def backup(path, home, dry):
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(home, "backups", f"{NAME}-{ts}")
    if not dry:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(path, dst)
    return dst


def install_one(rt, dry):
    home = homes()[rt]
    dst = os.path.join(home, "skills", NAME)
    msgs = []
    if os.path.exists(dst):
        ours = os.path.isfile(os.path.join(dst, MARKER))
        b = backup(dst, home, dry)
        msgs.append(f"기존 {'HarnessKit' if ours else '같은 이름의 스킬'}을 백업: {b}")
    if not dry:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        with open(os.path.join(dst, MARKER), "w", encoding="utf-8") as f:
            json.dump({"version": version(), "commit": commit(), "source": REPO,
                       "installed_at": dt.datetime.now().replace(microsecond=0).isoformat()}, f, indent=1)
    msgs.append(f"{'[dry-run] ' if dry else ''}설치: {dst}")
    return msgs


def uninstall_one(rt, dry):
    home = homes()[rt]
    dst = os.path.join(home, "skills", NAME)
    if not os.path.exists(dst):
        return [f"{rt}: 설치되어 있지 않음"]
    if not os.path.isfile(os.path.join(dst, MARKER)):
        return [f"{rt}: {dst} 는 HarnessKit 설치 기록이 없어 지우지 않음. 직접 확인하세요."]
    b = backup(dst, home, dry)
    return [f"{'[dry-run] ' if dry else ''}제거(백업 보관): {b}"]


def self_check(project):
    """Run the kit's own conflict check against what is installed."""
    sys.path.insert(0, os.path.join(SRC, "scripts"))
    try:
        import hkcheck
        import hkscan
    except ImportError as e:
        return [f"자체 점검을 건너뜀: {e}"]
    env = hkscan.scan_env(project)
    with open(hkcheck.DEFAULT_CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    comps = hkcheck.build_components(env, ["harnesskit"], [], catalog)
    lines = []
    for f in hkcheck.check(env, comps, catalog):
        if f["severity"] in ("high", "medium") and any("harnesskit" in i for i in f["items"]):
            lines.append(f"- [{f['severity']}] {' / '.join(f['items'])}: {f['detail']} → {f['resolve']}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=("auto", "claude", "codex", "both"), default="auto")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", default=os.getcwd(), help="project used for the post-install self check")
    a = ap.parse_args(argv)

    if not os.path.isfile(os.path.join(SRC, "SKILL.md")):
        sys.exit(f"skills/harnesskit/SKILL.md 를 찾을 수 없습니다: {SRC}")

    targets = {"claude": ["claude"], "codex": ["codex"], "both": ["claude", "codex"]}.get(a.target) or detect()
    if not targets:
        sys.exit("Claude Code(~/.claude)도 Codex(~/.codex)도 찾지 못했습니다. --target claude 또는 --target codex 로 지정하세요.")

    print(f"HarnessKit {version()} ({commit() or 'no git'}) → {', '.join(targets)}")
    for rt in targets:
        for m in (uninstall_one if a.uninstall else install_one)(rt, a.dry_run):
            print(f"  {rt}: {m}")

    if a.uninstall:
        return
    if not a.dry_run:
        issues = self_check(a.project)
        if issues:
            print("\n설치 후 점검에서 확인할 것:")
            print("\n".join(issues))
        else:
            print("\n설치 후 점검: HarnessKit과 부딪히는 도구 없음.")
    if not (shutil.which("skillspector") or os.path.isfile(os.path.join(HOME, ".local", "bin", "skillspector"))):
        print("\n보안 점검 도구 SkillSpector가 없습니다. HarnessKit은 점검 없이 외부 스킬을 설치하지 않으므로 미리 설치해 두세요:")
        print("  uv tool install git+https://github.com/NVIDIA/skillspector.git   (uv가 없으면: python3 -m pip install --user uv)")
    print("\n다음 단계: 새 세션을 열고 프로젝트 폴더에서 '킷으로 이 프로젝트 하네스 만들어줘'라고 요청하세요.")
    print("업데이트: 이 저장소에서 git pull 후 install.py 를 다시 실행하세요.")


if __name__ == "__main__":
    main()
