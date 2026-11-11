# 설치 안내 (AI용)

사용자가 이 저장소에서 "이 키트 설치해줘", "키트 업데이트해줘", "키트 지워줘"라고 하면 이 절차를 따른다. 설치는 스킬 폴더를 복사하는 일이다. 사용자 설정 파일(`settings.json`, `config.toml` 등)은 바꾸지 않는다.

## 설치·업데이트

1. **Python 확인**: `python3 --version`. Windows는 `python --version` 또는 `py -3 --version`. 3.8 미만이거나 없으면 아래 "수동 설치"로 간다.
2. **미리보기**: 저장소 루트에서 `python3 install.py --dry-run`을 실행하고, 어디에 설치되는지(Claude Code, Codex) 보여 준다.
   - 한쪽에만 설치하길 원하면 `--target claude` 또는 `--target codex`.
   - 감지가 안 되면 사용자에게 어느 도구를 쓰는지 묻고 `--target`으로 지정한다.
3. **설치**: `python3 install.py` (같은 옵션 유지). 하네스를 만들 프로젝트를 알면 `--project <경로>`를 붙인다. 설치 직후 점검이 그 프로젝트 기준으로 돈다.
4. **설치 후 점검 전달**: 출력에 "설치 후 점검에서 확인할 것"이 있으면 그대로 전한다. 해결은 사용자가 고른 뒤에만 한다. 예를 들어 원본 Harness 플러그인과 겹치면 다음 중 하나로 끈다.
   - 이 프로젝트에서만: `claude plugin disable harness@harness-marketplace --scope local`
   - 전체: `/plugin`
5. **안내**: 새 세션을 열어야 스킬이 보인다. Claude Code는 `/skills`에서 `harnesskit`을 확인할 수 있다. 다음 요청 예를 알려 준다.
   - `킷으로 이 프로젝트 하네스 만들어줘`
   - `이 스킬 깔아도 돼? <GitHub 주소>`
   - `킷 카탈로그 보여줘`

업데이트는 `git pull` 뒤에 같은 절차를 다시 따른다. 기존 설치는 `backups/` 폴더로 옮겨 둔다.

## 제거

`python3 install.py --uninstall` (한쪽만 지우려면 `--target`). 지운 폴더는 `backups/`에 남는다.

## 수동 설치 (Python이 없을 때)

`skills/harnesskit` 폴더를 통째로 복사한다.

- Claude Code: `~/.claude/skills/harnesskit`
- Codex: `~/.codex/skills/harnesskit`

같은 이름의 폴더가 있으면 먼저 다른 이름으로 옮겨 둔다. HarnessKit의 스캔·충돌 체크 스크립트는 Python을 쓰므로 Python 설치도 함께 권한다.
