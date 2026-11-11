# 설치 전 점검, 설치, 기록

build 5·7단계, check·sync 모드가 함께 쓰는 규칙이다. 설치할 일이 있을 때만 읽는다.

## 설치 전 점검과 설치

고른 도구 중 아직 설치되지 않은 것마다 아래를 차례로 한다.
1. **받기**: 새로 만든 빈 임시 폴더에 `git clone --depth 1 <저장소>`. 받은 코드는 실행하지 않는다.
2. **보안 점검(필수)**: `hkinspect.py <폴더> [--plugin <이름>]`. 판정에 따라 처리한다.
   - `SAFE`: 다음 단계로 간다.
   - `CAUTION`: 걸린 항목(파일:줄)을 보여 주고, 사용자가 진행을 고를 때만 간다.
   - `DO_NOT_INSTALL`: 설치하지 않는다. 사용자가 근거를 본 뒤 위험을 감수한다고 분명히 말한 경우에만 설치하고, 그 결정을 lock의 `decisions`에 남긴다.
   - `missing`(SkillSpector 없음): 출력의 설치 명령으로 SkillSpector부터 설치할지 묻는다. 설치하지 못하면 외부 도구는 설치하지 않는다.
3. **기능 충돌 체크**: `hkscan.py repo <폴더> --out ... --summary`와 `hkcheck.py --env ... --candidate-scan ... --md`(카탈로그 도구는 `--candidate <id>`)로 설치된 것과 부딪히는지 본다. `review` 항목은 `conflict-rules.md`로 판정한다.
4. **CLI로 설치하는 도구**(Spec Kit의 `specify init`, BMAD 설치기처럼 프로젝트에 스킬·명령을 만들어 주는 것): SkillSpector는 스킬 점검용이라 CLI 저장소 전체를 넣으면 판정이 부풀려진다. 설치 전에는 저장소 점검 결과를 참고로 보여 주고, 설치한 뒤 생성된 폴더(예: `.claude/skills/speckit-*`)를 `hkinspect.py`로 다시 점검해 통과해야 쓴다.
5. **설치**: 두 점검 결과를 한 표로 보여 주고 승인받은 것만 설치한다. **설치 범위는 기본이 이 프로젝트**다(아래 표). 전역 설치는 사용자가 요청할 때만 한다. 카탈로그 설치 명령은 전역 기준으로 적힌 것이 많으니 표대로 바꿔 실행하고, `verified: survey`면 README로 명령을 한 번 확인한다. `/plugin ...` 같은 슬래시 명령은 사용자에게 입력을 부탁한다. 설치 후 다시 스캔하고, 실패한 도구는 다시 시도하지 않고 `skipped`로 기록한다.

| 종류 | 프로젝트 범위 (기본) | 나만 쓰기 | 전역 (요청할 때만) |
|---|---|---|---|
| 스킬 폴더 (Claude Code) | `<프로젝트>/.claude/skills/<이름>/` | 같은 위치 + `.gitignore` | `~/.claude/skills/<이름>/` |
| 스킬 폴더 (Codex) | `<프로젝트>/.agents/skills/<이름>/` | 같은 위치 + `.gitignore` | `~/.codex/skills/<이름>/` |
| 플러그인 (Claude Code) | `claude plugin marketplace add <저장소> --scope project` 후 `claude plugin install <이름>@<마켓> --scope project` | `--scope local` | `--scope user` |
| MCP (Claude Code) | `claude mcp add --scope project ...` (`.mcp.json`) | `--scope local` | `--scope user` |
| Codex 플러그인·MCP | 프로젝트 범위를 확인하지 못했다. 사용자 범위로 설치하고 그렇다고 알린다 | | |
| CLI (`uv tool`, `npx`) | 기계 단위 도구다. `npx`는 버전을 고정해 필요할 때만 실행한다 | | |

프로젝트 범위는 설정이 `.claude/settings.json`·`.mcp.json`·프로젝트 스킬 폴더에 남아 git으로 팀과 공유된다. 상시 비용이 그 프로젝트에서만 들고, 다른 프로젝트의 스킬과 부딪히지 않는다.

## 기록

`_workspace/harnesskit/lock-data.json`을 아래처럼 쓰고 `hklock.py write --project . --data _workspace/harnesskit/lock-data.json`을 실행한다. 도구마다 설치 범위(`scope`)를 적는다.

```json
{
  "runtimes": ["claude"],
  "tools": [
    {"id": "im-not-ai", "status": "use", "scope": "user", "why": "보고서 문장 다듬기 (이미 전역에 설치돼 있음)"},
    {"id": "design-qa", "status": "use", "scope": "project", "why": "디자인 QA 출시 기준"},
    {"id": "superpowers", "status": "disabled", "why": "오케스트레이터와 작업 절차 자리 경쟁"}
  ],
  "decisions": [{"finding": "superpowers vs harnesskit (slot)", "choice": "이 프로젝트에서 superpowers 끔"}],
  "harness": {"orchestrator": "<오케스트레이터 스킬명>", "agents": ["..."], "skills": ["..."]}
}
```

