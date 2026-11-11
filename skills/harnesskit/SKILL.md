---
name: harnesskit
description: "HarnessKit(킷, kit). 프로젝트나 업무에 맞는 AI 하네스(에이전트·스킬·오케스트레이터)를 만든다. 만들기 전에 설치된 스킬·플러그인·훅·MCP를 진단하고, 서로 기능이 부딪히는 도구를 설치 전에 찾아 정리하고, 검증된 오픈소스 스킬을 연결한다. Claude Code와 Codex 모두 지원. '킷으로 하네스 만들어줘', 'kit로 이 프로젝트 하네스 구성해줘', '하네스 만들어줘', '이 스킬 깔아도 돼?', '스킬 충돌 체크', '하네스 회고', 'harnesskit.lock 대로 맞춰줘', '쓸만한 스킬 추천' 같은 요청에 쓴다. 하네스와 무관한 단순 질문에는 쓰지 않는다."
---

# HarnessKit

필요한 도구만 고르고, 서로 부딪히지 않게 정리한 뒤, Harness v2 절차로 하네스를 만든다.

## 원칙

1. **바꾸기 전에 보여 주고 승인받는다.** 설치, 끄기, 파일 생성은 사용자가 고른 뒤에 한다. 설정 파일은 고치기 전에 백업한다.
2. **이미 있는 검증된 스킬은 새로 만들지 않고 연결한다.** 같은 일을 하는 스킬을 또 만들면 트리거가 겹치고 비용만 는다.
3. **하네스가 필요 없는 일에는 만들지 않는다.** 하네스 설계에도 토큰이 든다.
4. **한 자리에는 하나만 둔다.** 답변 형식(출력 스타일), 작업 절차 담당, 하네스 생성기는 동시에 둘이 켜지면 지시가 부딪힌다.
5. **측정하지 않은 효과를 숫자로 말하지 않는다.** 토큰 수는 추정치라고 밝힌다.
6. **외부로 데이터를 보내는 도구는 먼저 알린다.**

## 준비

- **스크립트 위치**: 이 스킬 폴더의 `scripts/`. 보통 Claude Code는 `~/.claude/skills/harnesskit/scripts/`, Codex는 `~/.codex/skills/harnesskit/scripts/`다. 아래에서 `hkscan.py`처럼 줄여 쓴 것은 모두 그 폴더의 파일이다. Python 3.8 이상이 필요하다(`python3`, Windows는 `python` 또는 `py -3`). 받은 저장소 안의 코드는 실행하지 않는다.
- **런타임**: 지금 대화를 실행하는 도구가 Claude Code면 `claude`, Codex면 `codex`. 사용자가 두 도구를 모두 쓴다고 하면 `both`.
- **질문 방법**: Claude Code에서 `AskUserQuestion` 도구가 있으면 그것을, 없거나 Codex면 번호 목록으로 묻는다. 추천안을 첫 번째에 둔다.
- **중간 파일**: 프로젝트의 `_workspace/harnesskit/`에 둔다.

## 모드

| 요청 | 모드 | 따를 문서 |
|---|---|---|
| 하네스 만들어줘 / 구성해줘 / 확장해줘 | build | 아래 절차 + `references/mode-build.md` |
| 이 스킬 깔아도 돼? / 충돌 체크 / 이 저장소 괜찮아? | check | `references/mode-check.md` |
| 하네스 회고 / 피드백 반영 / 진화 | evolve | `references/mode-evolve.md` |
| lock대로 맞춰줘 / 동료 구성 재현 | sync | `references/mode-sync.md` |
| 쓸만한 스킬 / 카탈로그 보여줘 | catalog | `references/catalog.json`을 층(layer)별 표로 요약. `verified`와 `external_data`를 함께 보여 준다 |

## build 절차

**0. 상태 확인**: 프로젝트에 `harnesskit.lock`이 있으면 `hklock.py status --project .`를 실행하고 신호가 있으면 먼저 알린다.

**1. 스캔**: `hkscan.py env --project . --out _workspace/harnesskit/scan.json`. 사용자에게 세 줄로 요약한다: 설치된 도구, 기존 하네스(Claude Code·Codex), 상시 비용 상위 3개(추정 토큰).

**2. 분기**: 하네스가 필요한 일인지 판단한다.
- 산출물이 하나이고, 반복되지 않고, 한 세션에 끝나며, 역할을 나눠도 이득이 없으면 단발 작업이다. "하네스 없이 이 스킬로 바로 하면 된다"고 맞는 스킬을 알려 주고 선택받는다. 그래도 원하면 진행한다.
- 기존 하네스가 있으면 새로 만들지 않고 `mode-build.md` 0단계 표의 확장·유지보수 경로를 탄다.

