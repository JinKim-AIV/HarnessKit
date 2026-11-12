#!/usr/bin/env python3
"""HarnessKit 토큰 장부: 세션 기록에서 실제 사용량을 구간별로 모으고, 길어지면 새 세션을 권한다.

  hktokens.py mark "<RUN> <단계>" [--cap 에이전트=N ...] [--at ISO시각]
      구간 시작을 표시한다. 구간 이름의 첫 단어가 실행 구분(RUN)이다.
      --cap 은 이 구간에서 부를 에이전트의 도구 호출 상한(장부에서 비교).
      표시한 뒤 check 와 같은 점검을 하고, 알릴 것이 있을 때만 한 줄씩 출력한다.
  hktokens.py report [--run RUN]
      장부 폴더에 ledger.md 를 쓰고 RUN(기본: 마지막 실행)의 요약 몇 줄만 출력한다.
  hktokens.py check
      세션을 연 폴더와 대화 크기를 점검한다. 알릴 것이 없으면 아무것도 출력하지 않는다.
  hktokens.py size GLOB... [--limit 20000]
      인계 파일 크기를 본다. 상한을 넘은 파일이 있으면 종료 코드 1.

공통 옵션(하위 명령 뒤에 쓴다):
  --project DIR      하네스 프로젝트 폴더(기본: 현재 폴더). 세션 기록 위치를 정한다.
  --dir D            장부 폴더(기본: ./_workspace/tokens).
  --runtime R        claude(기본) | codex. Codex 기록은 읽지 않고 토큰을 '측정 안 됨'으로 적는다.
  --max-context N    대화 크기 기준(기본 200000, 추정값).
  --max-run N        실행 누계 기준(기본 30000000, 추정값).

- 숫자는 Claude Code 세션 기록(<설정 폴더>/projects/<경로>/*.jsonl, */subagents/*.jsonl)의
  message.usage 값의 합이다. 추정치가 아니다. 한 응답이 여러 줄로 기록되므로 message.id로 한 번만 센다.
- mark 는 환경 변수 CLAUDE_CODE_SESSION_ID(있을 때)로 표시한 세션을 함께 적는다. report 는 실행마다
  표시를 남긴 세션의 기록만 센다. 그래서 같은 폴더의 다른 세션이 섞이지 않고, 세션을 다른 폴더에서
  열었어도 기록을 찾아간다. 세션 id가 없으면 --project 폴더의 모든 세션을 센다.
- 도구 호출 수는 기록에 남은 tool_use 개수다. 에이전트 이름은 subagents/*.meta.json 의 agentType.
- 읽는 것은 사용량 숫자, 모델, 시각, 도구 호출 수, 세션을 연 폴더, 에이전트 이름·설명뿐이다.
  대화 내용은 옮기지 않는다. 네트워크 통신은 하지 않는다.
- 첫 표시 이전 사용량은 세지 않는다. 한 실행의 마지막 표시 뒤 기록은 다음 표시 전까지 그 구간에 들어간다.

Standard library only.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hkscan  # noqa: E402

FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
HEAD = ("입력", "캐시 쓰기", "캐시 읽기", "출력")
MAIN, SUB = "메인", "서브에이전트"
RECENT = dt.timedelta(minutes=30)  # 세션 id가 없을 때, 지금 세션이 이 폴더에 기록 중이라고 볼 시간 폭
UTC = dt.timezone.utc


# ---------------------------------------------------------------- 시각·숫자

def parse_t(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def now():
    return dt.datetime.now(UTC)


def big(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def span(sec):
    m = int(round(max(sec, 0) / 60))
    return f"{m // 60}시간 {m % 60}분" if m >= 60 else f"{m}분"


# ---------------------------------------------------------------- 세션 기록 위치

def projects_root():
    return os.path.join(hkscan.CLAUDE_HOME, "projects")


def log_dir(project):
    return os.path.join(projects_root(), re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(project)))


def folder_files(base):
    """한 기록 폴더의 모든 세션: [(파일, 주체, 세션 id)]."""
    out = [(f, SUB, os.path.basename(os.path.dirname(os.path.dirname(f))))
           for f in glob.glob(os.path.join(base, "*", "subagents", "*.jsonl"))]
    out += [(f, MAIN, os.path.basename(f)[:-len(".jsonl")]) for f in glob.glob(os.path.join(base, "*.jsonl"))]
    return out


def session_files(sid):
    """세션 id로 어느 폴더에 있든 그 세션과 서브에이전트 기록을 찾는다."""
    root = glob.escape(projects_root())
    out = [(f, SUB, sid) for f in glob.glob(os.path.join(root, "*", glob.escape(sid), "subagents", "*.jsonl"))]
    out += [(f, MAIN, sid) for f in glob.glob(os.path.join(root, "*", glob.escape(sid) + ".jsonl"))]
    return out


def opened_in(path):
    """세션을 연 폴더(기록 첫 cwd)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 200:
                    break
                if '"cwd"' in line:
                    try:
                        return json.loads(line).get("cwd")
                    except ValueError:
                        continue
    except OSError:
        pass
    return None


