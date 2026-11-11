---
name: harnesskit
description: "HarnessKit(킷, kit). 프로젝트나 업무에 맞는 AI 하네스(에이전트·스킬·오케스트레이터)를 만든다. 만들기 전에 설치된 스킬·플러그인·훅·MCP를 진단하고, 서로 기능이 부딪히는 도구를 설치 전에 찾아 정리하고, 검증된 오픈소스 스킬을 연결한다. Claude Code와 Codex 모두 지원. '킷으로 하네스 만들어줘', 'kit로 이 프로젝트 하네스 구성해줘', '하네스 만들어줘', '이 스킬 깔아도 돼?', '스킬 충돌 체크', '하네스 회고', '하네스가 느려·고쳐줘', 'harnesskit.lock 대로 맞춰줘', '쓸만한 스킬 추천', '이 스킬 카탈로그에 넣어줘' 같은 요청에 쓴다. 하네스와 무관한 단순 질문에는 쓰지 않는다."
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
7. **가볍게 유지한다.** 늘 드는 비용은 이 스킬 설명문 하나뿐이어야 한다. 웹 탐색과 보안 점검은 하네스를 만들거나 설치할 때만 하고, 평소 작업에서는 돌리지 않는다. 카탈로그는 파일 전체를 읽지 말고 `hkcatalog.py`로 필요한 항목만 본다. 보고는 표 하나와 결론 몇 줄로 끝낸다.
8. **가져오는 것은 예외 없이 보안 점검한다.** 외부 스킬·플러그인·MCP는 카탈로그에 있든 없든 설치하기 전에 `hkinspect.py`(NVIDIA SkillSpector)로 점검한다. 점검할 수 없으면 설치하지 않는다.

## 준비

- **스크립트 위치**: 이 SKILL.md가 있는 폴더의 `scripts/`. 아래에서 `hkscan.py`처럼 줄여 쓴 것은 모두 그 폴더의 파일이다. Python 3.8 이상이 필요하다(`python3`, Windows는 `python` 또는 `py -3`). 받은 저장소 안의 코드는 실행하지 않는다.
- **런타임**: 지금 대화를 실행하는 도구가 Claude Code면 `claude`, Codex면 `codex`. 사용자가 두 도구를 모두 쓴다고 하면 `both`.
- **질문 방법**: Claude Code에서 `AskUserQuestion` 도구가 있으면 그것을, 없거나 Codex면 번호 목록으로 묻는다. 추천안을 첫 번째에 둔다.
- **중간 파일**: 프로젝트의 `_workspace/harnesskit/`에 둔다.

## 모드

| 요청 | 모드 | 따를 문서 |
|---|---|---|
| 하네스 만들어줘 / 구성해줘 / 확장해줘 | build | 아래 절차 + `references/mode-build.md` |
| 이 스킬 깔아도 돼? / 충돌 체크 / 이 저장소 괜찮아? | check | `references/mode-check.md` |
| 하네스 회고 / 피드백 반영 / 진화 / 하네스가 느리다·토큰을 많이 쓴다·같은 실수를 한다 | evolve | `references/mode-evolve.md` |
| lock대로 맞춰줘 / 동료 구성 재현 | sync | `references/mode-sync.md` |
| 이거 카탈로그에 넣어줘 / 나중에 쓰게 저장 / 내 카탈로그 보여줘 | save | `references/mode-save.md` (설치하지 않고 보관만) |
| 쓸만한 스킬 / 카탈로그 보여줘 | catalog | `hkcatalog.py roles`로 역할별 목록을 보여 주고, 궁금한 항목은 `hkcatalog.py show <id>`. `verified`와 외부 전송 여부를 함께 보여 준다 |

## build 절차

자세한 절차는 `references/kit-build.md`에 있다. 단계마다 필요한 문서만 읽는다.

| 단계 | 할 일 | 읽을 문서 |
|---|---|---|
| 0 상태 확인 | lock이 있으면 `hklock.py status --project .` | — |
| 1 스캔 | `hkscan.py env --project . --out _workspace/harnesskit/scan.json --summary` 요약만 읽음 | — |
| 2 분기 | 단발 작업이면 하네스 없이 · 기존 하네스면 확장·유지보수 | 기존 하네스: `build-maintain.md` |
| 3 충돌 체크 | `hkcheck.py --env _workspace/harnesskit/scan.json --md` | review 항목: `conflict-rules.md` |
| 4 도구 선별 | 설치됨 → 카탈로그 → 내 카탈로그 → 웹 | `kit-build.md` |
| 5 설치 | 보안 점검 + 충돌 체크 → 승인 → 프로젝트 범위 | `install.md` |
| 6 설계·생성 | 설계안 승인 후에 파일 생성 | `mode-build.md` |
| 7 기록 | `hklock.py write` | `install.md` |
| 8 보고 | 만든 것 · 연결한 것 · 남은 충돌 | `kit-build.md` |

## 내장 기능과의 역할 분담

HarnessKit은 **설치 전 충돌**과 **하네스 연결**을 맡는다. 이미 쓰는 환경의 사용 기록 기반 점검은 Claude Code 내장 기능을 안내한다: `/skill-doctor`(안 쓰는 스킬), `/doctor prompt-audit`(지시문 감사), `claude plugin details <name>`(플러그인 토큰 예측).

## 실패 처리

- 스크립트가 실패하면 오류를 그대로 보고하고 결과를 추측으로 채우지 않는다. Python이 없으면 설치를 안내한다.
- 권한 거부, 네트워크 차단, 인증 실패는 다시 시도하지 않는다.
- 사용자가 해결안을 고르지 않은 충돌은 그대로 두고 보고서와 lock에 남긴다.
