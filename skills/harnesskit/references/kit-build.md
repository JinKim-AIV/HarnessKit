# HarnessKit build 절차 (자세히)

`SKILL.md`의 build 표에서 넘어온다. 설치는 `install.md`, 하네스 설계·생성은 `mode-build.md`를 따른다.


**0. 상태 확인**: 프로젝트에 `harnesskit.lock`이 있으면 `hklock.py status --project .`를 실행하고 신호가 있으면 먼저 알린다.

**1. 스캔**: `hkscan.py env --project . --out _workspace/harnesskit/scan.json --summary`. 출력되는 짧은 요약만 읽는다. `scan.json`에는 설명문 전문까지 들어 있어 수만 자가 되므로, 스크립트에 넘기는 용도로만 쓰고 직접 읽지 않는다. 사용자에게는 세 줄로 요약한다: 설치된 도구, 기존 하네스(Claude Code·Codex), 상시 비용 상위 3개(추정 토큰).

**2. 분기**: 하네스가 필요한 일인지 판단한다.
- 산출물이 하나이고, 반복되지 않고, 한 세션에 끝나며, 역할을 나눠도 이득이 없으면 단발 작업이다. "하네스 없이 이 스킬로 바로 하면 된다"고 맞는 스킬을 알려 주고 선택받는다. 그래도 원하면 진행한다.
- 기존 하네스가 있으면 새로 만들지 않고 `build-maintain.md`의 확장·유지보수 경로를 탄다.

**3. 현재 환경 충돌 체크**: `hkcheck.py --env _workspace/harnesskit/scan.json --md`로 표를 받아 읽는다(검토 항목에는 근거 파일 경로가 함께 나온다). JSON이 필요하면 `--out`으로 파일에 남기되 직접 읽지 않는다. `review` 항목은 `references/conflict-rules.md`로 판정한다. high/medium 항목은 해결안을 고르게 하고 적용한다. 고른 결과는 7단계 lock의 `decisions`에 남긴다.

**4. 도구 선별 (후보는 넓게, 설치는 좁게)**: `mode-build.md` 1단계로 업무를 분석해 필요한 역량을 정한 뒤, 역량마다 세 곳에서 후보를 모은다.
1. **이미 설치된 것**(동기화된 스킬 포함): 맞는 정도가 비슷하면 설치된 쪽을 먼저 쓴다. 설치 비용이 없다. 카탈로그나 웹 후보가 분명히 더 잘 맞으면 그쪽을 추천하고 이유를 적는다.
2. **카탈로그**: `hkcatalog.py find --role <역할>` 또는 `--text <키워드>`로 찾는다. 키트 카탈로그와 사용자가 보관해 둔 **내 카탈로그**(`origin: mine`)가 함께 나온다. 검토를 마친 도구라 우선하고, 내 카탈로그 항목은 "내 카탈로그"로 표시한다. `use_when`, `skip_when`, `requires`, 외부 전송을 보고 거른다.
3. **바깥(웹)**: 카탈로그와 별개로 매번 찾아본다. 공식 출처(Claude Code는 `anthropics/skills`와 공식 마켓플레이스 `claude-plugins-official`, Codex는 공식 문서의 스킬) → 큐레이션 목록(`hesreallyhim/awesome-claude-code`, `VoltAgent/awesome-agent-skills`) → 일반 검색 순서로 본다. 역량마다 3개, 전체 8개까지만 본다. 결과에는 **카탈로그 밖** 표시를 단다. 웹 검색 도구가 없으면 이 단계는 건너뛰고 그 사실을 알린다.

산출물에 사람이 읽는 한국어 글이 있으면 한국어 윤문 도구(`role: korean-writing`)를 기본 후보에 넣는다. 산출물에 화면(웹 UI, HTML)이 있으면 `hkcatalog.py find --category ui-ux`로 UI 설계·리뷰 도구를 후보에 넣고, 6단계에서 디자인 QA 에이전트(`references/roles/ui-ux-reviewer.md`)를 둔다. 모은 후보는 출처(설치됨 / 카탈로그 / 카탈로그 밖), 하는 일, 이유를 한 표로 보여 주고 고르게 한다. 같은 역할 후보가 여럿이면 하나를 추천하고, 나머지는 왜 뺐는지 한 줄씩 적는다.

**5. 설치 전 점검과 설치**: `references/install.md`를 따른다. 보안 점검(필수) → 기능 충돌 체크 → 승인 → 이 프로젝트 범위로 설치.

**6. 하네스 설계·생성**: `references/mode-build.md`의 1~6단계를 따른다. 2단계 설계가 끝나면 **파일을 만들기 전에 설계안(2-4)을 보여 주고 승인받는다.** 이때 아래 **도구 브리프**를 함께 넘긴다.

```
도구 브리프
- <플러그인명:스킬명 또는 스킬명> — 하는 일 / 쓸 때 / 쓰지 않을 때 (catalog의 use_when, skip_when)
- 끈 도구와 이유 (3단계 결정)
- 절차 담당: 하네스 오케스트레이터 | <외부 프레임워크>
- 런타임: claude | codex | both
```

런타임별 출력: `claude`는 `.claude/` 아래에 만든다. `codex`는 `references/codex.md` 형식으로 만든다. `both`는 Claude Code 기준으로 만든 뒤 7단계에서 `hklock.py mirror --to codex`를 실행한다.

**7. 기록**: `references/install.md` 「기록」대로 `hklock.py write`를 실행한다.

**8. 보고**: 다음 순서로 짧게 보고한다.
- 만든 것: 에이전트·스킬·오케스트레이터, 그리고 호출하는 말
- 연결한 외부 스킬, 끈 도구와 이유
- 남은 충돌과 외부 전송 도구
- 측정 방법: `npx ccusage@20.0.49 --offline`, `claude plugin details <name>`
- 다음 단계: 실제 작업 한 건 실행 → 피드백 → `하네스 회고`

