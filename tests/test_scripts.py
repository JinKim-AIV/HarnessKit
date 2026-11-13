"""Tests for HarnessKit scripts. Run: python3 -m unittest discover -s tests

Fixtures are synthetic: they mimic the structure of real plugins
(SessionStart bootstrap hook, output style, duplicate skill name)
without copying any third-party text.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "harnesskit", "scripts")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(text).lstrip())


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def skill(path, name, desc, extra=""):
    write(os.path.join(path, "SKILL.md"), f"---\nname: {name}\ndescription: {desc}\n{extra}---\n\nbody\n")


class Env:
    """A fake home with Claude Code and Codex directories."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="hk-test-")
        self.claude = os.path.join(self.root, "claude")
        self.codex = os.path.join(self.root, "codex")
        self.project = os.path.join(self.root, "proj")
        os.makedirs(self.project)
        os.makedirs(self.claude)

    def run(self, script, *args):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.claude, CODEX_HOME=self.codex, HOME=self.root)
        out = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, script), *args],
                             capture_output=True, text=True, env=env, check=True)
        return out.stdout

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def fake_bootstrap_plugin(base):
    """Plugin shaped like a process framework: SessionStart hook that injects a skill file."""
    write(os.path.join(base, ".claude-plugin", "marketplace.json"),
          '{"name": "fake-market", "plugins": [{"name": "superpowers", "source": "./"}]}')
    write(os.path.join(base, ".claude-plugin", "plugin.json"), '{"name": "superpowers", "license": "MIT"}')
    write(os.path.join(base, "hooks", "hooks.json"), json.dumps({"hooks": {"SessionStart": [
        {"matcher": "startup", "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run\" boot"}]}]}}))
    write(os.path.join(base, "hooks", "boot"), 'cat "${PLUGIN_ROOT}/skills/using-superpowers/SKILL.md"\n')
    skill(os.path.join(base, "skills", "using-superpowers"), "using-superpowers",
          "Use when starting any conversation - find and use skills")
    write(os.path.join(base, "skills", "using-superpowers", "SKILL.md"),
          "---\nname: using-superpowers\ndescription: Use when starting any conversation\n---\n" + "rule " * 400)
    skill(os.path.join(base, "skills", "verification-before-completion"), "verification-before-completion",
          "Use before claiming work is complete")
    skill(os.path.join(base, "skills", "brainstorming"), "brainstorming",
          "\"You MUST use this before building components or adding functionality\"")


