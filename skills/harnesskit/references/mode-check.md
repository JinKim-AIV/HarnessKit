# check 모드: 설치 전 충돌 점검

"이 스킬 깔아도 돼?", "스킬 충돌 체크해줘", "<GitHub 주소> 괜찮아?" 같은 요청에 쓴다. **설치는 하지 않는다.** 점검과 해결안 제시까지만 한다.

## 절차

1. **스캔**: `hkscan.py env --project . --out _workspace/harnesskit/scan.json --summary` (요약만 읽고 JSON은 스크립트에 넘긴다)

2. **점검 대상 정하기**
   - 카탈로그에 있는 도구: `--candidate <id>` 로 넘긴다. id는 `hkcatalog.py find --text <이름>`으로 찾는다(카탈로그 파일을 통째로 읽지 않는다).
   - GitHub 주소나 로컬 경로:
     1. 새로 만든 빈 임시 폴더에 `git clone --depth 1 <url>` 한다. 받은 저장소 안의 스크립트, 설치 명령, 빌드 도구는 **실행하지 않는다.**
     2. `hkscan.py repo <폴더> --out _workspace/harnesskit/cand-<이름>.json --summary` → JSON 파일을 `--candidate-scan`으로 넘긴다.
     3. README와 PRIVACY·SECURITY 문서에서 telemetry, analytics, 외부 API 호출, 계정 요구를 찾아 적는다. 라이선스는 `license_head`로 확인한다.
     4. **보안 점검(필수)**: `hkinspect.py <폴더> [--plugin <이름>]`. 판정 처리는 `install.md`와 같다. 판정(SAFE / CAUTION / DO_NOT_INSTALL)과 걸린 항목(파일:줄)을 결과에 넣는다. SkillSpector가 없으면(`missing`) 설치 명령을 보여 주고, 점검 전에는 "설치 권장" 결론을 내지 않는다.
   - 대상이 없으면 현재 설치된 것끼리 점검한다.

3. **판정**: `hkcheck.py --env _workspace/harnesskit/scan.json [--candidate ...] [--candidate-scan ...] --md` (표만 읽는다)
   - catalog, rule 항목은 그대로 보고한다.
   - `review` 항목은 `references/conflict-rules.md` 2절 절차로 원문을 읽고 판정한다.

4. **보고**: `references/conflict-rules.md` 5절 형식. 마지막에 결론 한 줄을 붙인다.
   - **설치 권장**: 보안 점검 SAFE이고 high/medium 충돌 없음
   - **조건부 권장**: 보안 점검 CAUTION이거나, 해결안 하나를 적용하면 괜찮음 (걸린 항목과 해결안을 적는다)
   - **비권장**: 보안 점검 DO_NOT_INSTALL, 정책상 제외 도구, 또는 해결할 수 없는 모순이 있음

5. **해결안 적용(선택)**: 사용자가 해결안을 고르면 `conflict-rules.md` 4절 방법으로 적용한다. 설정 파일은 먼저 백업한다. 프로젝트에 `harnesskit.lock`이 있으면 `hklock.py write --data`로 `decisions`에 남긴다.

## 내장 기능 안내

HarnessKit은 설치 전 충돌을 본다. 이미 쓰고 있는 환경의 사용 기록 기반 점검은 Claude Code 내장 기능이 더 정확하므로 함께 안내한다.

- 안 쓰는 스킬·플러그인과 스킬별 비용: `/skill-doctor`
- 지시문끼리의 낡음·모순 감사: `/doctor prompt-audit`
- 플러그인별 상시 토큰 예측: `claude plugin details <name>`
