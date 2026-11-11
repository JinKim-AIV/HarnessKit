#!/usr/bin/env python3
"""HarnessKit scanner.

Inventories what an AI coding agent will load, without running any of it:
skills, subagents, hooks, output styles, MCP servers and instruction files
for Claude Code and Codex. It can also scan a candidate repository that is
not installed yet, so conflicts can be checked before installation.

Usage:
  hkscan.py env  [--project DIR] [--out FILE]
  hkscan.py repo PATH [--out FILE]

Standard library only. Reads files, never executes anything it finds.
"""
import argparse
import json
import os
import re
import sys

DESC_LIMIT = 1536  # Claude Code truncates description + when_to_use here.
HOME = os.path.expanduser("~")
CLAUDE_HOME = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")


# ---------------------------------------------------------------- helpers

def read_text(path, limit=2_000_000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def read_json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def approx_tokens(text):
    """Rough token estimate: ~4 ASCII chars or ~1.5 other chars per token."""
    if not text:
        return 0
    ascii_n = sum(1 for c in text if ord(c) < 128)
    return round(ascii_n / 4 + (len(text) - ascii_n) / 1.5)


def parse_frontmatter(text):
    """Parse the leading YAML block of a markdown file (simple subset)."""
    if not text or not text.startswith("---"):
        return {}, text or ""
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block, body = text[3:end], text[end + 4:]
    data, key, buf, mode = {}, None, [], None

    def flush():
        if key is not None:
            joiner = "\n" if mode == "|" else " "
            data[key] = joiner.join(s.strip() for s in buf).strip()

    for line in block.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            flush()
            key, val, buf, mode = m.group(1), m.group(2).strip(), [], None
            if val in (">", "|", ">-", "|-"):
                mode = val[0]
            elif len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                buf = [val[1:-1]]
            elif val:
                buf = [val]
        elif key is not None and line.strip():
            buf.append(line.strip())
    flush()
    return data, body


def md_entry(path, kind):
    text = read_text(path)
    if text is None:
        return None
    meta, body = parse_frontmatter(text)
    name = meta.get("name") or (
        os.path.basename(os.path.dirname(path)) if kind == "skill"
        else os.path.splitext(os.path.basename(path))[0])
    desc = (meta.get("description", "") + " " + meta.get("when_to_use", "")).strip()
    listed = desc[:DESC_LIMIT]
    return {
        "name": name,
        "description": desc,
        "always_on_chars": len(listed),
        "always_on_tokens": approx_tokens(listed),
        "body_chars": len(body),
        "path": path,
        "disable_model_invocation": str(meta.get("disable-model-invocation", "")).lower() == "true",
    }


def list_dirs(path):
    try:
        return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    except OSError:
        return []


def list_files(path, ext=".md"):
    try:
        return sorted(f for f in os.listdir(path) if f.endswith(ext))
    except OSError:
        return []


def scan_skills_dir(path):
    out = []
    for d in list_dirs(path):
        p = os.path.join(path, d, "SKILL.md")
        if os.path.isfile(p):
            e = md_entry(p, "skill")
            if e:
                out.append(e)
    return out


def scan_md_dir(path, kind):
    return [e for e in (md_entry(os.path.join(path, f), kind) for f in list_files(path)) if e]


def hook_entries(hooks_obj, base_dir, source):
    """Flatten a Claude Code hooks object and estimate injected context."""
    out = []
    if not isinstance(hooks_obj, dict):
        return out
    hooks_obj = hooks_obj.get("hooks", hooks_obj)
    for event, groups in hooks_obj.items():
        if not isinstance(groups, list):
            continue
        for g in groups:
            for h in (g.get("hooks") or []) if isinstance(g, dict) else []:
                cmd = h.get("command") or h.get("prompt") or ""
                entry = {
                    "source": source,
                    "event": event,
                    "matcher": g.get("matcher", ""),
                    "type": h.get("type", "command"),
                    "command": cmd[:300],
                }
                if entry["type"] == "prompt":
                    entry["cost_note"] = "LLM judges every time this event fires"
                if event in ("SessionStart", "UserPromptSubmit") and base_dir:
                    entry["injects_estimate"] = estimate_injection(cmd, base_dir)
                out.append(entry)
    return out


def estimate_injection(cmd, base_dir):
    """Find .md files a hook script reads, to estimate injected text size."""
    files = set()
    candidates = [cmd]
    for tok in re.findall(r"[\w${}./\\-]+", cmd):
        tok = tok.replace("${CLAUDE_PLUGIN_ROOT}", base_dir).strip("\"'")
        if os.path.isfile(tok):
            candidates.append(read_text(tok, 200_000) or "")
        elif os.path.isfile(os.path.join(base_dir, tok)):
            candidates.append(read_text(os.path.join(base_dir, tok), 200_000) or "")
    # Hook launchers often dispatch to a sibling script by name.
    hooks_dir = os.path.join(base_dir, "hooks")
    for f in list_files(hooks_dir, ext=""):
        if f in cmd and os.path.isfile(os.path.join(hooks_dir, f)):
            candidates.append(read_text(os.path.join(hooks_dir, f), 200_000) or "")
    for text in candidates:
        for m in re.findall(r"[\w${}./-]+\.md", text or ""):
            rel = re.sub(r"^\$\{?[A-Z_]*\}?/(\.\./)?", "", m)
            p = os.path.normpath(os.path.join(base_dir, rel))
            if os.path.isfile(p):
                files.add(p)
    total = sum(len(read_text(p) or "") for p in files)
    return {
        "files": sorted(files),
        "chars": total,
        "tokens": sum(approx_tokens(read_text(p)) for p in files),
        "note": "estimate from files the hook script references; dynamic output not counted",
    }


# ---------------------------------------------------------------- plugins

def scan_plugin_dir(path, plugin_id, scope="", enabled=None):
    manifest = read_json(os.path.join(path, ".claude-plugin", "plugin.json")) or {}

    def comp_paths(field, default):
        val = manifest.get(field)
        if isinstance(val, str):
            val = [val]
        if isinstance(val, list):
            return [os.path.normpath(os.path.join(path, v)) for v in val if isinstance(v, str)]
        return [os.path.join(path, default)]

    skills, agents, styles, commands = [], [], [], []
    for p in comp_paths("skills", "skills"):
        if os.path.isfile(os.path.join(p, "SKILL.md")):
            e = md_entry(os.path.join(p, "SKILL.md"), "skill")
            skills += [e] if e else []
        else:
            skills += scan_skills_dir(p)
    for p in comp_paths("agents", "agents"):
        agents += scan_md_dir(p, "agent") if os.path.isdir(p) else []
    for p in comp_paths("outputStyles", "output-styles"):
        styles += scan_md_dir(p, "style") if os.path.isdir(p) else []
    for p in comp_paths("commands", "commands"):
        commands += [e["name"] for e in scan_md_dir(p, "command")] if os.path.isdir(p) else []

    hooks = []
    hv = manifest.get("hooks")
    if isinstance(hv, dict):
        hooks += hook_entries(hv, path, plugin_id)
    for hp in ([os.path.join(path, hv)] if isinstance(hv, str) else []) + [os.path.join(path, "hooks", "hooks.json")]:
        if os.path.isfile(hp):
            hooks += hook_entries(read_json(hp) or {}, path, plugin_id)
            break

    mcp = []
    mv = manifest.get("mcpServers")
    if isinstance(mv, dict):
        mcp += list(mv.keys())
    mj = read_json(os.path.join(path, ".mcp.json")) or {}
    mcp += list((mj.get("mcpServers") or {}).keys())

    return {
        "id": "plugin:" + plugin_id,
        "kind": "plugin",
        "name": manifest.get("name") or plugin_id.split("@")[0],
        "plugin_id": plugin_id,
        "scope": scope,
        "enabled": enabled,
        "version": manifest.get("version"),
        "license": manifest.get("license"),
        "path": path,
        "skills": skills,
        "agents": agents,
        "output_styles": styles,
        "commands": commands,
        "hooks": hooks,
        "mcp": sorted(set(mcp)),
    }


def load_settings(paths):
    merged = {"enabledPlugins": {}, "hooks": [], "outputStyle": None, "skillOverrides": {}}
    for scope, p in paths:
        s = read_json(p)
        if not isinstance(s, dict):
            continue
        merged["enabledPlugins"].update(s.get("enabledPlugins") or {})
        merged["skillOverrides"].update(s.get("skillOverrides") or {})
        if s.get("outputStyle"):
            merged["outputStyle"] = s["outputStyle"]
        if s.get("hooks"):
            merged["hooks"] += hook_entries(s["hooks"], os.path.dirname(p), "settings:" + scope)
    return merged


# ---------------------------------------------------------------- env scan

def scan_claude(project):
    pc = os.path.join(project, ".claude")
    settings = load_settings([
        ("user", os.path.join(CLAUDE_HOME, "settings.json")),
        ("project", os.path.join(pc, "settings.json")),
        ("local", os.path.join(pc, "settings.local.json")),
    ])
    items = []

    installed = (read_json(os.path.join(CLAUDE_HOME, "plugins", "installed_plugins.json")) or {}).get("plugins", {})
    for pid, records in installed.items():
        for r in records if isinstance(records, list) else [records]:
            proj = r.get("projectPath")
            if proj and os.path.abspath(proj) != os.path.abspath(project):
                continue
            path = r.get("installPath")
            if path and os.path.isdir(path):
                enabled = settings["enabledPlugins"].get(pid)
                items.append(scan_plugin_dir(path, pid, r.get("scope", ""), enabled))

    for scope, base in (("user", CLAUDE_HOME), ("project", pc)):
        for e in scan_skills_dir(os.path.join(base, "skills")):
            override = settings["skillOverrides"].get(e["name"], "on")
            items.append({"id": f"skill:{scope}:{e['name']}", "kind": "skill", "scope": scope,
                          "name": e["name"], "override": override, "skills": [e]})
        for e in scan_md_dir(os.path.join(base, "agents"), "agent"):
            items.append({"id": f"agent:{scope}:{e['name']}", "kind": "agent", "scope": scope,
                          "name": e["name"], "agents": [e]})
        for e in scan_md_dir(os.path.join(base, "output-styles"), "style"):
            items.append({"id": f"style:{scope}:{e['name']}", "kind": "output-style", "scope": scope,
                          "name": e["name"], "output_styles": [e]})

    mcp = []
    cj = read_json(os.path.join(HOME, ".claude.json")) or {}
    for name in (cj.get("mcpServers") or {}):
        mcp.append({"name": name, "scope": "user"})
    proj_cfg = (cj.get("projects") or {}).get(os.path.abspath(project)) or {}
    for name in (proj_cfg.get("mcpServers") or {}):
        mcp.append({"name": name, "scope": "local"})
    for name in ((read_json(os.path.join(project, ".mcp.json")) or {}).get("mcpServers") or {}):
        mcp.append({"name": name, "scope": "project"})
    for m in mcp:
        items.append({"id": f"mcp:{m['scope']}:{m['name']}", "kind": "mcp", "scope": m["scope"], "name": m["name"]})

    instr = []
    for p in (os.path.join(CLAUDE_HOME, "CLAUDE.md"), os.path.join(project, "CLAUDE.md"),
              os.path.join(pc, "CLAUDE.md"), os.path.join(project, "CLAUDE.local.md")):
        t = read_text(p)
        if t is not None:
            instr.append({"path": p, "chars": len(t), "tokens": approx_tokens(t)})

    return {
        "present": os.path.isdir(CLAUDE_HOME),
        "home": CLAUDE_HOME,
        "settings": {k: settings[k] for k in ("enabledPlugins", "outputStyle", "skillOverrides")},
        "settings_hooks": settings["hooks"],
        "items": items,
        "instruction_files": instr,
    }


def scan_codex(project):
    items = []
    for scope, base in (("user", os.path.join(CODEX_HOME, "skills")),
                        ("project", os.path.join(project, ".codex", "skills")),
                        ("shared", os.path.join(project, ".agents", "skills"))):
        for e in scan_skills_dir(base):
            items.append({"id": f"codex-skill:{scope}:{e['name']}", "kind": "skill", "runtime": "codex",
                          "scope": scope, "name": e["name"], "skills": [e]})
    for scope, base in (("user", os.path.join(CODEX_HOME, "agents")),
                        ("project", os.path.join(project, ".codex", "agents"))):
        for f in list_files(base, ext=""):
            items.append({"id": f"codex-agent:{scope}:{f}", "kind": "agent", "runtime": "codex",
                          "scope": scope, "name": os.path.splitext(f)[0]})
    cfg = read_text(os.path.join(CODEX_HOME, "config.toml")) or ""
    for name in re.findall(r"^\[mcp_servers\.([A-Za-z0-9_.-]+)\]", cfg, re.M):
        items.append({"id": f"codex-mcp:user:{name}", "kind": "mcp", "runtime": "codex", "scope": "user", "name": name})
    instr = []
    for p in (os.path.join(CODEX_HOME, "AGENTS.md"), os.path.join(project, "AGENTS.md")):
        t = read_text(p)
        if t is not None:
            instr.append({"path": p, "chars": len(t), "tokens": approx_tokens(t)})
    return {"present": os.path.isdir(CODEX_HOME), "home": CODEX_HOME, "items": items, "instruction_files": instr}


def scan_harness(project):
    pc = os.path.join(project, ".claude")
    agents = [e["name"] for e in scan_md_dir(os.path.join(pc, "agents"), "agent")]
    skills = [e["name"] for e in scan_skills_dir(os.path.join(pc, "skills"))]
    claude_md = read_text(os.path.join(project, "CLAUDE.md")) or ""
    m = re.search(r"^##\s*하네스[:：]?\s*(.+)$|^##\s*Harness[:：]?\s*(.+)$", claude_md, re.M)
    lock_path = os.path.join(pc, "harnesskit.lock")
    return {
        "exists": bool(agents or skills or m),
        "agents": agents,
        "skills": skills,
        "claude_md_section": (m.group(1) or m.group(2)).strip() if m else None,
        "workspace": os.path.isdir(os.path.join(project, "_workspace")),
        "lock": lock_path if os.path.isfile(lock_path) else None,
        "v1_artifacts": bool(re.search(r"TeamCreate|TeamDelete|CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
                                       " ".join(read_text(os.path.join(pc, "skills", s, "SKILL.md")) or "" for s in skills))),
    }


def always_on_summary(claude):
    """What is paid on every session, before any skill is used."""
    rows = []
    active_style = (claude["settings"].get("outputStyle") or "").lower()
    for it in claude["items"]:
        if it.get("enabled") is False:
            continue
        if it.get("override") in ("off", "user-invocable-only"):
            continue
        chars = tokens = 0
        for s in it.get("skills", []):
            if s.get("disable_model_invocation"):
                continue
            if it.get("override") == "name-only":
                chars += len(s["name"])
                tokens += approx_tokens(s["name"])
            else:
                chars += s["always_on_chars"]
                tokens += s["always_on_tokens"]
        chars += sum(a["always_on_chars"] for a in it.get("agents", []))
        tokens += sum(a["always_on_tokens"] for a in it.get("agents", []))
        hook_chars = sum((h.get("injects_estimate") or {}).get("chars", 0) for h in it.get("hooks", []))
        tokens += sum((h.get("injects_estimate") or {}).get("tokens", 0) for h in it.get("hooks", []))
        style_chars = 0
        for s in it.get("output_styles", []):
            if active_style and (s["name"].lower() == active_style
                                 or os.path.basename(s["path"]).lower().startswith(active_style)):
                style_chars += s["body_chars"]
                tokens += approx_tokens(read_text(s["path"]))
        if chars or hook_chars or style_chars:
            rows.append({"id": it["id"], "listing_chars": chars, "hook_injection_chars": hook_chars,
                         "output_style_chars": style_chars, "approx_tokens": tokens,
                         "prompt_hooks": sum(1 for h in it.get("hooks", []) if h.get("type") == "prompt")})
    rows.sort(key=lambda r: -(r["listing_chars"] + r["hook_injection_chars"] + r["output_style_chars"]))
    instr = sum(f["chars"] for f in claude["instruction_files"])
    return {"by_item": rows, "instruction_file_chars": instr,
            "note": "approx_tokens is a rough estimate (~4 ASCII or ~1.5 other chars per token); `claude plugin details <name>` gives Claude Code's own projection for plugins"}


def scan_env(project):
    project = os.path.abspath(project)
    claude = scan_claude(project)
    return {
        "mode": "env",
        "project": project,
        "claude": claude,
        "codex": scan_codex(project),
        "harness": scan_harness(project),
        "always_on": always_on_summary(claude),
    }


# ---------------------------------------------------------------- repo scan

def scan_repo(path):
    """Scan a candidate repository that has not been installed."""
    path = os.path.abspath(path)
    items = []
    mk = read_json(os.path.join(path, ".claude-plugin", "marketplace.json"))
    seen = set()
    if isinstance(mk, dict):
        mname = mk.get("name", "")
        for p in mk.get("plugins", []):
            src = p.get("source")
            if isinstance(src, str):
                pdir = os.path.normpath(os.path.join(path, src))
                if os.path.isdir(pdir) and pdir not in seen:
                    seen.add(pdir)
                    items.append(scan_plugin_dir(pdir, f"{p.get('name')}@{mname}", "candidate"))
            else:
                items.append({"id": f"plugin:{p.get('name')}@{mname}", "kind": "plugin", "name": p.get("name"),
                              "note": "remote source, not scanned", "source": src})
    if os.path.isfile(os.path.join(path, ".claude-plugin", "plugin.json")) and path not in seen:
        items.append(scan_plugin_dir(path, os.path.basename(path), "candidate"))
    if not items:
        if os.path.isfile(os.path.join(path, "SKILL.md")):
            e = md_entry(os.path.join(path, "SKILL.md"), "skill")
            items.append({"id": "skill:candidate:" + e["name"], "kind": "skill", "name": e["name"], "skills": [e]})
        for base in ("skills", os.path.join(".claude", "skills"), os.path.join(".agents", "skills")):
            for e in scan_skills_dir(os.path.join(path, base)):
                items.append({"id": "skill:candidate:" + e["name"], "kind": "skill", "name": e["name"], "skills": [e]})
    lic = None
    for f in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        t = read_text(os.path.join(path, f), 400)
        if t:
            lic = " ".join(t.split())[:80]
            break
    return {"mode": "repo", "path": path, "license_head": lic, "items": items}


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("env", help="scan the installed environment")
    e.add_argument("--project", default=os.getcwd())
    e.add_argument("--out")
    r = sub.add_parser("repo", help="scan a candidate repository")
    r.add_argument("path")
    r.add_argument("--out")
    a = ap.parse_args(argv)
    result = scan_env(a.project) if a.cmd == "env" else scan_repo(a.path)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(a.out)
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