def _meta(path):
    try:
        with open(path[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
            m = json.load(f)
        return m.get("agentType") or "?", m.get("description") or ""
    except (OSError, ValueError):
        return "?", ""


def responses(files, since=None):
    """세션 기록의 응답을 message.id 하나에 한 번씩 돌려준다(시각 순).

    since 가 있으면 그 뒤에 수정된 파일만 읽는다(큰 기록 폴더를 매번 다 읽지 않기 위해).
    서브에이전트 파일을 먼저 읽어, 옛 형식처럼 메인 파일에 같은 응답이 섞여 있어도 한 번만 센다.
    """
    seen, out = set(), []
    for path, who, sid in sorted(set(files), key=lambda x: x[1] != SUB):
        try:
            if since and dt.datetime.fromtimestamp(os.path.getmtime(path), UTC) < since:
                continue
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        agent, desc = _meta(path) if who == SUB else (None, "")
        msgs = {}
        with fh:
            for line in fh:
                if '"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") != "assistant":
                    continue
                m = d.get("message") or {}
                key = m.get("id") or d.get("requestId")
                if not key or key in seen:
                    continue
                r = msgs.get(key)
                if r is None:
                    t = parse_t(d.get("timestamp"))
                    if t is None:
                        continue
                    side = who == MAIN and d.get("isSidechain") is True  # 옛 형식: 서브에이전트가 메인 파일에 섞임
                    r = msgs[key] = {"t": t, "who": SUB if side else who, "agent": "?" if side else agent,
                                     "desc": desc, "file": path, "sid": sid, "dir": os.path.dirname(path) if who == MAIN
                                     else os.path.dirname(os.path.dirname(os.path.dirname(path))),
                                     "model": m.get("model") or "?", "usage": m.get("usage") or {}, "tools": set()}
                elif not r["usage"] and m.get("usage"):
                    r["usage"] = m["usage"]
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        r["tools"].add(c.get("id") or len(r["tools"]))
        for key, r in msgs.items():
            seen.add(key)
            if r["model"] == "<synthetic>":  # API 호출이 아니다
                continue
            r["tok"] = {k: int(r["usage"].get(k) or 0) for k in FIELDS}
            out.append(r)
    out.sort(key=lambda r: r["t"])
    return out


def context(r):
    """그 응답을 만들 때 모델이 읽은 대화 크기(입력 + 캐시 쓰기 + 캐시 읽기)."""
    u = r["tok"]
    return u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]


def wrong_folder(project, sid):
    """세션을 프로젝트 밖에서 열었으면 경고 문장, 아니면 빈 문자열."""
    mains = [f for f, who, _ in session_files(sid) if who == MAIN]
    if not mains or os.path.dirname(mains[0]) == log_dir(project):
        return ""
    where = opened_in(mains[0]) or os.path.dirname(mains[0])
    return (f"세션을 프로젝트 폴더({os.path.abspath(project)})가 아닌 {where} 에서 열었습니다."
            " 프로젝트 에이전트·스킬이 등록되지 않았을 수 있습니다. 장부는 세션 id로 기록을 찾아 집계합니다."
            " 다음 실행은 프로젝트 폴더에서 세션을 여세요.")


def ancestor_hint(project, since):
    """세션 id가 없을 때: 상위 폴더에서 연 세션이 이 시각 뒤에 기록을 남겼으면 그 폴더를 알려 준다."""
    p = os.path.abspath(project)
    while os.path.dirname(p) != p:
        p = os.path.dirname(p)
        if any(r["who"] == MAIN and r["t"] >= since for r in responses(folder_files(log_dir(p)), since)):
            return (f" 상위 폴더 {p} 에서 연 세션의 기록이 있습니다. --project {p} 로 집계할 수 있지만 그 폴더의"
                    " 다른 세션도 섞입니다. 다음 실행은 프로젝트 폴더에서 세션을 여세요.")
    return ""


# ---------------------------------------------------------------- 표시

def load_marks(d):
    path = os.path.join(d, "marks.jsonl")
    if not os.path.exists(path):
        return []
    marks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            m = json.loads(line)
            m["dt"] = parse_t(m.get("t"))
            m.setdefault("run", m["label"].split()[0] if m.get("label") else "?")
            m.setdefault("caps", {})
            if m["dt"]:
                marks.append(m)
    return sorted(marks, key=lambda m: m["dt"])


def parse_caps(items):
    caps = {}
    for it in items or []:
        name, _, n = it.partition("=")
        if not name.strip() or not n.strip().isdigit():
            sys.exit(f"--cap 형식은 에이전트=숫자 입니다: {it}")
        caps[name.strip()] = int(n)
    return caps


# ---------------------------------------------------------------- 점검 (mark·check)

def signals(a, marks, ref, first_mark=False):
    if a.runtime == "codex":
        return []
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    run = marks[-1]["run"] if marks else None
    start = min((m["dt"] for m in marks if m["run"] == run), default=ref)
    since = min(start, ref - RECENT)
    out = []
    if sid and session_files(sid):
        if first_mark:  # 폴더 경고는 실행의 첫 표시와 check 에서만(매 단계 반복하지 않는다)
            w = wrong_folder(a.project, sid)
            if w:
                out.append("[토큰] " + w)
        sids = {m.get("session") for m in marks if m["run"] == run and m.get("session")} | {sid}
        files = [x for s in sids for x in session_files(s)]
        recs = responses(files, since)
        mine = [r for r in recs if r["who"] == MAIN and r["sid"] == sid]
    else:
        recs = responses(folder_files(log_dir(a.project)), since)
        mine = [r for r in recs if r["who"] == MAIN and r["t"] >= ref - RECENT]
        if not mine:  # 부른 응답은 실행 전에 이미 기록되므로, 이 폴더에서 연 세션이면 최근 기록이 있다
            return [f"[토큰] 최근 이 폴더의 세션 기록이 없습니다({log_dir(a.project)})."
                    " 세션을 프로젝트 폴더에서 열었는지 확인하세요." + ancestor_hint(a.project, ref - RECENT)]
    if not mine:
        return out
    ctx = context(max(mine, key=lambda r: r["t"]))
    total = sum(sum(r["tok"].values()) for r in recs if r["t"] >= start) if marks else 0
    over = []
    if ctx > a.max_context:
        over.append(f"대화 크기 {big(ctx)} (기준 {big(a.max_context)})")
    if total > a.max_run:
        over.append(f"이번 실행 누계 {big(total)} (기준 {big(a.max_run)})")
    if over:
        out.append("[토큰] " + " · ".join(over) + " — 기준은 추정값입니다. 지금 단계까지 _workspace/에 남기고,"
                   " 새 세션에서 이어 할지 사용자에게 한 줄로 제안하세요.")
    return out


def cmd_mark(a):
    os.makedirs(a.dir, exist_ok=True)
    t = parse_t(a.at) if a.at else now()
    if t is None:
        sys.exit(f"--at 시각을 읽지 못했습니다: {a.at}")
    run = a.label.split()[0] if a.label.strip() else sys.exit("구간 이름이 비었습니다")
    first = not any(m["run"] == run for m in load_marks(a.dir))
    rec = {"t": iso(t), "label": a.label, "run": run, "caps": parse_caps(a.cap)}
    if os.environ.get("CLAUDE_CODE_SESSION_ID"):
        rec["session"] = os.environ["CLAUDE_CODE_SESSION_ID"]
    with open(os.path.join(a.dir, "marks.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for line in signals(a, load_marks(a.dir), t, first_mark=first):
        print(line)


def cmd_check(a):
    for line in signals(a, load_marks(a.dir), now(), first_mark=True):
        print(line)


# ---------------------------------------------------------------- 장부

def segment_of(marks, t):
    i = None
    for k, m in enumerate(marks):
        if m["dt"] > t:
            break
        i = k
    return i


def cmd_report(a):
    marks = load_marks(a.dir)
    if not marks:
        sys.exit(f"표시가 없습니다: {os.path.join(a.dir, 'marks.jsonl')}. 먼저 mark 로 단계 시작을 표시합니다.")
    runs = list(dict.fromkeys(m["run"] for m in marks))
    focus = a.run or marks[-1]["run"]
    if focus not in runs:
        sys.exit(f"실행 {focus} 의 표시가 없습니다. 있는 실행: {', '.join(runs)}")
    base = log_dir(a.project)
    ledger = os.path.join(a.dir, "ledger.md")
    head = ["# 토큰 장부", "", f"집계 시각: {iso(now())}"]

    if a.runtime == "codex":
        head.append("토큰: **측정 안 됨** — Codex 세션 기록은 HarnessKit이 아직 읽지 않습니다. 구간 시각만 남깁니다.")
        out = head + ["", "| 구간 | 시작 | 걸린 시간 |", "|---|---|---:|"]
        for k, m in enumerate(marks):
            nxt = marks[k + 1]["dt"] if k + 1 < len(marks) else now()
            out.append(f"| {m['label']} | {m['t']} | {span((nxt - m['dt']).total_seconds())} |")
        write_ledger(a.dir, out)
        n = sum(1 for m in marks if m["run"] == focus)
        print(f"장부: {ledger}\n{focus} 토큰: 측정 안 됨(Codex) · 구간 {n}개")
        return

    by_run = {run: {m["session"] for m in marks if m["run"] == run and m.get("session")} for run in runs}
    files = folder_files(base) + [x for s in set().union(*by_run.values()) for x in session_files(s)]
    seg, last_t, agents, skipped = {}, {}, {}, 0
    for r in responses(files, marks[0]["dt"]):
        if r["t"] < marks[0]["dt"]:
            continue
        i = segment_of(marks, r["t"])
        sids = by_run[marks[i]["run"]]
        # 실행 표시를 남긴 세션만 센다. 세션 id가 없던 실행은 이 폴더의 기록만 센다
        if (r["sid"] not in sids) if sids else (r["dir"] != base):
            skipped += 1
            continue
        b = seg.setdefault((i, r["who"], r["model"]), dict.fromkeys(FIELDS + ("n", "tools"), 0))
        for k in FIELDS:
            b[k] += r["tok"][k]
        b["n"] += 1
        b["tools"] += len(r["tools"])
        last_t[i] = max(last_t.get(i, r["t"]), r["t"])
        if r["who"] == SUB:
            # 서브에이전트 기록 파일 하나 = 에이전트 실행 하나. 옛 형식(메인 파일에 섞임)은 구간별로 묶는다
            key = r["file"] if os.sep + "subagents" + os.sep in r["file"] else (r["file"], i)
            g = agents.setdefault(key, {"seg": i, "agent": r["agent"], "desc": r["desc"], "n": 0, "tools": 0})
            g["n"] += 1
            g["tools"] += len(r["tools"])

    out = head + [f"출처: 세션 기록 usage 값의 합(추정치 아님) · 기록 폴더: {base}",
                  "실행마다 표시를 남긴 세션의 기록만 셉니다(세션 id가 없던 실행은 이 폴더의 모든 세션)."
                  + (f" 다른 세션의 응답 {skipped}개는 빼었습니다." if skipped else "")]

    # 실행별 합계
    out += ["", "## 실행별 합계", "", "| 실행 | 메인 | 서브에이전트 | 합계 | 응답 | 걸린 시간 |",
            "|---|---:|---:|---:|---:|---:|"]
    totals = {}
    for run in runs:
        idx = [k for k, m in enumerate(marks) if m["run"] == run]
        t = {MAIN: 0, SUB: 0, "n": 0}
        for (i, who, _), b in seg.items():
            if i in idx:
                t[who] += sum(b[k] for k in FIELDS)
                t["n"] += b["n"]
        end = max([last_t[i] for i in idx if i in last_t] or [marks[idx[0]]["dt"]])
        t["took"] = span((end - marks[idx[0]]["dt"]).total_seconds())
        totals[run] = t
        out.append(f"| {run} | {t[MAIN]:,} | {t[SUB]:,} | **{t[MAIN] + t[SUB]:,}** | {t['n']} | {t['took']} |")

    # 구간별
    out += ["", "## 구간별", "",
            "| 구간 | 주체 | 모델 | 응답 | 도구 호출 | " + " | ".join(HEAD) + " | 합계 | 걸린 시간 |",
            "|---|---|---|---:|---:|" + "---:|" * (len(HEAD) + 2)]
    for (i, who, model), b in sorted(seg.items(), key=lambda kv: (kv[0][0], kv[0][1] != MAIN, kv[0][2])):
        took = span(((last_t.get(i) or marks[i]["dt"]) - marks[i]["dt"]).total_seconds())
        out.append(f"| {marks[i]['label']} | {who} | {model} | {b['n']} | {b['tools']} | "
                   + " | ".join(f"{b[k]:,}" for k in FIELDS) + f" | {sum(b[k] for k in FIELDS):,} | {took} |")

    # 에이전트별 상한 비교
    out += ["", "## 에이전트별 도구 호출 (상한 비교)", "",
            "| 구간 | 에이전트 · 맡은 일 | 응답 / 도구 호출 | 상한 · 판정 |", "|---|---|---:|---|"]
    over, nocap = [], []
    for g in sorted(agents.values(), key=lambda g: (g["seg"], g["agent"])):
        cap = marks[g["seg"]]["caps"].get(g["agent"])
        if cap is None:
            verdict = "상한 없음"
            nocap.append(g)
        elif g["tools"] > cap:
            verdict = f"{cap} · **넘음**"
            over.append((g, cap))
        else:
            verdict = f"{cap} · ✓"
        desc = (g["desc"][:40] + "…") if len(g["desc"]) > 40 else g["desc"]
        out.append(f"| {marks[g['seg']]['label']} | {g['agent']}{' · ' + desc if desc else ''} | "
                   f"{g['n']} / {g['tools']} | {verdict} |")
    if not agents:
        out.append("| — | 서브에이전트 기록 없음 | — | — |")

    # 경고
    warn = {}
    first = {}
    for m in marks:
        first.setdefault(m["run"], m["dt"])
    for run in runs:
        ws = [wrong_folder(a.project, s) for s in sorted(by_run[run])]
        ws = [w for w in ws if w]
        if totals[run]["n"] == 0:
            ws.append("표시 뒤 세션 기록이 없습니다. 세션을 프로젝트 폴더에서 열었는지 확인하세요."
                      + ("" if by_run[run] else ancestor_hint(a.project, first[run])))
        if ws:
            warn[run] = ws
    out += ["", "## 경고", ""] + ([f"- {run}: {w}" for run, ws in warn.items() for w in ws] or ["- 없음"])
    out += ["", "## 구간 시작 시각", ""]
    for m in marks:
        extra = [f"세션 {m['session'][:8]}"] if m.get("session") else []
        extra += [", ".join(f"{k}={v}" for k, v in m["caps"].items())] if m["caps"] else []
        out.append(f"- {m['t']} {m['label']}" + (f" ({' · '.join(extra)})" if extra else ""))
    write_ledger(a.dir, out)

    # 화면 요약: 지금 실행만 몇 줄
    t = totals[focus]
    idx = {k for k, m in enumerate(marks) if m["run"] == focus}
    by_seg = {}
    for (i, _, _), b in seg.items():
        if i in idx:
            by_seg[i] = by_seg.get(i, 0) + sum(b[k] for k in FIELDS)
    top = sorted(by_seg.items(), key=lambda kv: -kv[1])[:3]
    lines = [f"장부: {ledger}",
             f"{focus} 합계 {big(t[MAIN] + t[SUB])} (메인 {big(t[MAIN])} · 서브에이전트 {big(t[SUB])})"
             f" · 응답 {t['n']} · 걸린 시간 {t['took']}"]
    if top:
        lines.append("큰 구간: " + ", ".join(f"{marks[i]['label'].split(None, 1)[-1]} {big(v)}" for i, v in top))
    o = [f"{g['agent']} {g['tools']}/{c}" for g, c in over if g["seg"] in idx]
    if o:
        lines.append("상한 넘음: " + ", ".join(o))
    n = sorted({g["agent"] for g in nocap if g["seg"] in idx})
    if n:
        lines.append("상한 없음: " + ", ".join(n))
    lines += [f"경고: {w}" for w in warn.get(focus, [])]
    print("\n".join(lines))


def write_ledger(d, lines):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "ledger.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- 인계 파일 크기

def approx(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return hkscan.approx_tokens(f.read())
    except OSError:
        return 0


def cmd_size(a):
    files, empty = [], []
    for pat in a.globs:
        hit = sorted(p for p in glob.glob(pat, recursive=True) if os.path.isfile(p))
        files += hit
        if not hit:
            empty.append(pat)
    files = list(dict.fromkeys(files))
    over = [p for p in files if os.path.getsize(p) > a.limit]
    if files:
        top = max(files, key=os.path.getsize)
        print(f"인계 파일 {len(files)}개 · 가장 큰 것 {top} {os.path.getsize(top):,}B"
              f" (추정 {big(approx(top))} 토큰) · 상한 {a.limit:,}B {'✗' if over else '✓'}")
    for p in over:
        print(f"  넘음: {p} {os.path.getsize(p):,}B (추정 {big(approx(p))} 토큰) — 목차와 조각 파일로 나눕니다")
    if empty:
        print("맞는 파일 없음: " + ", ".join(empty))
    sys.exit(1 if over else 0)


# ---------------------------------------------------------------- main

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=".")
    common.add_argument("--dir", default=os.path.join("_workspace", "tokens"))
    common.add_argument("--runtime", choices=("claude", "codex"), default="claude")
    common.add_argument("--max-context", type=int, default=200_000)
    common.add_argument("--max-run", type=int, default=30_000_000)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("mark", parents=[common])
    mk.add_argument("label")
    mk.add_argument("--cap", action="append", metavar="에이전트=N")
    mk.add_argument("--at")
    rp = sub.add_parser("report", parents=[common])
    rp.add_argument("--run")
    sub.add_parser("check", parents=[common])
    sz = sub.add_parser("size", parents=[common])
    sz.add_argument("globs", nargs="+")
    sz.add_argument("--limit", type=int, default=20_000)
    a = ap.parse_args(argv)
    {"mark": cmd_mark, "report": cmd_report, "check": cmd_check, "size": cmd_size}[a.cmd](a)


if __name__ == "__main__":
    main()
