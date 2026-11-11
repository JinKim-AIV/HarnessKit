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

    def test_repo_scan_estimates_bootstrap_injection(self):
        repo = os.path.join(self.e.root, "repo")
        fake_bootstrap_plugin(repo)
        data = json.loads(self.e.run("hkscan.py", "repo", repo))
        item = data["items"][0]
        self.assertEqual(item["plugin_id"], "superpowers@fake-market")
        hook = item["hooks"][0]
        self.assertEqual(hook["event"], "SessionStart")
        self.assertGreater(hook["injects_estimate"]["chars"], 1500)

    def test_env_scan_sees_user_project_and_codex(self):
        skill(os.path.join(self.e.claude, "skills", "my-review"), "my-review", "review pull requests")
        skill(os.path.join(self.e.project, ".claude", "skills", "orch"), "orch", "orchestrator")
        write(os.path.join(self.e.project, ".claude", "agents", "analyst.md"), "---\nname: analyst\ndescription: a\n---\n")
        write(os.path.join(self.e.project, "CLAUDE.md"), "## 하네스: 데모\n")
        skill(os.path.join(self.e.codex, "skills", "humanize"), "humanize", "윤문")
        write(os.path.join(self.e.codex, "config.toml"), "[mcp_servers.context7]\ncommand = 'x'\n")
        data = json.loads(self.e.run("hkscan.py", "env", "--project", self.e.project))
        ids = {i["id"] for i in data["claude"]["items"]}
        self.assertIn("skill:user:my-review", ids)
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


class CatalogTests(unittest.TestCase):
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
