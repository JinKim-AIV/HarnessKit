# Codex 출력 형식

Codex용 하네스를 만들 때 읽는다. Harness v2 절차는 Claude Code의 멀티에이전트 기능을 전제로 하므로, Codex에서는 결과물 위치와 실행 방식을 바꾼다. Codex 기능은 버전과 설정에 따라 다르다. **확인하지 않은 기능을 약속하지 않는다.**

## 1. 파일 위치

| 구성 | Claude Code | Codex |
|---|---|---|
| 에이전트 정의 | `.claude/agents/<name>.md` (YAML 머리말 + 본문) | `.codex/agents/<name>.toml` |
| 스킬 | `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` (형식 동일) |
| 상시 안내 | `CLAUDE.md` | `AGENTS.md` |
| 사용자 스킬 | `~/.claude/skills/` | `~/.codex/skills/` |
| MCP 설정 | `.mcp.json`, `~/.claude.json` | `~/.codex/config.toml`의 `[mcp_servers.<name>]` |

Codex 에이전트 정의 예시:

```toml
name = "requirements-analyst"
description = "요구사항 문서에서 테스트 항목과 경계 조건을 뽑는다. 코드 수정 작업에는 쓰지 않는다."
developer_instructions = '''
역할: 요구사항 분석가.
입력: _workspace/00_input/ 의 요구사항 문서.
출력: _workspace/01_analyst_test-items.md (정상·경계·예외 표).
규칙: 원문에 없는 요구사항을 만들지 않는다. 불명확한 항목은 '확인 필요'로 표시한다.
사용 스킬: humanize-korean (보고서 문장 다듬기, 사실 확인에는 쓰지 않음)
다시 위임하지 않는다. 실패하면 실패한 작업과 남은 불확실성을 그대로 보고한다.
'''
# model 은 기본적으로 상위 작업에서 상속한다. 측정된 이유가 있을 때만 지정한다.
```

## 2. 실행 방식 대체

| Claude Code 기능 | Codex 대체 |
|---|---|
| `Workflow` 스크립트 (`pipeline`, `parallel`, `schema`) | 메인 에이전트가 단계를 순서대로 실행한다. 단계 결과는 `_workspace/{phase}_{role}_{artifact}` 파일로 넘긴다. 스키마는 결과 파일 안의 JSON으로 대신하고 다음 단계 전에 필수 필드를 확인한다. |
| `Agent(name)` + `SendMessage` (지속형 협업) | 메인 에이전트가 중계한다. 역할 A의 결과를 요약해 역할 B에 넘기고, 피드백 왕복 횟수에 상한(기본 2회)을 둔다. |
| 서브에이전트 병렬 위임 | Codex에서 사용자 정의 에이전트(`.codex/agents/`)를 부를 수 있으면 쓴다. 확인할 수 없으면 순차 실행으로 낮추고 사용자에게 알린다. |
| `TaskCreate`/`TaskUpdate` 공유 작업 목록 | `_workspace/tasks.md` 체크리스트. |
| 에이전트별 모델 티어 (fable/opus/sonnet) | 기본은 상속. 원래 티어는 toml 주석으로 남긴다. |
| `AskUserQuestion` | 번호 목록으로 묻는다. 추천안을 1번에 둔다. |

## 3. 규칙

- 병렬로 파일을 고치게 하려면 역할마다 쓰기 범위를 겹치지 않게 나눈다. 나눌 수 없으면 순차로 실행한다.
- 실패하거나 건너뛴 단계는 최종 보고에 남긴다. 성공처럼 보이게 채우지 않는다.
- 위임은 한 단계까지만 한다(메인 → 역할). 더 깊게 나눠야 하면 이유를 오케스트레이터에 적는다.

## 4. 두 런타임을 함께 지원할 때

1. Claude Code 기준으로 설계하고 `.claude/`에 만든다.
2. 오케스트레이터 스킬 본문에 `## Codex에서 실행할 때` 절을 두고, Claude 전용 기능을 쓰는 단계마다 위 표의 대체 방식을 적는다.
3. `hklock.py write`로 lock을 쓴 뒤 `hklock.py mirror --to codex`로 `.agents/skills/`, `.codex/agents/*.toml`을 만든다.
4. `CLAUDE.md`와 `AGENTS.md`에 같은 하네스 섹션을 둔다.
5. 이후 한쪽을 고치면 `hklock.py mirror`로 다른 쪽을 맞춘다. `hklock.py status`가 어긋남을 알려 준다.