def fake_style_plugin(base):
    write(os.path.join(base, ".claude-plugin", "plugin.json"), '{"name": "attention-span"}')
    write(os.path.join(base, "output-styles", "attention-kind.md"),
          "---\nname: Attention-kind\ndescription: short answers\n---\nLead with the conclusion.\n")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    def test_summary_is_short_and_full_json_still_written(self):
        skill(os.path.join(self.e.claude, "skills", "my-review"), "my-review", "review pull requests " * 40)
        out = os.path.join(self.e.root, "scan.json")
        text = self.e.run("hkscan.py", "env", "--project", self.e.project, "--out", out, "--summary")
        self.assertIn("my-review", text)
        self.assertLess(len(text.encode("utf-8")), 2000)
        self.assertGreater(len(json.loads(read(out))["claude"]["items"][0]["skills"][0]["description"]), 500)

    def test_repo_scan_estimates_bootstrap_injection(self):
        repo = os.path.join(self.e.root, "repo")
        fake_bootstrap_plugin(repo)
        data = json.loads(self.e.run("hkscan.py", "repo", repo))
        item = data["items"][0]
        self.assertEqual(item["plugin_id"], "superpowers@fake-market")
        hook = item["hooks"][0]
        self.assertEqual(hook["event"], "SessionStart")
        self.assertGreater(hook["injects_estimate"]["chars"], 1500)

    def test_plugin_manifest_lists_hook_files(self):
        repo = os.path.join(self.e.root, "repo")
        write(os.path.join(repo, ".claude-plugin", "plugin.json"),
              json.dumps({"name": "minimal", "hooks": ["./hooks/a.json", "./hooks/hooks.json", {"hooks": {
                  "Stop": [{"hooks": [{"type": "command", "command": "true"}]}]}}]}))
        write(os.path.join(repo, "hooks", "a.json"), json.dumps({"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "node hooks/on.js"}]}],
            "SubagentStart": [{"hooks": [{"type": "command", "command": "node hooks/on.js"}]}]}}))
        write(os.path.join(repo, "hooks", "hooks.json"), json.dumps({"hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "true"}]}]}}))
        hooks = json.loads(self.e.run("hkscan.py", "repo", repo))["items"][0]["hooks"]
        self.assertEqual(sorted(h["event"] for h in hooks),
                         ["SessionStart", "Stop", "SubagentStart", "UserPromptSubmit"])
        self.assertIn("injects_estimate", [h for h in hooks if h["event"] == "SubagentStart"][0])

    def test_env_scan_sees_user_project_and_codex(self):
        skill(os.path.join(self.e.claude, "skills", "my-review"), "my-review", "review pull requests")
        skill(os.path.join(self.e.claude, "skills", "synced", "bucket-1", "frontend-design"),
              "frontend-design", "Create frontend interfaces")
        skill(os.path.join(self.e.project, ".claude", "skills", "orch"), "orch", "orchestrator")
        write(os.path.join(self.e.project, ".claude", "agents", "analyst.md"), "---\nname: analyst\ndescription: a\n---\n")
        write(os.path.join(self.e.project, "CLAUDE.md"), "## 하네스: 데모\n")
        skill(os.path.join(self.e.codex, "skills", "humanize"), "humanize", "윤문")
        write(os.path.join(self.e.codex, "config.toml"), "[mcp_servers.context7]\ncommand = 'x'\n")
        data = json.loads(self.e.run("hkscan.py", "env", "--project", self.e.project))
        ids = {i["id"] for i in data["claude"]["items"]}
        self.assertIn("skill:user:my-review", ids)
        self.assertNotIn("skill:user:synced", ids)
        self.assertIn("skill:synced:frontend-design", ids)
        self.assertIn("skill:project:orch", ids)
        codex_ids = {i["id"] for i in data["codex"]["items"]}
        self.assertIn("codex-skill:user:humanize", codex_ids)
        self.assertIn("codex-mcp:user:context7", codex_ids)
        self.assertTrue(data["harness"]["exists"])
        self.assertEqual(data["harness"]["sections"]["CLAUDE.md"], "데모")
        self.assertEqual(data["harness"]["claude"]["agents"], ["analyst"])


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    def check(self, *args):
        return json.loads(self.e.run("hkcheck.py", "--project", self.e.project, *args))

    def scan_repo(self, name, builder):
        repo = os.path.join(self.e.root, name)
        builder(repo)
        out = os.path.join(self.e.root, name + ".json")
        self.e.run("hkscan.py", "repo", repo, "--out", out)
        return out

    def test_catalog_contradiction_between_candidates(self):
        a = self.scan_repo("sp", fake_bootstrap_plugin)
        b = self.scan_repo("as", fake_style_plugin)
        data = self.check("--candidate-scan", a, "--candidate-scan", b)
        types = {(f["type"], f["severity"]) for f in data["findings"]}
        self.assertIn(("contradiction", "high"), types)

    def test_duplicate_skill_name(self):
        skill(os.path.join(self.e.claude, "skills", "verification-before-completion"),
              "verification-before-completion", "Use before claiming work is complete")
        a = self.scan_repo("sp", fake_bootstrap_plugin)
        data = self.check("--candidate-scan", a)
        dup = [f for f in data["findings"] if "두 군데 이상" in f["detail"]]
        self.assertEqual(len(dup), 1)

    def test_harnesskit_vs_original_harness(self):
        data = self.check("--candidate", "harnesskit", "--candidate", "harness")
        self.assertTrue(any(f["type"] == "trigger" and f["severity"] == "high" for f in data["findings"]))

    def test_codex_and_claude_skills_do_not_conflict(self):
        skill(os.path.join(self.e.claude, "skills", "reviewer-a"), "reviewer-a", "code review helper")
        skill(os.path.join(self.e.codex, "skills", "reviewer-b"), "reviewer-b", "code review helper")
        data = self.check()
        self.assertFalse([f for f in data["findings"] if f["type"] == "trigger?"])

    def test_same_runtime_intent_overlap_goes_to_review(self):
        skill(os.path.join(self.e.claude, "skills", "reviewer-a"), "reviewer-a", "code review helper")
        skill(os.path.join(self.e.claude, "skills", "reviewer-b"), "reviewer-b", "reviewing pull requests")
        data = self.check()
        review = [f for f in data["findings"] if f["type"] == "trigger?"]
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["severity"], "review")

    def test_out_creates_missing_dirs(self):
        out = os.path.join(self.e.project, "_workspace", "harnesskit", "check.json")
        self.e.run("hkcheck.py", "--project", self.e.project, "--out", out)
        scan = os.path.join(self.e.project, "_workspace", "harnesskit", "scan.json")
        self.e.run("hkscan.py", "env", "--project", self.e.project, "--out", scan)
        self.assertTrue(os.path.isfile(out) and os.path.isfile(scan))

    def test_bundled_skill_is_one_tool(self):
        # A synced frontend-design skill must not also count as the example-skills bundle.
        skill(os.path.join(self.e.claude, "skills", "synced", "b", "frontend-design"), "frontend-design", "Create frontend interfaces")
        skill(os.path.join(self.e.claude, "skills", "synced", "b", "skill-creator"), "skill-creator", "Create skills")
        data = self.check()
        comps = {c["label"]: c["catalog_ids"] for c in data["components"]}
        self.assertEqual(comps["frontend-design"], ["frontend-design"])
        self.assertEqual(comps["skill-creator"], ["skill-creator"])
        self.assertFalse([f for f in data["findings"] if "example-skills" in " ".join(f["items"])])

    def test_unknown_catalog_id_fails(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.check("--candidate", "no-such-tool")


class LockTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        p = self.e.project
        write(os.path.join(p, ".claude", "agents", "analyst.md"),
              "---\nname: analyst\ndescription: Analyze requirements\nmodel: sonnet\n---\n\nRead the spec and list risks.\n")
        write(os.path.join(p, ".claude", "agents", "verifier.md"),
              "---\nname: verifier\ndescription: 결과 교차 검증\nmodel: opus\n---\n\nCheck the analyst output.\n")
        skill(os.path.join(p, ".claude", "skills", "demo-orch"), "demo-orch", "demo orchestrator")
        self.data = os.path.join(self.e.root, "data.json")
        write(self.data, json.dumps({
            "runtimes": ["claude", "codex"],
            "tools": [{"id": "im-not-ai", "status": "use", "why": "Korean reports"}],
            "decisions": [{"finding": "superpowers vs harnesskit (slot)", "choice": "disable superpowers here"}],
            "harness": {"orchestrator": "demo-orch", "agents": ["analyst", "verifier"], "skills": ["demo-orch"]},
        }))

    def tearDown(self):
        self.e.cleanup()

    def test_write_status_mirror(self):
        p = self.e.project
        self.e.run("hklock.py", "write", "--project", p, "--data", self.data)
        lock = json.loads(read(os.path.join(p, "harnesskit.lock")))
        self.assertIn(".claude/agents/analyst.md", lock["harness"]["files"])
        self.assertEqual(self.e.run("hklock.py", "status", "--project", p, "--brief"), "")

        with open(os.path.join(p, ".claude", "agents", "analyst.md"), "a", encoding="utf-8") as f:
            f.write("Also check tests.\n")
        line = self.e.run("hklock.py", "status", "--project", p, "--brief")
        self.assertIn("evolve", line)

        skill(os.path.join(self.e.claude, "skills", "new-tool"), "new-tool", "something new")
        status = json.loads(self.e.run("hklock.py", "status", "--project", p))
        self.assertIn("claude_skills", status["env_changes"])

        self.e.run("hklock.py", "mirror", "--project", p, "--to", "codex")
        toml = read(os.path.join(p, ".codex", "agents", "analyst.toml"))
        self.assertIn('name = "analyst"', toml)
        self.assertIn("Read the spec and list risks.", toml)
        self.assertIn('model_reasoning_effort = "low"', toml)
        self.assertIn("claude_model=sonnet", toml)
        vtoml = read(os.path.join(p, ".codex", "agents", "verifier.toml"))
        self.assertIn('model_reasoning_effort = "high"', vtoml)
        self.assertTrue(os.path.isfile(os.path.join(p, ".agents", "skills", "demo-orch", "SKILL.md")))

        os.remove(os.path.join(p, ".claude", "agents", "analyst.md"))
        self.e.run("hklock.py", "mirror", "--project", p, "--to", "claude")
        md = read(os.path.join(p, ".claude", "agents", "analyst.md"))
        self.assertIn("name: analyst", md)
        self.assertIn("model: sonnet", md)
        self.assertIn("Read the spec and list risks.", md)

    def test_status_reports_missing_token_ops_only_in_full_output(self):
        p = self.e.project
        self.e.run("hklock.py", "write", "--project", p, "--data", self.data)
        status = json.loads(self.e.run("hklock.py", "status", "--project", p))
        self.assertEqual(status["token_ops"], {"ledger": False, "caps": False})
        self.assertTrue(any("hktokens.py" in h["message"] for h in status["hints"]))
        self.assertEqual(self.e.run("hklock.py", "status", "--project", p, "--brief"), "")

        skill(os.path.join(p, ".claude", "skills", "demo-orch"), "demo-orch", "demo orchestrator",
              extra="")
        with open(os.path.join(p, ".claude", "skills", "demo-orch", "SKILL.md"), "a", encoding="utf-8") as f:
            f.write('python3 "$HK/hktokens.py" mark "<RUN> ② 빌드" --cap builder=40\n')
        self.e.run("hklock.py", "write", "--project", p, "--data", self.data)
        status = json.loads(self.e.run("hklock.py", "status", "--project", p))
        self.assertEqual(status["token_ops"], {"ledger": True, "caps": True})
        self.assertEqual(status["hints"], [])

        # 사용자가 끈 결정은 lock을 다시 써도 남고, 알림도 하지 않는다
        off = json.loads(read(self.data))
        off["harness"]["token_ops"] = "off"
        write(self.data, json.dumps(off))
        self.e.run("hklock.py", "write", "--project", p, "--data", self.data)
        on_again = json.loads(read(self.data))
        on_again["harness"].pop("token_ops")
        write(self.data, json.dumps(on_again))
        self.e.run("hklock.py", "write", "--project", p, "--data", self.data)
        self.assertEqual(json.loads(read(os.path.join(p, "harnesskit.lock")))["harness"]["token_ops"], "off")
        self.assertIsNone(json.loads(self.e.run("hklock.py", "status", "--project", p))["token_ops"])


class TokensTests(unittest.TestCase):
    """hktokens.py: 세션 기록(jsonl)을 흉내 낸 가짜 기록으로 장부·점검·크기 확인."""
    SID = "11111111-2222-3333-4444-555555555555"

    def setUp(self):
        import datetime as dt
        import re
        self.dt = dt
        self.e = Env()
        self.p = self.e.project
        self.logs = os.path.join(self.e.claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(self.p)))
        self.dir = os.path.join(self.p, "_workspace", "tokens")
        self.t0 = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(minutes=20)

    def tearDown(self):
        self.e.cleanup()

    def at(self, minutes):
        return (self.t0 + self.dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def lines(self, path, recs, cwd=None):
        rows = [{"type": "user", "cwd": cwd or self.p, "timestamp": self.at(0), "message": {"role": "user"}}]
        for minute, mid, usage, ntools, *model in recs:
            msg = {"id": mid, "model": model[0] if model else "claude-opus-5-5", "usage": usage,
                   "content": [{"type": "text", "text": "x"}]}
            rows.append({"type": "assistant", "timestamp": self.at(minute), "message": msg})
            for k in range(ntools):  # 한 응답이 블록마다 여러 줄로 기록된다
                rows.append({"type": "assistant", "timestamp": self.at(minute), "message": dict(
                    msg, content=[{"type": "tool_use", "id": f"{mid}-t{k}", "name": "Bash"}])})
        write(path, "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")

    def usage(self, cache_read, out=10):
        return {"input_tokens": 5, "cache_creation_input_tokens": 100, "cache_read_input_tokens": cache_read,
                "output_tokens": out}

    def tokens(self, *args, sid=SID, check=True):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.e.claude, CODEX_HOME=self.e.codex, HOME=self.e.root)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        if sid:
            env["CLAUDE_CODE_SESSION_ID"] = sid
        return subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "hktokens.py"), *args, "--project", self.p,
                               "--dir", self.dir], capture_output=True, text=True, env=env, cwd=self.p, check=check)

    def fake_session(self, base=None, sid=SID, cwd=None):
        base = base or self.logs
        self.lines(os.path.join(base, sid + ".jsonl"), [
            (1, "m1", self.usage(1000), 2),
            (2, "syn", self.usage(0, 0), 0, "<synthetic>"),
            (8, "m2", self.usage(250_000), 1),
        ], cwd=cwd)
        sub = os.path.join(base, sid, "subagents")
        self.lines(os.path.join(sub, "agent-a.jsonl"), [(6, "a1", self.usage(2000), 2), (7, "a2", self.usage(3000), 1)])
        write(os.path.join(sub, "agent-a.meta.json"), json.dumps({"agentType": "builder", "description": "빌드"}))
        self.lines(os.path.join(sub, "agent-b.jsonl"), [(7, "b1", self.usage(500), 1)])
        write(os.path.join(sub, "agent-b.meta.json"), json.dumps({"agentType": "reviewer", "description": "검사"}))
        # 같은 폴더의 다른 세션: 장부에 섞이면 안 된다
        self.lines(os.path.join(base, "other-session.jsonl"), [(9, "o1", self.usage(9_999_999), 0)])

    def test_mark_report_counts_once_per_response_and_compares_caps(self):
        self.fake_session()
        self.tokens("mark", "run-1 ① 준비", "--at", self.at(0))
        self.tokens("mark", "run-1 ② 빌드", "--cap", "builder=2", "--at", self.at(5))
        out = self.tokens("report").stdout
        ledger = read(os.path.join(self.dir, "ledger.md"))
        # 메인: m1(1,115) + m2(250,115), <synthetic> 제외, 같은 id 여러 줄은 한 번만
        self.assertIn("| run-1 | 251,230 | 5,845 | **257,075** | 5 |", ledger)
        self.assertIn("builder · 빌드 | 2 / 3 | 2 · **넘음** |", ledger)
        self.assertIn("reviewer · 검사 | 1 / 1 | 상한 없음 |", ledger)
        self.assertIn("다른 세션의 응답 1개는 빼었습니다", ledger)
        self.assertNotIn("9,999,999", ledger)
        self.assertIn("상한 넘음: builder 3/2", out)
        self.assertIn("상한 없음: reviewer", out)
        self.assertLess(len(out.splitlines()), 8, "화면 요약은 몇 줄이어야 한다")

    def test_mark_suggests_new_session_when_conversation_is_large(self):
        self.fake_session()
        quiet = self.tokens("mark", "run-1 ① 준비", "--at", self.at(0), "--max-context", "300000").stdout
        self.assertEqual(quiet, "")
        loud = self.tokens("mark", "run-1 ② 빌드", "--at", self.at(9)).stdout
        self.assertIn("대화 크기 250k", loud)
        self.assertIn("새 세션", loud)

    def test_warns_when_session_was_opened_in_another_folder(self):
        parent = os.path.join(self.e.claude, "projects", "-elsewhere")
        self.fake_session(base=parent, cwd="/elsewhere")
        out = self.tokens("mark", "run-1 ① 준비", "--at", self.at(0)).stdout
        self.assertIn("/elsewhere 에서 열었습니다", out)
        again = self.tokens("mark", "run-1 ② 빌드", "--at", self.at(5)).stdout
        self.assertNotIn("열었습니다", again)  # 폴더 경고는 실행의 첫 표시에서만
        rep = self.tokens("report").stdout
        self.assertIn("run-1 합계 257k", rep)  # 세션 id로 기록을 찾아 장부가 비지 않는다
        self.assertIn("경고:", rep)

    def test_without_session_id_warns_when_this_folder_has_no_records(self):
        out = self.tokens("check", sid=None).stdout
        self.assertIn("세션 기록이 없습니다", out)

    def test_codex_is_not_measured(self):
        self.tokens("mark", "run-1 ① 준비", "--runtime", "codex", sid=None)
        out = self.tokens("report", "--runtime", "codex", sid=None).stdout
        self.assertIn("측정 안 됨", out)
        self.assertIn("측정 안 됨", read(os.path.join(self.dir, "ledger.md")))

    def test_size_flags_handoff_files_over_limit(self):
        write(os.path.join(self.p, "_workspace", "01_small.md"), "a" * 100)
        write(os.path.join(self.p, "_workspace", "02_big.md"), "b" * 30_000)
        ok = self.tokens("size", "_workspace/01_*.md")
        self.assertIn("✓", ok.stdout)
        bad = self.tokens("size", "_workspace/*.md", check=False)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("02_big.md", bad.stdout)


