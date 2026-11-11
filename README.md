# HarnessKit

**더 많은 스킬이 아닌, 더 잘 맞는 AI.**

HarnessKit은 Claude Code와 Codex에서 쓰는 AI 스킬입니다. 프로젝트나 업무를 설명하면 그 일에 맞는 AI 하네스(역할별 에이전트, 스킬, 작업 순서를 정한 오케스트레이터)를 만들어 줍니다. 만들기 전에 지금 설치된 도구를 점검하고, **서로 기능이 부딪히는 스킬을 설치 전에 찾아** 정리한 뒤, 검증된 오픈소스 스킬을 연결합니다.

하네스 설계 절차는 오픈소스 [Harness v2](https://github.com/revfactory/harness)를 가져와 고쳐 썼습니다(Apache-2.0).

---

## 빠른 시작

1. 저장소를 받습니다.
   ```
   git clone <이 저장소 주소>
   ```
2. 받은 폴더에서 Claude Code나 Codex를 열고 이렇게 말합니다.
   ```
   이 키트 설치해줘
   ```
   AI가 `INSTALL.md`를 읽고 설치합니다. 직접 설치하려면 `python3 install.py`를 실행합니다.
3. **새 세션**을 열고, 하네스를 만들 프로젝트 폴더에서 요청합니다.
   ```
   킷으로 이 프로젝트 하네스 만들어줘
   ```

업데이트는 `git pull` 후 "키트 업데이트해줘"(또는 `python3 install.py`), 제거는 `python3 install.py --uninstall`입니다.

## 이렇게 씁니다

| 하고 싶은 일 | 이렇게 말하세요 |
|---|---|
| 프로젝트에 맞는 하네스 만들기 | `킷으로 이 프로젝트 하네스 만들어줘` |
| 스킬을 깔기 전에 괜찮은지 보기 | `이 스킬 깔아도 돼? https://github.com/...` |
| 지금 설치된 것끼리 부딪히는지 보기 | `킷으로 스킬 충돌 체크해줘` |
| 하네스를 쓰고 난 뒤 고치기 | `하네스 회고해줘` / `이 피드백 하네스에 반영해줘` |
| 동료가 만든 구성 그대로 쓰기 | `harnesskit.lock 대로 맞춰줘` |
| 쓸만한 스킬 목록 보기 | `킷 카탈로그 보여줘` |

## 무엇을 해 주나

```
"킷으로 하네스 만들어줘"
 0 상태 확인   이전에 만든 하네스가 있으면, 그 뒤로 바뀐 것을 먼저 알려 줌
 1 스캔        설치된 스킬·플러그인·훅·출력 스타일·MCP와 기존 하네스를 목록화 (Claude Code, Codex)
 2 분기        한 번 하고 끝날 일이면 "하네스 없이 이 스킬로 바로 하세요"라고 제안
 3 충돌 체크   지금 설치된 것끼리 부딪히는지 → 해결안 제시 → 고른 것만 적용
 4 도구 선별   업무 분석 → 카탈로그에서 필요한 도구만 추천 (쓸 때 / 쓰지 않을 때 / 외부 전송 여부)
 5 설치 전 점검 후보와 설치된 것의 충돌을 설치 전에 점검 → 승인 → 설치
 6 하네스 생성 Harness v2 절차. 이미 있는 스킬은 새로 만들지 않고 에이전트에 연결
 7 기록        고른 도구·끈 도구·이유·파일 해시를 harnesskit.lock에 저장
 8 보고        만든 것, 연결한 스킬, 남은 충돌, 측정 방법
```

화면(웹 UI, HTML)을 만드는 하네스에는 **디자인 QA 리뷰어** 서브에이전트가 들어갑니다. 코드 규칙 → 데스크톱·모바일·라이트·다크 화면 캡처 → 화면 결함 → 출시 기준 순으로 보고, 문제를 우선순위(P0~P2)와 근거, 캡처와 함께 보고합니다. 코드는 고치지 않고, 빌드 담당이 P0·P1을 고치면 같은 화면을 다시 캡처해 전후를 비교합니다(`references/roles/ui-ux-reviewer.md`).

생성된 하네스의 오케스트레이터에는 두 가지가 들어갑니다.

- **상태 점검 한 줄**: 실행할 때마다 `harnesskit.lock`과 비교해 새 도구가 설치됐거나, 하네스 파일이 바뀌었거나, 회고할 때가 되면 한 줄로 알려 줍니다. 훅이 아니라 스크립트라서, 알릴 것이 없으면 아무것도 출력하지 않습니다.
- **착수 전 확인**: 요청이 모호할 때만 작업 전에 묻습니다. 질문 수는 작업 크기에 맞춥니다.

## 충돌 체크 예시

인기 스킬 세 개(Superpowers, Karpathy Guidelines, Attention-kind)를 함께 설치하기 전에 점검한 실제 결과입니다(일부 생략).

| 심각도 | 유형 | 대상 | 내용 |
|---|---|---|---|
| high | 지시 모순 | superpowers ↔ attention-span | Superpowers는 답하기 전에 스킬부터 부르고 `"Using [skill] to [purpose]"`라고 알리라고 하고, Attention-kind는 `"The first sentence carries the single most important takeaway"`라고 한다. 둘 다 응답 첫 줄을 가져가려 한다. |
| high | 지시 모순 | superpowers ↔ karpathy-guidelines | `"1% chance ... MUST invoke"`, `"Skill check comes BEFORE clarifying questions"` vs `"If something is unclear, stop ... Ask."`, `"For trivial tasks, use judgment."` |
| low | 상시 비용 | superpowers | SessionStart 훅이 세션마다 약 3,180자(추정 약 800토큰)를 주입한다. |

판정은 두 층으로 나뉩니다.
- **스크립트가 확정하는 것**: 카탈로그에 원문 근거와 함께 기록된 충돌, 같은 자리 경쟁, 역할 중복, 이름 중복, 상시 비용. 매번 같은 결과가 나옵니다.
- **AI가 원문을 읽고 판정하는 것**: 같은 의도를 주장하는 스킬 쌍. 판정 기준은 `references/conflict-rules.md`에 있습니다.

### 충돌 유형

| 유형 | 뜻 |
|---|---|
| 트리거 겹침 | 같은 요청에 둘 이상이 반응해, 어느 쪽이 불릴지 매번 달라짐 |
| 지시 모순 | 같은 상황에 반대로 지시함 |
| 자리 경쟁 | 출력 스타일, 세션 시작 지침, 작업 절차 담당처럼 하나만 둘 수 있는 자리를 다툼 |
| 역할 중복 | 같은 일을 하는 도구가 둘 (메모리 2개, HWP 도구 2개 등) |
| 부작용 경쟁 | 같은 설정·파일·네트워크 경로를 바꿈 |

## 카탈로그

저장소 파일을 읽고 검토한 도구 51개를 담았습니다. 하네스를 만들 때는 **이미 설치된 것 → 카탈로그 → 웹 탐색** 순으로 후보를 모으고, 설치는 기능 충돌 체크와 SkillSpector 보안 점검을 통과한 것만 합니다. 전체 내용은 `skills/harnesskit/references/catalog.json`에 있고, 스킬은 `hkcatalog.py`로 필요한 항목만 읽습니다.

| 층 | 도구 | 하는 일 | 주의 |
|---|---|---|---|
| 상시 적용 (자리마다 하나) | Attention-kind | 결론부터, 짧게 답하기 | 출력 스타일. AGPL이라 링크로만 안내 |
| | Karpathy Guidelines | 과한 구현, 관계없는 수정, 말없는 가정 줄이기 | |
| | Superpowers | 브레인스토밍 → 계획 → TDD → 검증 절차 | 매 세션 지침 주입. 하네스 오케스트레이터와 같은 자리 |
| 작업용 | im-not-ai | 한국어 윤문, 번역투 교정 | |
| | Anthropic 문서 스킬 | Word·Excel·PPT·PDF | LibreOffice 등 필요 |
| | kordoc | HWP/HWPX 읽기·쓰기·양식 | `KORDOC_OFFLINE=1` 권장 |
| | Context7 | 버전별 라이브러리 문서 | 질의가 외부로 전송됨 |
| | Trail of Bits static-analysis, fp-check | CodeQL·Semgrep 결과 분류, 오탐 판정 | fp-check는 응답마다 판정 훅이 돎 |
| | Trail of Bits mutation / property-based testing | 테스트 설계 점검 | |
| | Playwright | 웹 E2E 테스트 | 브라우저 도구는 하나만 |
| UI/UX (`--category ui-ux`) | frontend-design, ui-ux-pro-max, playground, shadcn | UI 설계, 디자인 시스템, 단일 HTML 도구, 컴포넌트 | 설계 스킬끼리 같은 요청을 다툼 |
| | web-design-guidelines, web-design-reviewer, design-qa, design-review | 코드 규칙 리뷰, 실제 화면 검토, 출시 기준 판정, UX 비평 | 디자인 QA 리뷰어가 단계별로 나눠 씀 |
| | Chrome DevTools MCP, draw.io, frontend-slides, Canva, Miro | 성능·접근성 점검, 다이어그램, HTML 슬라이드, 디자인 도구 연동 | |
| | 공식 code-review, pr-review-toolkit, feature-dev, commit-commands, GitHub MCP | PR 리뷰, 측면별 리뷰, 기능 개발 절차, 커밋·PR, GitHub 연동 | feature-dev는 작업 절차 자리를 다툼 |
| | Trail of Bits spec-compliance, testing-handbook, claude-security, skill-creator, arXiv MCP | 명세–코드 대조, 퍼징, 보안 스캔, 스킬 작성, 논문 | |
| 측정·보안 | ccusage, **SkillSpector (필수)** | 토큰 측정, 설치 전 보안 점검 | `--offline`, `--no-llm` |
| 선택 | Headroom, Anthropic example-skills, impeccable, ui-ux-pro-max, antv 차트, security-guidance 등 | 필요할 때만 골라 설치 | 묶음이 크거나 외부 전송·훅이 있음 |
| 제외 | claude-mem, k-skill 전체 설치, agent-browser | | 외부 전송, 상시 비용, Playwright와 충돌 |

## Claude Code와 Codex

| | Claude Code | Codex |
|---|---|---|
| 설치 위치 | `~/.claude/skills/harnesskit` | `~/.codex/skills/harnesskit` |
| 스캔·충돌 체크·카탈로그 | 지원 | 지원 |
| 하네스 출력 | `.claude/agents/*.md`, `.claude/skills/`, `CLAUDE.md` | `.codex/agents/*.toml`, `.agents/skills/`, `AGENTS.md` |
| 실행 방식 | 워크플로·지속형 에이전트·서브에이전트 | 메인 에이전트가 단계를 이어 실행하고 `_workspace/` 파일로 넘김, 가능하면 서브에이전트 |

두 도구를 함께 쓰는 팀이면 Claude Code 기준으로 만든 하네스를 `hklock.py mirror --to codex`로 Codex 형식으로 옮깁니다.

## Harness v2와 무엇이 다른가

HarnessKit은 Harness v2의 하네스 설계 절차를 그대로 쓰고, 그 앞뒤를 채웁니다. 바꾼 부분은 파생 문서에 **[HK]**로 표시했습니다.

| | Harness v2 | HarnessKit |
|---|---|---|
| 점검 범위 | 프로젝트 `.claude/agents`, `.claude/skills`, `CLAUDE.md` | + 사용자 스킬, 플러그인, 훅, 출력 스타일, MCP, Codex |
| 외부 스킬 | 프로젝트 안의 스킬만 재사용 | 설치된 외부 스킬을 에이전트에 연결 |
| 도구 간 충돌 | 다루지 않음 | 설치 전에 점검하고 해결안 제시 |
| 하네스가 필요 없는 일 | 따로 거르지 않음 | 단발 작업이면 하네스 없이 처리하도록 제안 |
| 회고 | 사용자가 요청해야 시작 | lock과 비교해 시점을 알려 주고, 규칙을 더하기 전에 정리 |
| 런타임 | Claude Code | Claude Code + Codex |

Claude Code 내장 기능과는 역할을 나눕니다. 안 쓰는 스킬 찾기는 `/skill-doctor`, 지시문 감사는 `/doctor prompt-audit`, 플러그인 토큰 예측은 `claude plugin details`가 더 정확하므로 그쪽을 안내합니다. HarnessKit은 **설치 전 충돌**과 **하네스 연결**을 맡습니다.

## 안전

- 스캔 스크립트는 파일을 읽기만 하고, 스캔한 스킬의 코드는 실행하지 않습니다. 네트워크 통신도 하지 않습니다.
- 외부 스킬은 카탈로그에 있든 없든 설치 전에 SkillSpector로 점검합니다. 설치되는 범위(스킬, 에이전트, 훅, 명령 등)만 보고, `DO_NOT_INSTALL`이면 사용자가 근거를 보고 분명히 감수한다고 할 때만 설치하며 그 결정을 기록합니다.
- 키트 자신도 SkillSpector 점검에서 남은 탐지가 0건입니다. 허용한 항목은 근거와 함께 `.skillspector-baseline.yaml`에 있습니다.
- 설치·끄기·파일 생성은 사용자가 승인한 뒤에만 하고, 설정 파일은 고치기 전에 백업합니다.
- 외부로 데이터를 보내는 도구는 카탈로그와 점검 결과에 표시합니다.

## 요구 사항

- Claude Code 또는 Codex
- Python 3.8 이상 (Windows는 `python` 또는 `py -3`)
- [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector): 외부 스킬을 설치하기 전 보안 점검에 쓴다. 없으면 HarnessKit은 외부 스킬을 설치하지 않는다. `uv tool install git+https://github.com/NVIDIA/skillspector.git`

## 구조

```
HarnessKit/
├── install.py                       설치·업데이트·제거
├── INSTALL.md                       AI가 따르는 설치 절차
├── skills/harnesskit/
│   ├── SKILL.md                     진입점 (상시 설명문 약 160토큰)
│   ├── scripts/
│   │   ├── hkscan.py                환경·후보 저장소 스캔
│   │   ├── hkcheck.py               충돌 체크
│   │   ├── hkinspect.py             설치 전 보안 점검 (NVIDIA SkillSpector, --no-llm)
│   │   ├── hkcatalog.py             카탈로그에서 필요한 항목만 조회
│   │   └── hklock.py                harnesskit.lock 기록, 변화 감지, Claude↔Codex 변환
│   ├── .skillspector-baseline.yaml  키트 자체 점검에서 허용한 항목과 근거
│   └── references/
│       ├── catalog.json             큐레이션 카탈로그
│       ├── conflict-rules.md        충돌 판정 기준
│       ├── mode-build.md            하네스 설계 절차 (Harness v2 파생, [HK] 표시)
│       ├── mode-evolve.md           회고 절차 (Harness v2 파생, [HK] 표시)
│       ├── mode-check.md, mode-sync.md, codex.md, preflight.md
│       ├── roles/ui-ux-reviewer.md  디자인 QA 리뷰어 역할 템플릿
│       └── harness/                 Harness v2 참조 문서 원본
└── tests/                           python3 -m unittest discover -s tests
```

## 라이선스

Apache-2.0. Harness v2에서 가져온 부분은 `NOTICE`에 출처와 변경 내용을 적었습니다. 카탈로그의 외부 도구는 각 저장소의 라이선스를 따르며, HarnessKit은 그 파일을 복사하지 않고 공식 설치 방법만 안내합니다.
