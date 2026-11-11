# check 모드: 설치 전 충돌 점검

"이 스킬 깔아도 돼?", "스킬 충돌 체크해줘", "<GitHub 주소> 괜찮아?" 같은 요청에 쓴다. **설치는 하지 않는다.** 점검과 해결안 제시까지만 한다.

## 절차

1. **스캔**: `hkscan.py env --project . --out _workspace/harnesskit/scan.json`

2. **점검 대상 정하기**
   - 카탈로그에 있는 도구: `--candidate <id>` 로 넘긴다. id는 `references/catalog.json` 참고.
   - GitHub 주소나 로컬 경로:
     1. 새로 만든 빈 임시 폴더에 `git clone --depth 1 <url>` 한다. 받은 저장소 안의 스크립트, 설치 명령, 빌드 도구는 **실행하지 않는다.**
     2. `hkscan.py repo <폴더> --out _workspace/harnesskit/cand-<이름>.json` → `--candidate-scan`으로 넘긴다.
     3. README와 PRIVACY·SECURITY 문서에서 telemetry, analytics, 외부 API 호출, 계정 요구를 찾아 적는다. 라이선스는 `license_head`로 확인한다.
     4. SkillSpector가 설치되어 있으면 `--no-llm` 모드로 보안 점검을 돌린다. 없으면 설치를 권하는 데서 그친다.
   - 대상이 없으면 현재 설치된 것끼리 점검한다.

3. **판정**: `hkcheck.py --env _workspace/harnesskit/scan.json [--candidate ...] [--candidate-scan ...] --out _workspace/harnesskit/check.json`
   - catalog, rule 항목은 그대로 보고한다.
   - `review` 항목은 `references/conflict-rules.md` 2절 절차로 원문을 읽고 판정한다.

4. **보고**: `references/conflict-rules.md` 5절 형식. 마지막에 결론 한 줄을 붙인다.
   - **설치 권장**: high/medium 충돌 없음
   - **조건부 권장**: 해결안 하나를 적용하면 괜찮음 (어떤 해결안인지 적는다)
   - **비권장**: 정책상 제외 도구이거나, 해결할 수 없는 모순이 있음

5. **해결안 적용(선택)**: 사용자가 해결안을 고르면 `conflict-rules.md` 4절 방법으로 적용한다. 설정 파일은 먼저 백업한다. 프로젝트에 `harnesskit.lock`이 있으면 `hklock.py write --data`로 `decisions`에 남긴다.

## 내장 기능 안내

HarnessKit은 설치 전 충돌을 본다. 이미 쓰고 있는 환경의 사용 기록 기반 점검은 Claude Code 내장 기능이 더 정확하므로 함께 안내한다.

- 안 쓰는 스킬·플러그인과 스킬별 비용: `/skill-doctor`
- 지시문끼리의 낡음·모순 감사: `/doctor prompt-audit`
- 플러그인별 상시 토큰 예측: `claude plugin details <name>`