FAKE_SKILLSPECTOR = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
assert args[0] == "scan" and "--no-llm" in args and "--format" in args, args
target = args[1]
if "evil" in target:
    rep, code = {"risk_assessment": {"score": 80, "severity": "HIGH", "recommendation": "DO_NOT_INSTALL"},
                 "issues": [{"id": "PI1", "category": "prompt_injection", "severity": "HIGH", "confidence": 0.9,
                             "location": {"file": "SKILL.md", "start_line": 3}, "surface": "instructions"}]}, 1
elif "partial" in target:
    rep, code = {"risk_assessment": {"score": 5, "severity": "LOW", "recommendation": "SAFE"},
                 "analysis_completeness": {"is_complete": False}, "issues": []}, 0
else:
    rep, code = {"risk_assessment": {"score": 0, "severity": "LOW", "recommendation": "SAFE"}, "issues": [],
                 "metadata": {"llm_requested": False}}, 0
print(json.dumps(rep)); sys.exit(code)
"""


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.fake = os.path.join(self.e.root, "bin", "skillspector")
        write(self.fake, FAKE_SKILLSPECTOR)
        os.chmod(self.fake, 0o755)

    def tearDown(self):
        self.e.cleanup()

    def inspect(self, *args, fake=True):
        path = (os.path.dirname(self.fake) + os.pathsep if fake else "") + "/usr/bin:/bin"
        env = dict(os.environ, HOME=self.e.root, PATH=path)
        out = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "hkinspect.py"), *args],
                             capture_output=True, text=True, env=env)
        return json.loads(out.stdout), out.returncode

    def test_verdicts(self):
        for name, verdict, code in (("good-skill", "SAFE", 0), ("evil-skill", "DO_NOT_INSTALL", 2), ("partial-skill", "CAUTION", 1)):
            d = os.path.join(self.e.root, name)
            skill(d, name, "x")
            res, rc = self.inspect(d)
            self.assertEqual((res["verdict"], rc), (verdict, code), name)
        res, _ = self.inspect(os.path.join(self.e.root, "evil-skill"))
        self.assertEqual(res["top_issues"][0]["where"], "SKILL.md:3")

    def test_missing_skillspector_blocks(self):
        d = os.path.join(self.e.root, "good-skill")
        skill(d, "good-skill", "x")
        res, rc = self.inspect(d, fake=False)
        self.assertEqual((res["status"], rc), ("missing", 3))

    def test_plugin_in_marketplace(self):
        repo = os.path.join(self.e.root, "market")
        write(os.path.join(repo, ".claude-plugin", "marketplace.json"), json.dumps({"name": "m", "plugins": [
            {"name": "good", "source": "./plugins/good"},
            {"name": "remote", "source": {"source": "github", "repo": "someone/remote"}}]}))
        skill(os.path.join(repo, "plugins", "good", "skills", "a"), "a", "x")
        res, rc = self.inspect(repo, "--plugin", "good")
        self.assertEqual(res["verdict"], "SAFE")
        self.assertTrue(res["target"].endswith(os.path.join("plugins", "good")))
        res, rc = self.inspect(repo, "--plugin", "remote")
        self.assertEqual((res["status"], rc), ("remote-source", 4))


SKILLSPECTOR = shutil.which("skillspector") or (
    os.path.expanduser("~/.local/bin/skillspector") if os.path.isfile(os.path.expanduser("~/.local/bin/skillspector")) else None)


@unittest.skipUnless(SKILLSPECTOR, "SkillSpector가 설치된 환경에서만 실행")
class SelfInspectTests(unittest.TestCase):
    def test_kit_has_no_active_findings(self):
        kit = os.path.join(ROOT, "skills", "harnesskit")
        out = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "hkinspect.py"), kit,
                              "--baseline", os.path.join(kit, ".skillspector-baseline.yaml")],
                             capture_output=True, text=True, timeout=600,
                             env=dict(os.environ, PATH=os.path.dirname(SKILLSPECTOR) + os.pathsep + os.environ.get("PATH", "")))
        res = json.loads(out.stdout)
        self.assertEqual(res["issues_by_severity"], {}, res.get("top_issues"))
        self.assertIn(res["verdict"], ("SAFE", "CAUTION"))


class PersonalCatalogTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    def entry(self, **over):
        e = {"id": "my-slides", "name": "My Slides", "repo": "https://github.com/someone/my-slides", "license": "MIT",
             "layer": "task", "role": "slides", "use_when": ["발표 자료"], "skip_when": [], "install": {"claude": ["x"]},
             "detect": {"skills": ["my-slides"]}, "always_on": "설명문 1개", "external_data": "없음.",
             "conflicts": [{"with": "frontend-slides", "type": "trigger", "detail": "둘 다 슬라이드 요청에 반응", "resolve": "하나만"}],
             "verified": "direct", "memo": "인스타에서 봄"}
        e.update(over)
        path = os.path.join(self.e.root, "entry.json")
        write(path, json.dumps(e, ensure_ascii=False))
        return path

    def cat(self, *args, check=True):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.e.claude, CODEX_HOME=self.e.codex, HOME=self.e.root)
        return subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "hkcatalog.py"), *args],
                              capture_output=True, text=True, env=env, check=check)

    def test_add_find_check_remove(self):
        out = json.loads(self.cat("add", "--file", self.entry()).stdout)
        self.assertEqual(out["saved"], "my-slides")
        self.assertTrue(out["path"].startswith(self.e.root))
        mine = [json.loads(l) for l in self.cat("mine").stdout.splitlines()]
        self.assertEqual([m["id"] for m in mine], ["my-slides"])
        self.assertEqual(mine[0]["origin"], "mine")
        found = [json.loads(l)["id"] for l in self.cat("find", "--role", "slides").stdout.splitlines()]
        self.assertIn("my-slides", found)
        self.assertIn("frontend-slides", found)
        # hkcheck merges the personal catalog: the saved conflict shows up between candidates
        data = json.loads(self.e.run("hkcheck.py", "--project", self.e.project,
                                     "--candidate", "my-slides", "--candidate", "frontend-slides"))
        self.assertTrue(any("my-slides" in " ".join(f["items"]) and f["type"] == "trigger" for f in data["findings"]))
        self.cat("remove", "my-slides")
        self.assertEqual(self.cat("mine").stdout.strip(), "{}")

    def test_rejects_duplicates_and_bad_entries(self):
        dup = self.cat("add", "--file", self.entry(id="x-dup", repo="https://github.com/humbleteam/design-qa.git"), check=False)
        self.assertNotEqual(dup.returncode, 0)
        self.assertIn("이미 키트 카탈로그에 있음", dup.stderr)
        bad = self.cat("add", "--file", self.entry(layer="nope", conflicts=[{"with": "a", "type": "weird"}]), check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("layer", bad.stderr)


class ReadBudgetTests(unittest.TestCase):
    """What the agent reads is cost too. Keep the always-read and per-step documents small."""
    LIMITS = {"SKILL.md": 1600, "references/kit-build.md": 1500, "references/install.md": 1200,
              "references/mode-build.md": 11700, "references/build-maintain.md": 1000,
              "references/mode-check.md": 900, "references/mode-save.md": 1000, "references/mode-sync.md": 800,
              "references/token-ops.md": 1700}

    def test_documents_stay_within_budget(self):
        sys.path.insert(0, SCRIPTS)
        import hkscan
        over = {}
        for rel, limit in self.LIMITS.items():
            with open(os.path.join(ROOT, "skills", "harnesskit", rel), encoding="utf-8") as f:
                tokens = hkscan.approx_tokens(f.read())
            if tokens > limit:
                over[rel] = (tokens, limit)
        self.assertEqual(over, {}, "추정 토큰이 상한을 넘었다")


class CatalogTests(unittest.TestCase):
    def test_category_filter(self):
        out = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "hkcatalog.py"), "find", "--category", "ui-ux"],
                             capture_output=True, text=True, check=True).stdout
        ids = {json.loads(l)["id"] for l in out.splitlines() if l.strip() and l.strip() != "{}"}
        self.assertTrue({"web-design-reviewer", "design-qa", "design-review", "frontend-design"} <= ids)
        self.assertNotIn("im-not-ai", ids)

    def test_catalog_is_consistent(self):
        with open(os.path.join(ROOT, "skills", "harnesskit", "references", "catalog.json"), encoding="utf-8") as f:
            cat = json.load(f)
        ids = {e["id"] for e in cat["entries"]}
        self.assertEqual(len(ids), len(cat["entries"]), "duplicate ids")
        for e in cat["entries"]:
            for key in ("name", "layer", "verified", "conflicts"):
                self.assertIn(key, e, f"{e['id']} missing {key}")
            self.assertIn(e["verified"], ("direct", "survey"))
            for c in e["conflicts"]:
                self.assertIn(c["type"], cat["conflict_types"], f"{e['id']} bad conflict type")


if __name__ == "__main__":
    unittest.main()
