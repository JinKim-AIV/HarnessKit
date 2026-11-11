# HarnessKit 저장소

HarnessKit 스킬의 원본 저장소다. 사용자가 이 저장소에서 HarnessKit 설치·업데이트·제거를 요청하면 `INSTALL.md` 절차를 따른다.

## 개발 규칙

- 테스트: `python3 -m unittest discover -s tests`. 스크립트를 고치면 테스트를 함께 고치고 돌린다.
- 스크립트는 Python 표준 라이브러리만 쓴다. 스캔하는 스킬·저장소의 코드는 실행하지 않는다.
- `skills/harnesskit/references/harness/`는 Harness v2 원본 그대로 둔다. Harness v2에서 파생한 `mode-build.md`, `mode-evolve.md`를 고치면 바뀐 곳에 `[HK]`를 표시하고 `NOTICE`를 갱신한다.
- `catalog.json` 항목을 추가하거나 고치면 `verified`(direct/survey)를 사실대로 적고, 충돌 `detail`에는 원문 인용을 넣는다. 외부 도구의 파일은 저장소에 복사하지 않는다.
- 카탈로그의 `npx`·`uvx` 설치 명령은 버전을 고정한다. 고정하지 않으면 원 저장소가 털렸을 때 악성 업데이트가 그대로 실행된다.
- 키트 자신은 SkillSpector 자체 점검에서 남은 탐지가 0건이어야 한다(`tests`의 SelfInspectTests). 허용할 항목은 `skills/harnesskit/.skillspector-baseline.yaml`에 근거와 함께 적는다.
- 늘 드는 비용은 스킬 설명문 하나로 유지한다. 훅을 추가하지 않는다.
- 사용자에게 보이는 문구와 커밋 메시지는 한국어로 쓴다.
