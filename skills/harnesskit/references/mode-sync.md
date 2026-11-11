# sync 모드: lock대로 구성 재현

동료가 만든 프로젝트를 받아 "harnesskit.lock 대로 맞춰줘", "이 프로젝트 하네스 환경 세팅해줘"라고 할 때 쓴다.

## 절차

1. **읽기**: 프로젝트 루트의 `harnesskit.lock`을 읽는다. `runtimes`, `tools`(use/disabled/skipped와 이유), `decisions`, `harness`를 확인한다.

2. **비교**: `hkscan.py env --project . --out _workspace/harnesskit/scan.json` 결과와 lock을 대조해 세 목록을 만든다.
   - 설치할 것: lock에서 `use`인데 이 PC에 없는 도구
   - 끌 것: lock에서 `disabled`인데 이 PC에서 켜져 있는 도구
   - 다른 것: 이 PC에만 있는 도구 (끄라고 하지 않는다. 충돌만 본다)

3. **런타임 맞추기**: 이 PC의 런타임이 lock과 다르면(예: lock은 claude, 지금은 Codex) 카탈로그의 해당 런타임 설치 명령을 쓰고, 하네스 파일은 `hklock.py mirror --to codex`(또는 `--to claude`)로 만든다. 카탈로그에 그 런타임 명령이 없으면 그 도구는 건너뛰고 보고한다.

4. **보안 점검과 충돌 체크**: 설치할 도구마다 `hkinspect.py`로 보안 점검을 한다(필수, `SKILL.md` 5단계 판정 규칙). 이어서 `--candidate`로 `hkcheck.py`를 돌린다. 이 PC에만 있는 도구와 부딪히는 항목은 따로 보여 준다.

5. **승인 후 적용**: 계획을 표로 보여 주고 승인받은 뒤 설치·끄기를 한다.
   - `/plugin ...` 같은 슬래시 명령은 사용자에게 입력을 부탁한다.
   - `claude plugin install`, `npx`, `uv tool install` 같은 셸 명령은 승인 후 실행한다.
   - `verified: survey` 도구는 실행 전에 원 저장소 README로 명령을 한 번 확인한다.
   - `decisions`의 우선순위 문장이 `CLAUDE.md`/`AGENTS.md`에 없으면 넣는다.

6. **확인**: 다시 스캔하고 `hklock.py status`로 남은 차이를 보고한다.

## 지킬 것

- lock은 팀이 공유하는 파일이다. 이 PC 사정으로 다르게 설치한 것은 보고만 하고, 사용자가 원할 때만 lock을 고친다.
- 설치에 실패한 도구는 다시 시도하지 않고, 그 도구 없이 하네스를 쓸 때 무엇이 빠지는지 적는다.