**3. 현재 환경 충돌 체크**: `hkcheck.py --env _workspace/harnesskit/scan.json --out _workspace/harnesskit/check.json`. `review` 항목은 `references/conflict-rules.md`로 판정한다. high/medium 항목은 해결안을 고르게 하고 적용한다. 고른 결과는 7단계 lock의 `decisions`에 남긴다.

**4. 업무 분석과 도구 선별**: `mode-build.md` 1단계로 업무를 분석해 필요한 역량을 정한다. `references/catalog.json`에서 `role`·`capabilities`가 맞는 후보를 고르고 `use_when`, `skip_when`, `requires`, `external_data`를 보고 걸러낸다. 같은 역할 도구가 이미 설치돼 있으면 그것을 쓴다. 카탈로그에 없는 도구를 원하면 `mode-check.md`의 저장소 점검을 거친다. 후보를 이유와 함께 표로 보여 준다.

**5. 후보 충돌 체크와 설치**: `hkcheck.py --env ... --candidate <id> ...`로 설치 전에 점검하고 보고한다. 승인받은 도구만 카탈로그의 해당 런타임 설치 명령으로 설치한다.
- `/plugin ...` 같은 슬래시 명령은 사용자에게 입력을 부탁한다. 셸 명령은 승인 후 실행한다.
- `verified: survey` 도구는 실행 전에 원 저장소 README로 명령을 확인한다.
- 설치 후 다시 스캔한다. 실패한 도구는 다시 시도하지 않고 `skipped`로 기록한다.

**6. 하네스 설계·생성**: `references/mode-build.md`의 1~6단계를 따른다. 2단계 설계가 끝나면 **파일을 만들기 전에 설계안(2-4)을 보여 주고 승인받는다.** 이때 아래 **도구 브리프**를 함께 넘긴다.

```
도구 브리프
- <플러그인명:스킬명 또는 스킬명> — 하는 일 / 쓸 때 / 쓰지 않을 때 (catalog의 use_when, skip_when)
- 끈 도구와 이유 (3단계 결정)
- 절차 담당: 하네스 오케스트레이터 | <외부 프레임워크>
- 런타임: claude | codex | both
```

런타임별 출력: `claude`는 `.claude/` 아래에 만든다. `codex`는 `references/codex.md` 형식으로 만든다. `both`는 Claude Code 기준으로 만든 뒤 7단계에서 `hklock.py mirror --to codex`를 실행한다.

**7. 기록**: `_workspace/harnesskit/lock-data.json`을 쓰고 `hklock.py write --project . --data _workspace/harnesskit/lock-data.json`을 실행한다.

```json
{
  "runtimes": ["claude"],
  "tools": [
    {"id": "im-not-ai", "status": "use", "why": "보고서 문장 다듬기"},
    {"id": "superpowers", "status": "disabled", "why": "오케스트레이터와 작업 절차 자리 경쟁"}
  ],
  "decisions": [{"finding": "superpowers vs harnesskit (slot)", "choice": "이 프로젝트에서 superpowers 끔"}],
  "harness": {"orchestrator": "<오케스트레이터 스킬명>", "agents": ["..."], "skills": ["..."]}
}
```

**8. 보고**: 다음 순서로 짧게 보고한다.
- 만든 것: 에이전트·스킬·오케스트레이터, 그리고 호출하는 말
- 연결한 외부 스킬, 끈 도구와 이유
- 남은 충돌과 외부 전송 도구
- 측정 방법: `npx ccusage@latest --offline`, `claude plugin details <name>`
- 다음 단계: 실제 작업 한 건 실행 → 피드백 → `하네스 회고`

## 내장 기능과의 역할 분담

HarnessKit은 **설치 전 충돌**과 **하네스 연결**을 맡는다. 이미 쓰는 환경의 사용 기록 기반 점검은 Claude Code 내장 기능을 안내한다: `/skill-doctor`(안 쓰는 스킬), `/doctor prompt-audit`(지시문 감사), `claude plugin details <name>`(플러그인 토큰 예측).

## 실패 처리

- 스크립트가 실패하면 오류를 그대로 보고하고 결과를 추측으로 채우지 않는다. Python이 없으면 설치를 안내한다.
- 권한 거부, 네트워크 차단, 인증 실패는 다시 시도하지 않는다.
- 사용자가 해결안을 고르지 않은 충돌은 그대로 두고 보고서와 lock에 남긴다.
